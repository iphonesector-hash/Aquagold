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
from smart_intake import parse_intake

BALE_API = "https://tapi.bale.ai/bot{token}/{method}"
KEYWORDS = ("فیلتر", "دستگاه", "ساید", "یخچال")


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
            result = json.loads(raw) if raw else {"ok": True}
            if result.get("ok") is False:
                detail = str(result.get("description") or result.get("message") or "پاسخ ناموفق")[:300]
                raise RuntimeError(f"بله عملیات را نپذیرفت: {detail}")
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"بله پاسخ نداد ({exc.code}): {detail}") from exc


def _canonical_webhook(secret):
    return f"https://aquagold-db.vercel.app/api/bale/webhook/{secret}"


def _normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\u200c", " ")).strip()


def _extract_job(text):
    raw = str(text or "").strip()
    flat = _normalize_text(raw)
    parsed = parse_intake(raw)
    phone = (parsed.get("phones") or [""])[0]
    keyword_hits = [word for word in KEYWORDS if word in flat]
    if not phone and not keyword_hits:
        return None
    return {
        "customer_name": parsed.get("last_name") or "",
        "phone": phone,
        "address": parsed.get("address") or "",
        "job_type": parsed.get("service_type") or "سرویس",
        "visitor_code": parsed.get("visitor_code"),
        "time_text": parsed.get("time_text"),
        "matched_keywords": keyword_hits,
        "rule": "smart-v8",
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
        try:
            from operational_v8 import _send_push
            label = parsed.get("customer_name") or parsed.get("phone") or "کار جدید"
            _send_push("کار جدید بله", label, "/?open=bale-jobs", "bale-job")
        except Exception as exc:
            app_v3.logger.warning("bale_push_failed: %s", exc)
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


@app_v3.app.post("/api/bale/jobs/<job_id>/complete")
@app_v3.roles_required("technician")
def bale_job_complete(job_id):
    return jsonify({
        "error": "این مسیر سرویس مستقل نمی‌سازد؛ کار را با «انجام شد ← ثبت هوشمند» تکمیل کن",
        "code": "SMART_INTAKE_REQUIRED",
    }), 409


@app_v3.app.post("/api/bale/jobs/<job_id>/finalize")
@app_v3.roles_required("technician")
def bale_job_finalize(job_id):
    data = request.get_json(silent=True) or {}
    service_visit_id = app_v3.valid_uuid(data.get("service_visit_id"), "شناسه سرویس", required=True)
    with app_v3.get_db() as db, db.cursor() as cur:
        job = _get_locked_job(cur, job_id)
        cur.execute(
            """select id,customer_id,received_amount from service_visits
               where id=%s::uuid and raw_chat_input=%s and registered_by=%s""",
            (service_visit_id, job.get("raw_text"), str(request.current_user.get("user_id"))),
        )
        service = cur.fetchone()
        if not service:
            raise ValidationError("ثبت هوشمند این کار پیدا نشد؛ ابتدا ثبت نهایی را انجام بده")
        cur.execute(
            """update bale_jobs set status='completed',customer_id=%s,service_visit_id=%s,
               received_amount=%s,completed_at=now(),updated_at=now() where id=%s::uuid""",
            (service["customer_id"], service["id"], service["received_amount"], job_id),
        )
        app_v3.audit(cur, "bale_job", job_id, "smart_finalize", before={"status": job["status"]}, after={"service_visit_id": str(service["id"])})
    settings = _load_settings()
    _send_chat(settings, job["chat_id"], "✅ کار از طریق ثبت هوشمند AquaGold انجام و وارد سرویس‌های اصلی شد", job["message_id"])
    return jsonify({"ok": True, "service_visit_id": str(service["id"]), "customer_id": str(service["customer_id"])})


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
