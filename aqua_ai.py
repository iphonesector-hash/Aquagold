"""Aqua AI: encrypted provider settings, CRM tools, web-aware chat and voice."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from flask import Response, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import app_v3
from aquagold_validation import ValidationError, phone as valid_phone, text as valid_text


DEFAULTS = {
    "brain_provider": "groq",
    "brain_model": "groq/compound",
    "voice_provider": "elevenlabs",
    "voice_id": "JBFqnCBsd6RMkjVDRZzb",
    "tts_model": "eleven_v3",
    "stt_model": "scribe_v2",
    "auto_speak": False,
}
SECRET_FIELDS = {"groq_api_key", "elevenlabs_api_key"}
SAFE_FIELDS = set(DEFAULTS)
MODEL_RE = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")


def _fernet():
    material = str(app_v3.app.secret_key or "").encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material).digest()))


def _encrypt(value):
    return _fernet().encrypt(value.encode()).decode()


def _decrypt(value):
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


def _load_settings(cur=None):
    own = cur is None
    context = app_v3.get_db() if own else None
    db = context.__enter__() if own else None
    cursor = db.cursor() if own else cur
    try:
        cursor.execute("select value from app_settings where key='aqua_ai'")
        row = cursor.fetchone()
        stored = dict((row or {}).get("value") or {})
    finally:
        if own:
            cursor.close()
            context.__exit__(None, None, None)
    result = {**DEFAULTS, **{k: v for k, v in stored.items() if k in SAFE_FIELDS}}
    for field in SECRET_FIELDS:
        result[field] = _decrypt(stored.get(f"{field}_cipher")) or os.getenv(field.upper(), "")
    return result


def _consume_secret_bootstrap():
    try:
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("select value from app_settings where key='aqua_ai_bootstrap' for update")
            row = cur.fetchone()
            payload = dict((row or {}).get("value") or {})
            if not payload:
                return False
            current = _load_settings(cur)
            for key in SECRET_FIELDS:
                encoded = str(payload.get(key) or "")
                if encoded:
                    current[key] = base64.b64decode(encoded.encode()).decode()
            if payload.get("voice_id"):
                current["voice_id"] = str(payload["voice_id"])
            stored = {key: current[key] for key in SAFE_FIELDS}
            for key in SECRET_FIELDS:
                stored[f"{key}_cipher"] = _encrypt(current.get(key, "")) if current.get(key) else ""
            cur.execute("insert into app_settings(key,value,updated_at) values('aqua_ai',%s,now()) on conflict(key) do update set value=excluded.value,updated_at=now()", (app_v3.Jsonb(stored),))
            cur.execute("delete from app_settings where key='aqua_ai_bootstrap'")
        return True
    except Exception as exc:
        app_v3.logger.warning("aqua_ai_bootstrap_failed: %s", exc)
        return False


def _public_settings(settings):
    out = {k: settings.get(k) for k in SAFE_FIELDS}
    for field in SECRET_FIELDS:
        value = settings.get(field, "")
        out[f"{field}_configured"] = bool(value)
        out[f"{field}_mask"] = f"••••{value[-4:]}" if value else ""
    return out


_consume_secret_bootstrap()

def configuration_status():
    try:
        settings = _load_settings()
        return {"brain": bool(settings["groq_api_key"]), "voice": bool(settings["elevenlabs_api_key"]), "provider": "Aqua"}
    except Exception:
        return {"brain": bool(os.getenv("GROQ_API_KEY")), "voice": bool(os.getenv("ELEVENLABS_API_KEY")), "provider": "Aqua"}


def _serializer():
    return URLSafeTimedSerializer(app_v3.app.secret_key, salt="aqua-ai-action-v1")


def _post_json(url, payload, headers, timeout=45):
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0 AquaGold/7.2", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:800]
        raise RuntimeError(f"سرویس هوش مصنوعی پاسخ نداد ({exc.code}): {detail}") from exc


def _multipart(fields, file_name, file_bytes, content_type):
    boundary = f"----AquaGold{uuid.uuid4().hex}"
    chunks = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode())
    chunks.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file_name}\"\r\nContent-Type: {content_type}\r\n\r\n".encode()
    )
    chunks.extend([file_bytes, f"\r\n--{boundary}--\r\n".encode()])
    return boundary, b"".join(chunks)


def _customer_search(cur, query, limit=8):
    q = (query or "").strip()
    cur.execute(
        """
        select c.id::text,c.first_name,c.last_name,trim(concat_ws(' ',c.first_name,c.last_name)) name,
               c.address,c.map_label,c.device_model,
               case when c.location is null then null else st_y(c.location::geometry) end latitude,
               case when c.location is null then null else st_x(c.location::geometry) end longitude,
               (select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone
        from customers_v2 c
        where c.archived=false and (%s='' or c.normalized_name ilike '%%'||%s||'%%'
          or c.last_name ilike '%%'||%s||'%%' or coalesce(c.address,'') ilike '%%'||%s||'%%'
          or exists(select 1 from customer_phones p where p.customer_id=c.id and p.phone ilike '%%'||%s||'%%'))
        order by case when c.normalized_name ilike %s then 0 else 1 end,c.updated_at desc limit %s
        """,
        (q, q, q, q, q, f"%{q}%", limit),
    )
    return [app_v3.row_json(row) for row in cur.fetchall()]


def _map_query(text):
    if "نقشه" not in text or not any(word in text for word in ("مشتری", "پیدا", "نشان")):
        return None
    cleaned = re.sub(r"(?:پیدا کن|نشان بده|برای من|لطفاً|لطفا|برام|مشتری|روی|نقشه|رو|را|در)", " ", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _customer_draft(text):
    if "مشتری" not in text or not any(word in text for word in ("ثبت کن", "اضافه کن", "بساز")):
        return None
    phone_match = re.search(r"(?:\+98|0098|0)?9[0-9۰-۹٠-٩]{9}", text)
    name_match = re.search(r"مشتری\s+(.+?)(?=\s+(?:با\s+)?(?:شماره|موبایل|تلفن|آدرس)|\s+(?:ثبت کن|اضافه کن|بساز)|$)", text)
    address_match = re.search(r"آدرس\s+(.+?)(?=\s+(?:ثبت کن|اضافه کن|بساز)|$)", text)
    name = (name_match.group(1) if name_match else "").strip()
    if not name:
        return {"missing": ["نام مشتری"]}
    parts = name.split()
    return {
        "first_name": parts[0] if len(parts) > 1 else "",
        "last_name": " ".join(parts[1:]) if len(parts) > 1 else parts[0],
        "phones": [phone_match.group(0)] if phone_match else [],
        "address": address_match.group(1).strip() if address_match else "",
        "map_label": name,
    }


def _today_sales(cur):
    cur.execute(
        """
        select extract(hour from coalesce(visited_at,created_at) at time zone 'Asia/Tehran')::int as hour_of_day,
               coalesce(sum(invoice_amount),0)::bigint sales,coalesce(sum(received_amount),0)::bigint received
        from service_visits
        where (coalesce(visited_at,created_at) at time zone 'Asia/Tehran')::date=(now() at time zone 'Asia/Tehran')::date
        group by 1 order by 1
        """
    )
    points = [app_v3.row_json(row) for row in cur.fetchall()]
    for point in points:
        point["hour"] = point.pop("hour_of_day", point.get("hour"))
    return points, sum(int(x["sales"]) for x in points), sum(int(x["received"]) for x in points)


def _workspace_context(cur):
    cur.execute("select count(*)::int customers from customers_v2 where archived=false")
    customers = cur.fetchone()["customers"]
    cur.execute("select count(*)::int products from products where is_active=true")
    products = cur.fetchone()["products"]
    points, sales, received = _today_sales(cur)
    return {"customers": customers, "products": products, "today_sales": sales, "today_received": received, "hourly": points[-12:]}


def _groq_answer(settings, text, history, context):
    key = settings.get("groq_api_key")
    if not key:
        return "کلید Groq هنوز تنظیم نشده است. مدیر می‌تواند آن را از تنظیمات ← هوش مصنوعی آکوا وارد کند."
    compact_context = {
        "customers": int(context.get("customers") or 0),
        "products": int(context.get("products") or 0),
        "today_sales": int(context.get("today_sales") or 0),
        "today_received": int(context.get("today_received") or 0),
    }
    system_text = "تو آریا هستی؛ دستیار فارسی AquaGold و رفیق صمیمی کاربر. فارسی تهرانی، گرم، طبیعی و خودمونی حرف بزن؛ مثل یک دوست باهوش و قابل‌اعتماد، نه کارمند اداری. جواب‌ها روان و کوتاه باشند، گاهی از واژه‌های طبیعی مثل «آره»، «ببین»، «اوکی»، «حتماً» استفاده کن ولی لوس، مصنوعی یا بیش‌ازحد شوخ نباش. اگر موضوع جدی/مالی است دقیق بمان. تغییر دیتابیس را بدون تأیید کاربر انجام‌شده فرض نکن. وضعیت فعلی: " + json.dumps(compact_context, ensure_ascii=False)
    messages = [{"role": "system", "content": system_text}]
    # Keep the request comfortably below upstream body limits. The current user
    # message is appended separately, so remove an identical trailing history item.
    clean_history = []
    for item in (history or [])[-4:]:
        if item.get("role") not in {"user", "assistant"}:
            continue
        content = str(item.get("content", "")).strip()[:900]
        if content:
            clean_history.append({"role": item["role"], "content": content})
    if clean_history and clean_history[-1]["role"] == "user" and clean_history[-1]["content"] == str(text).strip()[:900]:
        clean_history.pop()
    messages.extend(clean_history)
    messages.append({"role": "user", "content": str(text)[:1800]})
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}"}
    payload = {"model": settings.get("brain_model") or "groq/compound", "messages": messages, "temperature": 0.2}
    try:
        data = _post_json(endpoint, payload, headers)
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "413" not in msg and "request_too_large" not in msg and "request entity too" not in msg:
            raise
        # One tiny retry without conversation history. This also makes old chats
        # with oversized error messages self-healing instead of permanently failing.
        retry_messages = [
            {"role": "system", "content": system_text[:900]},
            {"role": "user", "content": str(text)[:900]},
        ]
        # Compound can overflow internally on live-search/tool queries even with a tiny input.
        # Retry on compound-mini first, then a plain chat model so the user always gets a response.
        try:
            data = _post_json(endpoint, {"model": "groq/compound-mini", "messages": retry_messages, "temperature": 0.2}, headers)
        except RuntimeError:
            data = _post_json(endpoint, {"model": "llama-3.3-70b-versatile", "messages": retry_messages, "temperature": 0.2}, headers)
    return data["choices"][0]["message"]["content"]


@app_v3.app.get("/api/aqua-ai/settings")
@app_v3.token_required
def aqua_settings_get():
    return jsonify(_public_settings(_load_settings()))


@app_v3.app.patch("/api/aqua-ai/settings")
@app_v3.roles_required("admin")
def aqua_settings_set():
    data = request.get_json() or {}
    with app_v3.get_db() as db, db.cursor() as cur:
        current = _load_settings(cur)
        next_settings = {**current}
        for key in SAFE_FIELDS:
            if key in data:
                if key == "auto_speak":
                    next_settings[key] = bool(data[key])
                elif key in {"brain_provider", "voice_provider"}:
                    next_settings[key] = DEFAULTS[key]
                else:
                    value = valid_text(data[key], "تنظیم مدل هوش مصنوعی", required=True, max_length=100)
                    if not MODEL_RE.fullmatch(value):
                        raise ValidationError("نام مدل یا Voice ID معتبر نیست")
                    next_settings[key] = value
        for key in SECRET_FIELDS:
            if key in data and data[key] not in (None, "", "********"):
                next_settings[key] = valid_text(data[key], "کلید API", required=True, max_length=500)
            if key in (data.get("clear_keys") or []):
                next_settings[key] = ""
        stored = {key: next_settings[key] for key in SAFE_FIELDS}
        for key in SECRET_FIELDS:
            stored[f"{key}_cipher"] = _encrypt(next_settings.get(key, "")) if next_settings.get(key) else ""
        cur.execute(
            "insert into app_settings(key,value,updated_at) values('aqua_ai',%s,now()) on conflict(key) do update set value=excluded.value,updated_at=now()",
            (app_v3.Jsonb(stored),),
        )
        app_v3.audit(cur, "app_setting", "aqua_ai", "update", after={"brain": bool(next_settings["groq_api_key"]), "voice": bool(next_settings["elevenlabs_api_key"])})
    return jsonify(_public_settings(next_settings))


@app_v3.app.post("/api/aqua-ai/chat")
@app_v3.roles_required("technician")
@app_v3.limiter.limit("30 per minute; 500 per day")
def aqua_chat():
    data = request.get_json() or {}
    text = valid_text(data.get("text"), "پیام", required=True, max_length=4000)
    with app_v3.get_db() as db, db.cursor() as cur:
        map_name = _map_query(text)
        if map_name is not None:
            matches = _customer_search(cur, map_name)
            if not matches:
                return jsonify({"answer": "مشتری مطابق این عبارت پیدا نشد.", "results": []})
            customer = matches[0]
            if customer.get("latitude") is None:
                return jsonify({"answer": f"{customer['name']} پیدا شد، اما هنوز GPS ندارد.", "results": matches, "action": {"type": "open_customer", "customer": customer}})
            return jsonify({"answer": f"{customer['name']} را روی نقشه پیدا کردم.", "results": matches, "action": {"type": "show_customer_on_map", "customer": customer}})

        if "امروز" in text and any(word in text for word in ("فروش", "نمودار", "درآمد")):
            points, sales, received = _today_sales(cur)
            return jsonify({"answer": f"فروش امروز {sales:,} تومان و دریافتی {received:,} تومان است.", "chart": {"title": "فروش امروز", "points": points}, "action": {"type": "open_page", "page": "finance"}})

        draft = _customer_draft(text)
        if draft is not None:
            if draft.get("missing"):
                return jsonify({"answer": "برای ثبت مشتری، نام را هم بگو؛ نمونه: مشتری علی رضایی با شماره 0912… ثبت کن."})
            nonce = uuid.uuid4().hex
            cur.execute(
                "insert into aqua_ai_events(user_id,event_type,status,action_nonce,metadata) values(%s,'create_customer','pending',%s,%s)",
                (request.current_user.get("user_id"), nonce, app_v3.Jsonb({"name": draft["map_label"]})),
            )
            token = _serializer().dumps({"type": "create_customer", "payload": draft, "user_id": request.current_user.get("user_id"), "nonce": nonce})
            return jsonify({"answer": f"مشتری {draft['map_label']} آماده ثبت است. اطلاعات را بررسی و تأیید کن.", "pending_action": {"type": "create_customer", "label": f"ثبت {draft['map_label']}", "payload": draft, "token": token}})

        context = _workspace_context(cur)
    try:
        answer = _groq_answer(_load_settings(), text, data.get("history"), context)
    except RuntimeError as exc:
        answer = str(exc)
    return jsonify({"answer": answer})


@app_v3.app.post("/api/aqua-ai/actions/confirm")
@app_v3.roles_required("technician")
@app_v3.limiter.limit("20 per minute")
def aqua_confirm_action():
    token = valid_text((request.get_json() or {}).get("token"), "توکن عملیات", required=True, max_length=5000)
    try:
        action = _serializer().loads(token, max_age=600)
    except SignatureExpired:
        return jsonify({"error": "زمان تأیید این عملیات تمام شده؛ دوباره از آکوا بخواه"}), 400
    except BadSignature:
        return jsonify({"error": "عملیات معتبر نیست"}), 400
    if str(action.get("user_id")) != str(request.current_user.get("user_id")) or action.get("type") != "create_customer":
        return jsonify({"error": "این عملیات برای کاربر فعلی معتبر نیست"}), 403
    payload = action["payload"]
    nonce = action.get("nonce")
    if not nonce:
        return jsonify({"error": "شناسه عملیات معتبر نیست"}), 400
    phones = [valid_phone(value) for value in payload.get("phones", [])]
    with app_v3.get_db() as db, db.cursor() as cur:
        if phones:
            cur.execute("select phone from customer_phones where phone=any(%s) limit 1", (phones,))
            if cur.fetchone():
                return jsonify({"error": "این شماره قبلاً برای مشتری دیگری ثبت شده"}), 409
        cur.execute(
            "update aqua_ai_events set status='executing' where action_nonce=%s and user_id=%s and status='pending' returning id",
            (nonce, request.current_user.get("user_id")),
        )
        event = cur.fetchone()
        if not event:
            return jsonify({"error": "این عملیات قبلاً اجرا یا منقضی شده است"}), 409
        cur.execute(
            """insert into customers_v2(first_name,last_name,normalized_name,address,map_label,created_by)
               values(%s,%s,%s,%s,%s,%s) returning id""",
            (payload.get("first_name"), payload["last_name"], app_v3.normalize_name(payload.get("first_name"), payload["last_name"]), payload.get("address"), payload.get("map_label"), str(request.current_user.get("user_id"))),
        )
        customer_id = cur.fetchone()["id"]
        for index, phone in enumerate(phones):
            cur.execute("insert into customer_phones(customer_id,phone,is_primary) values(%s,%s,%s)", (customer_id, phone, index == 0))
        cur.execute("update aqua_ai_events set status='completed',metadata=metadata||%s where id=%s", (app_v3.Jsonb({"customer_id": str(customer_id)}), event["id"]))
        app_v3.audit(cur, "customer", customer_id, "aqua_ai_create", after={"name": payload.get("map_label"), "phones": phones})
    return jsonify({"answer": "مشتری با موفقیت توسط هوش مصنوعی آکوا ثبت شد.", "customer_id": str(customer_id)})


@app_v3.app.post("/api/aqua-ai/transcribe")
@app_v3.roles_required("technician")
@app_v3.limiter.limit("10 per minute; 100 per day")
def aqua_transcribe():
    upload = request.files.get("audio")
    if not upload:
        return jsonify({"error": "فایل صوتی دریافت نشد"}), 400
    audio = upload.read(8 * 1024 * 1024 + 1)
    if len(audio) > 8 * 1024 * 1024:
        return jsonify({"error": "صدا باید حداکثر ۸ مگابایت باشد"}), 413
    settings = _load_settings()
    key = settings.get("elevenlabs_api_key")
    if not key:
        return jsonify({"error": "کلید ElevenLabs در تنظیمات وارد نشده است"}), 409
    boundary, body = _multipart({"model_id": settings.get("stt_model") or "scribe_v2", "language_code": "fas"}, upload.filename or "aqua.webm", audio, upload.mimetype or "audio/webm")
    req = urllib.request.Request("https://api.elevenlabs.io/v1/speech-to-text", data=body, headers={"xi-api-key": key, "Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return jsonify({"error": f"تبدیل صدا ناموفق بود ({exc.code})"}), 502
    return jsonify({"text": payload.get("text", "")})


@app_v3.app.post("/api/aqua-ai/speak")
@app_v3.roles_required("technician")
@app_v3.limiter.limit("20 per minute; 200 per day")
def aqua_speak():
    text = valid_text((request.get_json() or {}).get("text"), "متن صدا", required=True, max_length=2500)
    settings = _load_settings()
    key = settings.get("elevenlabs_api_key")
    if not key:
        return jsonify({"error": "کلید ElevenLabs در تنظیمات وارد نشده است"}), 409
    voice_id = settings.get("voice_id") or DEFAULTS["voice_id"]
    requested_model = settings.get("tts_model") or "eleven_v3"
    models = [requested_model]
    if requested_model != "eleven_multilingual_v2":
        models.append("eleven_multilingual_v2")
    last_error = None
    for model_id in models:
        for attempt in range(3):
            req = urllib.request.Request(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
                data=json.dumps({"text": text, "model_id": model_id}, ensure_ascii=False).encode(),
                headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    audio = response.read()
                    if audio:
                        return Response(audio, mimetype="audio/mpeg", headers={"Cache-Control": "no-store", "X-Aqua-TTS-Model": model_id})
                    last_error = "empty_audio"
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:500]
                last_error = f"HTTP {exc.code}: {detail}"
                app_v3.logger.warning("aqua_tts_failed model=%s attempt=%s status=%s detail=%s", model_id, attempt + 1, exc.code, detail)
                if exc.code not in {408, 409, 422, 429, 500, 502, 503, 504}:
                    break
            except urllib.error.URLError as exc:
                last_error = str(exc.reason)[:300]
                app_v3.logger.warning("aqua_tts_network_failed model=%s attempt=%s detail=%s", model_id, attempt + 1, last_error)
            if attempt < 2:
                time.sleep(0.35 * (attempt + 1))
    app_v3.logger.error("aqua_tts_exhausted detail=%s", last_error)
    return jsonify({"error": "ساخت صدای آریا موقتاً ناموفق بود؛ دوباره تلاش کن"}), 502
