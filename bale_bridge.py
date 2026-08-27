"""Bale Messenger bridge: group message intake -> AquaGold work inbox."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from flask import jsonify, request

import app_v3
from aquagold_validation import ValidationError, text as valid_text

BALE_API = "https://tapi.bale.ai/bot{token}/{method}"
KEYWORDS = ("فیلتر", "دستگاه", "ساید", "یخچال")
PHONE_RE = re.compile(r"(?:\+98|0098|0)?9[0-9۰-۹٠-٩]{9}")
PERSIAN_WORD_RE = re.compile(r"[آ-ی]{2,}")
DIGIT_TRANS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


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
    ctx = app_v3.get_db() if own else None
    db = ctx.__enter__() if own else None
    cursor = db.cursor() if own else cur
    try:
        cursor.execute("select value from app_settings where key='bale_bot'")
        row = cursor.fetchone()
        data = dict((row or {}).get("value") or {})
    finally:
        if own:
            cursor.close()
            ctx.__exit__(None, None, None)
    return {
        "enabled": bool(data.get("enabled", False)),
        "auto_reply": bool(data.get("auto_reply", True)),
        "allowed_chat_ids": [str(x) for x in (data.get("allowed_chat_ids") or [])],
        "webhook_secret": str(data.get("webhook_secret") or ""),
        "bot_token": _decrypt(data.get("bot_token_cipher")),
        "bot_token_cipher": data.get("bot_token_cipher") or "",
    }


def _public_settings(settings):
    token = settings.get("bot_token", "")
    return {
        "enabled": bool(settings.get("enabled")),
        "auto_reply": bool(settings.get("auto_reply", True)),
        "allowed_chat_ids": settings.get("allowed_chat_ids") or [],
        "bot_token_configured": bool(token),
        "bot_token_mask": f"••••{token[-4:]}" if token else "",
        "webhook_configured": bool(settings.get("webhook_secret")),
    }


def _bale_call(token, method, payload=None, timeout=15):
    if not token:
        raise RuntimeError("توکن ربات بله تنظیم نشده است")
    body = json.dumps(payload or {}, ensure_ascii=False).encode()
    req = urllib.request.Request(
        BALE_API.format(token=token, method=method),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode(errors="replace")
            return json.loads(raw) if raw else {"ok": True}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"بله پاسخ نداد ({exc.code}): {detail}") from exc


def _canonical_webhook(secret):
    return f"https://aquagold-db.vercel.app/api/bale/webhook/{secret}"


def _normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\u200c", " ")).strip()


def _normalize_phone(value):
    return app_v3.normalize_phone(str(value or "").translate(DIGIT_TRANS))


def _extract_job(text):
    raw = str(text or "").strip()
    flat = _normalize_text(raw)
    phone_match = PHONE_RE.search(raw)
    phone = _normalize_phone(phone_match.group(0)) if phone_match else ""
    keyword_hits = [word for word in KEYWORDS if word in flat]

    cleaned_for_name = PHONE_RE.sub(" ", flat)
    for junk in ("شماره", "تلفن", "موبایل", "آدرس", "کار", "سرویس", "تعویض", "نصب", "بررسی") + KEYWORDS:
        cleaned_for_name = cleaned_for_name.replace(junk, " ")
    words = [w for w in PERSIAN_WORD_RE.findall(cleaned_for_name) if len(w) >= 2]
    has_name_and_phone = bool(phone and words)
    if not keyword_hits and not has_name_and_phone:
        return None

    lines = [_normalize_text(x) for x in raw.splitlines() if _normalize_text(x)]
    customer_name = ""
    if phone_match:
        for line in lines:
            if PHONE_RE.search(line):
                candidate = PHONE_RE.sub("", line)
                candidate = re.sub(r"(?:شماره|تلفن|موبایل|آقا|خانم|مشتری)[:：]?", " ", candidate)
                candidate = _normalize_text(candidate)
                if PERSIAN_WORD_RE.search(candidate):
                    customer_name = candidate[:120]
                    break
    if not customer_name:
        for line in lines:
            if any(k in line for k in KEYWORDS):
                continue
            candidate = PHONE_RE.sub("", line)
            if len(PERSIAN_WORD_RE.findall(candidate)) >= 1:
                customer_name = _normalize_text(candidate)[:120]
                break

    address = ""
    address_markers = ("خیابان", "خ ", "کوچه", "پلاک", "واحد", "شهرک", "بلوار", "میدان", "اتوبان", "بزرگراه", "تهران", "کرج")
    address_lines = [line for line in lines if any(marker in line for marker in address_markers)]
    if address_lines:
        address = "، ".join(address_lines)[:1000]

    if "یخچال" in flat or "ساید" in flat:
        job_type = "یخچال/ساید"
    elif "فیلتر" in flat:
        job_type = "فیلتر"
    elif "دستگاه" in flat:
        job_type = "دستگاه"
    else:
        job_type = "سرویس"

    return {
        "customer_name": customer_name,
        "phone": phone,
        "address": address,
        "job_type": job_type,
        "matched_keywords": keyword_hits,
        "rule": "keyword" if keyword_hits else "name_phone",
    }


def _message_payload(update):
    message = update.get("message") or update.get("edited_message") or update.get("channel_post") or {}
    text = message.get("text") or message.get("caption") or ""
    chat = message.get("chat") or {}
    sender = message.get("from") or message.get("sender_chat") or {}
    sender_name = _normalize_text(" ".join(str(sender.get(k) or "") for k in ("first_name", "last_name"))) or str(sender.get("title") or "")
    return message, text, chat, sender, sender_name


def _send_chat(settings, chat_id, text, reply_to_message_id=None):
    if not settings.get("auto_reply") or not settings.get("bot_token"):
        return
    payload = {"chat_id": chat_id, "text": text}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        _bale_call(settings["bot_token"], "sendMessage", payload, timeout=8)
    except Exception as exc:
        app_v3.logger.warning("bale_send_failed: %s", exc)


def _find_customer_by_phone(cur, phone):
    if not phone:
        return None
    cur.execute("select customer_id from customer_phones where phone=%s order by is_primary desc,id limit 1", (phone,))
    row = cur.fetchone()
    return row["customer_id"] if row else None


@app_v3.app.post("/api/bale/webhook/<secret>")
@app_v3.limiter.exempt
def bale_webhook(secret):
    settings = _load_settings()
    expected = settings.get("webhook_secret") or ""
    if not expected or not hmac.compare_digest(secret, expected):
        return jsonify({"ok": False}), 404
    update = request.get_json(silent=True) or {}
    message, text, chat, sender, sender_name = _message_payload(update)
    if not message or not text:
        return jsonify({"ok": True, "ignored": "no_text"})
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    if chat_id is None or message_id is None:
        return jsonify({"ok": True, "ignored": "no_message_id"})
    allowed = set(settings.get("allowed_chat_ids") or [])
    if allowed and str(chat_id) not in allowed:
        return jsonify({"ok": True, "ignored": "chat_not_allowed"})
    parsed = _extract_job(text)
    if not parsed:
        return jsonify({"ok": True, "ignored": "not_work"})

    with app_v3.get_db() as db, db.cursor() as cur:
        customer_id = _find_customer_by_phone(cur, parsed.get("phone"))
        cur.execute(
            """insert into bale_jobs(bale_update_id,chat_id,chat_title,message_id,sender_id,sender_name,raw_text,customer_name,phone,address,job_type,customer_id,parsed)
               values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict(chat_id,message_id) do nothing returning id""",
            (
                update.get("update_id"), chat_id, chat.get("title"), message_id, sender.get("id"), sender_name,
                str(text)[:8000], parsed.get("customer_name"), parsed.get("phone"), parsed.get("address"),
                parsed.get("job_type"), customer_id, app_v3.Jsonb(parsed),
            ),
        )
        row = cur.fetchone()
    if row:
        _send_chat(settings, chat_id, "✅ کار در AquaGold ثبت شد", message_id)
        return jsonify({"ok": True, "registered": True, "job_id": str(row["id"])})
    return jsonify({"ok": True, "duplicate": True})


@app_v3.app.get("/api/bale/settings")
@app_v3.roles_required("admin")
def bale_settings_get():
    return jsonify(_public_settings(_load_settings()))


@app_v3.app.patch("/api/bale/settings")
@app_v3.roles_required("admin")
def bale_settings_set():
    data = request.get_json() or {}
    with app_v3.get_db() as db, db.cursor() as cur:
        current = _load_settings(cur)
        token = current.get("bot_token", "")
        if data.get("bot_token") not in (None, "", "********"):
            token = valid_text(data.get("bot_token"), "توکن بله", required=True, max_length=500)
        allowed_raw = data.get("allowed_chat_ids", current.get("allowed_chat_ids") or [])
        if isinstance(allowed_raw, str):
            allowed = [x.strip() for x in re.split(r"[,،\s]+", allowed_raw) if x.strip()]
        else:
            allowed = [str(x).strip() for x in (allowed_raw or []) if str(x).strip()]
        secret = current.get("webhook_secret") or hashlib.sha256((str(app_v3.app.secret_key) + datetime.now(timezone.utc).isoformat()).encode()).hexdigest()[:40]
        stored = {
            "enabled": bool(data.get("enabled", current.get("enabled", False))),
            "auto_reply": bool(data.get("auto_reply", current.get("auto_reply", True))),
            "allowed_chat_ids": allowed,
            "webhook_secret": secret,
            "bot_token_cipher": _encrypt(token) if token else current.get("bot_token_cipher", ""),
        }
        cur.execute(
            "insert into app_settings(key,value,updated_at) values('bale_bot',%s,now()) on conflict(key) do update set value=excluded.value,updated_at=now()",
            (app_v3.Jsonb(stored),),
        )
        app_v3.audit(cur, "app_setting", "bale_bot", "update", after={"enabled": stored["enabled"], "token": bool(token), "allowed_chats": len(allowed)})
    webhook_result = None
    if stored["enabled"] and token:
        webhook_result = _bale_call(token, "setWebhook", {"url": _canonical_webhook(secret)})
    result = _public_settings({**stored, "bot_token": token})
    result["webhook_url"] = _canonical_webhook(secret) if secret else ""
    result["webhook_result"] = webhook_result
    return jsonify(result)


@app_v3.app.post("/api/bale/test")
@app_v3.roles_required("admin")
def bale_test():
    settings = _load_settings()
    data = _bale_call(settings.get("bot_token"), "getMe")
    return jsonify({"ok": bool(data.get("ok", True)), "bot": data.get("result") or data})


@app_v3.app.get("/api/bale/jobs")
@app_v3.roles_required("technician")
def bale_jobs_list():
    status = (request.args.get("status") or "new").strip()
    if status not in {"new", "completed", "cancelled", "review", "all"}:
        raise ValidationError("وضعیت کار معتبر نیست")
    with app_v3.get_db() as db, db.cursor() as cur:
        if status == "all":
            cur.execute("select * from bale_jobs order by received_at desc limit 300")
        else:
            cur.execute("select * from bale_jobs where status=%s order by received_at desc limit 300", (status,))
        rows = [app_v3.row_json(x) for x in cur.fetchall()]
    return jsonify(rows)


@app_v3.app.get("/api/bale/jobs/counts")
@app_v3.roles_required("technician")
def bale_jobs_counts():
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select status,count(*)::int count from bale_jobs group by status")
        counts = {row["status"]: row["count"] for row in cur.fetchall()}
    return jsonify({"new": counts.get("new", 0), "review": counts.get("review", 0), "completed": counts.get("completed", 0), "cancelled": counts.get("cancelled", 0)})


def _get_locked_job(cur, job_id):
    cur.execute("select * from bale_jobs where id=%s::uuid for update", (job_id,))
    job = cur.fetchone()
    if not job:
        raise ValidationError("کار پیدا نشد")
    if job["status"] not in {"new", "review"}:
        raise ValidationError("این کار قبلاً تعیین تکلیف شده است")
    return job


def _ensure_customer(cur, job):
    customer_id = job.get("customer_id") or _find_customer_by_phone(cur, job.get("phone"))
    if customer_id:
        return customer_id
    name = _normalize_text(job.get("customer_name"))
    phone = _normalize_phone(job.get("phone"))
    if not name or not phone:
        return None
    cur.execute(
        "insert into customers_v2(last_name,normalized_name,address,map_label,created_by) values(%s,%s,%s,%s,%s) returning id",
        (name, app_v3.normalize_name(None, name), job.get("address") or None, name, str(request.current_user.get("user_id"))),
    )
    customer_id = cur.fetchone()["id"]
    cur.execute("insert into customer_phones(customer_id,phone,is_primary) values(%s,%s,true) on conflict do nothing", (customer_id, phone))
    return customer_id


@app_v3.app.post("/api/bale/jobs/<job_id>/complete")
@app_v3.roles_required("technician")
def bale_job_complete(job_id):
    data = request.get_json() or {}
    received = app_v3.as_int(data.get("received_amount"), -1)
    if received < 0:
        raise ValidationError("مبلغ دریافتی را وارد کن")
    with app_v3.get_db() as db, db.cursor() as cur:
        job = _get_locked_job(cur, job_id)
        customer_id = _ensure_customer(cur, job)
        service_visit_id = None
        if customer_id:
            pct = app_v3.finance_percent(cur)
            company = round(received * float(pct) / 100)
            cur.execute(
                """insert into service_visits(customer_id,registered_by,service_type,description,amount,invoice_amount,received_amount,company_share_percent,company_share_amount,customer_balance,overpayment_amount,status,visited_at,raw_chat_input)
                   values(%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,'completed',now(),%s) returning id""",
                (customer_id, str(request.current_user.get("user_id")), job.get("job_type") or "سرویس بله", job.get("raw_text"), received, received, received, pct, company, job.get("raw_text")),
            )
            service_visit_id = cur.fetchone()["id"]
        cur.execute(
            """update bale_jobs set status='completed',received_amount=%s,customer_id=coalesce(%s,customer_id),service_visit_id=%s,completed_at=now(),updated_at=now() where id=%s::uuid""",
            (received, customer_id, service_visit_id, job_id),
        )
        app_v3.audit(cur, "bale_job", job_id, "complete", before={"status": job["status"]}, after={"received_amount": received, "service_visit_id": str(service_visit_id) if service_visit_id else None})
    settings = _load_settings()
    _send_chat(settings, job["chat_id"], f"✅ کار انجام شد و در AquaGold ثبت شد. مبلغ دریافتی: {received:,} تومان", job["message_id"])
    return jsonify({"ok": True, "service_visit_id": str(service_visit_id) if service_visit_id else None})


@app_v3.app.post("/api/bale/jobs/<job_id>/cancel")
@app_v3.roles_required("technician")
def bale_job_cancel(job_id):
    data = request.get_json() or {}
    reason = valid_text(data.get("reason"), "علت کنسل شدن", required=True, max_length=1000)
    with app_v3.get_db() as db, db.cursor() as cur:
        job = _get_locked_job(cur, job_id)
        cur.execute("update bale_jobs set status='cancelled',cancel_reason=%s,cancelled_at=now(),updated_at=now() where id=%s::uuid", (reason, job_id))
        app_v3.audit(cur, "bale_job", job_id, "cancel", before={"status": job["status"]}, after={"reason": reason})
    settings = _load_settings()
    _send_chat(settings, job["chat_id"], f"❌ کار کنسل شد. علت: {reason}", job["message_id"])
    return jsonify({"ok": True})
