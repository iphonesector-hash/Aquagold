"""AquaGold operational v8: reports, recurring service, push, reporting bot, health."""
from __future__ import annotations

import base64
import gzip
import io
import json
import os
import re
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from flask import Response, jsonify, request, send_file

import app_v3
import aqua_ai
import bale_bridge
from aquagold_validation import ValidationError, text as valid_text

app = app_v3.app
TEHRAN = ZoneInfo("Asia/Tehran")
CANCEL_REASONS = ("مشتری منصرف شد", "قیمت", "عدم حضور", "زمان نامناسب", "آدرس اشتباه", "پاسخ نداد", "سپرد به شخص دیگر", "سایر")


def _safe_json(value):
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return app_v3.row_json(value) if hasattr(value, "keys") else value


def _date_arg(name, default=None):
    raw = (request.args.get(name) or default or "").strip()
    if not raw:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValidationError("تاریخ معتبر نیست")
    return raw


def _range_clause(date_expr="coalesce(v.visited_at,v.created_at)"):
    start = _date_arg("from")
    end = _date_arg("to")
    where, params = [], []
    if start:
        where.append(f"({date_expr} at time zone 'Asia/Tehran')::date >= %s::date")
        params.append(start)
    if end:
        where.append(f"({date_expr} at time zone 'Asia/Tehran')::date <= %s::date")
        params.append(end)
    return (" and ".join(where) if where else "true"), params


def _setting(cur, key, default=None):
    cur.execute("select value from app_settings where key=%s", (key,))
    row = cur.fetchone()
    return dict((row or {}).get("value") or default or {})


def _save_setting(cur, key, value):
    cur.execute(
        "insert into app_settings(key,value,updated_at) values(%s,%s,now()) "
        "on conflict(key) do update set value=excluded.value,updated_at=now()",
        (key, app_v3.Jsonb(value)),
    )


def _reporting_settings(cur=None):
    own = cur is None
    ctx = app_v3.get_db() if own else None
    db = ctx.__enter__() if own else None
    cursor = db.cursor() if own else cur
    try:
        data = _setting(cursor, "reporting_bot")
    finally:
        if own:
            cursor.close(); ctx.__exit__(None, None, None)
    token = bale_bridge._decrypt(data.get("bot_token_cipher"))
    return {
        "enabled": bool(data.get("enabled", True)),
        "chat_id": str(data.get("chat_id") or ""),
        "send_nightly": bool(data.get("send_nightly", True)),
        "send_backup": bool(data.get("send_backup", True)),
        "bot_token": token,
        "bot_token_cipher": data.get("bot_token_cipher") or "",
    }


def _consume_reporting_bootstrap():
    try:
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("select value from app_settings where key='reporting_bot_bootstrap' for update")
            row = cur.fetchone()
            data = dict((row or {}).get("value") or {})
            encoded = str(data.get("bot_token") or "")
            if not encoded:
                return
            token = base64.b64decode(encoded).decode()
            current = _reporting_settings(cur)
            stored = {
                "enabled": True,
                "chat_id": current.get("chat_id") or "",
                "send_nightly": True,
                "send_backup": True,
                "bot_token_cipher": bale_bridge._encrypt(token),
            }
            _save_setting(cur, "reporting_bot", stored)
            cur.execute("delete from app_settings where key='reporting_bot_bootstrap'")
    except Exception as exc:
        app_v3.logger.warning("reporting_bot_bootstrap_failed: %s", exc)


_consume_reporting_bootstrap()


def _bale_document(token, chat_id, filename, payload, caption=""):
    if not token or not chat_id:
        raise RuntimeError("ربات گزارش یا کانال گزارش تنظیم نشده است")
    boundary = "----AquaGoldReport" + secrets.token_hex(12)
    parts = []
    def field(name, value):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    field("chat_id", chat_id)
    if caption:
        field("caption", caption)
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{filename}\"\r\n"
        "Content-Type: application/gzip\r\n\r\n".encode()
    )
    parts.extend([payload, f"\r\n--{boundary}--\r\n".encode()])
    req = urllib.request.Request(
        bale_bridge.BALE_API.format(token=token, method="sendDocument"),
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        result = json.loads(response.read().decode(errors="replace") or "{}")
        if result.get("ok") is False:
            detail = str(result.get("description") or result.get("message") or "پاسخ ناموفق")[:300]
            raise RuntimeError(f"بله فایل را نپذیرفت: {detail}")
        return result


def _backup_bytes():
    tables = [
        "customers_v2", "customer_phones", "service_visits", "service_items", "expenses",
        "company_settlements", "products", "invoices", "invoice_items", "inventory",
        "bale_jobs", "customer_notes", "service_media", "audit_log",
    ]
    out = {"format": "AquaGold Backup v8", "created_at": datetime.now(timezone.utc).isoformat(), "tables": {}}
    with app_v3.get_db() as db, db.cursor() as cur:
        for table in tables:
            try:
                cur.execute(f"select * from {table} order by 1")
                out["tables"][table] = [app_v3.row_json(r) for r in cur.fetchall()]
            except Exception as exc:
                db.rollback()
                out["tables"][table] = {"error": str(exc)[:160]}
        out["settings"] = {}
        for key in ("finance", "admin_profile"):
            out["settings"][key] = _setting(cur, key, {})
    raw = json.dumps(out, ensure_ascii=False, default=str, separators=(",", ":")).encode()
    return gzip.compress(raw, compresslevel=6)


def _send_push(title, body, url="/", tag="aquagold"):
    try:
        from pywebpush import webpush
    except Exception:
        return 0
    sent = 0
    with app_v3.get_db() as db, db.cursor() as cur:
        vapid = _ensure_vapid(cur)
        cur.execute("select id,subscription from push_subscriptions where active=true")
        rows = cur.fetchall()
        for row in rows:
            try:
                webpush(
                    subscription_info=dict(row["subscription"]),
                    data=json.dumps({"title": title, "body": body, "url": url, "tag": tag}, ensure_ascii=False),
                    vapid_private_key=vapid["private_pem"],
                    vapid_claims={"sub": "mailto:admin@aquagold.local"},
                    ttl=3600,
                )
                sent += 1
            except Exception as exc:
                if "410" in str(exc) or "404" in str(exc):
                    cur.execute("update push_subscriptions set active=false where id=%s", (row["id"],))
    return sent


def _ensure_vapid(cur):
    data = _setting(cur, "web_push")
    private_pem = bale_bridge._decrypt(data.get("private_cipher"))
    public_key = data.get("public_key") or ""
    if private_pem and public_key and "-----BEGIN" not in private_pem:
        return {"private_pem": private_pem, "public_key": public_key}
    key = serialization.load_pem_private_key(private_pem.encode(), password=None) if private_pem else ec.generate_private_key(ec.SECP256R1())
    private_pem = base64.urlsafe_b64encode(key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())).rstrip(b"=").decode()
    numbers = key.public_key().public_numbers()
    raw = b"\x04" + numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
    public_key = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    _save_setting(cur, "web_push", {"private_cipher": bale_bridge._encrypt(private_pem), "public_key": public_key})
    return {"private_pem": private_pem, "public_key": public_key}


@app.get("/api/ops/company-share")
@app_v3.roles_required("technician")
def ops_company_share():
    clause, params = _range_clause()
    settle_clause, settle_params = _range_clause("s.settled_at")
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(f"""
            select (coalesce(v.visited_at,v.created_at) at time zone 'Asia/Tehran')::date day,
                   count(*)::int services,
                   coalesce(sum(v.received_amount),0)::bigint received,
                   coalesce(sum(v.company_share_amount),0)::bigint company_share,
                   coalesce(sum(v.received_amount-v.company_share_amount),0)::bigint own_share
            from service_visits v where {clause}
            group by 1 order by 1 desc
        """, params)
        days = [app_v3.row_json(r) for r in cur.fetchall()]
        cur.execute(f"""select (s.settled_at at time zone 'Asia/Tehran')::date day,
                               coalesce(sum(s.amount),0)::bigint settled
                        from company_settlements s where {settle_clause}
                        group by 1""", settle_params)
        settled_by_day = {str(row["day"]): int(row["settled"] or 0) for row in cur.fetchall()}
        for day in days:
            day["settled"] = settled_by_day.get(str(day["day"]), 0)
            day["balance"] = int(day.get("company_share") or 0) - day["settled"]
        cur.execute(f"select coalesce(sum(s.amount),0)::bigint settled from company_settlements s where {settle_clause}", settle_params)
        settled = int(cur.fetchone()["settled"] or 0)
    total = sum(int(x["company_share"] or 0) for x in days)
    return jsonify({"days": days, "totals": {"company_share": total, "settled": settled, "due": max(total-settled, 0), "received": sum(int(x["received"] or 0) for x in days), "own_share": sum(int(x["own_share"] or 0) for x in days)}})


@app.get("/api/ops/cancellations")
@app_v3.roles_required("technician")
def ops_cancellations():
    start, end = _date_arg("from"), _date_arg("to")
    where, params = ["status='cancelled'"], []
    if start:
        where.append("(coalesce(cancelled_at,updated_at) at time zone 'Asia/Tehran')::date >= %s::date"); params.append(start)
    if end:
        where.append("(coalesce(cancelled_at,updated_at) at time zone 'Asia/Tehran')::date <= %s::date"); params.append(end)
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(f"select * from bale_jobs where {' and '.join(where)} order by coalesce(cancelled_at,updated_at) desc limit 1000", params)
        rows = [app_v3.row_json(r) for r in cur.fetchall()]
        cur.execute(f"select coalesce(nullif(cancel_reason,''),'نامشخص') reason,count(*)::int count from bale_jobs where {' and '.join(where)} group by 1 order by count desc", params)
        reasons = [app_v3.row_json(r) for r in cur.fetchall()]
    return jsonify({"rows": rows, "reasons": reasons, "total": len(rows), "reason_options": CANCEL_REASONS})


@app.get("/api/ops/financial-report")
@app_v3.roles_required("technician")
def ops_financial_report():
    clause, params = _range_clause()
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(f"""
            select v.id::text,coalesce(v.visited_at,v.created_at) visit_date,
                   trim(concat_ws(' ',c.first_name,c.last_name)) customer_name,
                   (select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone,
                   v.service_type,v.invoice_amount,v.received_amount,v.company_share_amount,
                   (v.received_amount-v.company_share_amount) own_share_amount,v.customer_balance
            from service_visits v join customers_v2 c on c.id=v.customer_id
            where {clause} order by visit_date
        """, params)
        rows = [app_v3.row_json(r) for r in cur.fetchall()]
        exp_clause, exp_params = _range_clause("e.expense_date::timestamptz")
        cur.execute(f"select coalesce(sum(e.amount),0)::bigint expenses from expenses e where {exp_clause}", exp_params)
        expenses = int(cur.fetchone()["expenses"] or 0)
        cancel_clause, cancel_params = _range_clause("coalesce(b.cancelled_at,b.updated_at)")
        cur.execute(f"select count(*)::int cancellations from bale_jobs b where b.status='cancelled' and {cancel_clause}", cancel_params)
        cancellations = int(cur.fetchone()["cancellations"] or 0)
    totals = {
        "invoice": sum(int(r.get("invoice_amount") or 0) for r in rows),
        "received": sum(int(r.get("received_amount") or 0) for r in rows),
        "company_share": sum(int(r.get("company_share_amount") or 0) for r in rows),
        "customer_balance": sum(int(r.get("customer_balance") or 0) for r in rows),
        "expenses": expenses,
        "service_count": len(rows),
        "cancellations": cancellations,
    }
    totals["own_share"] = totals["received"] - totals["company_share"] - expenses
    by_day = {}
    for r in rows:
        day = str(r.get("visit_date") or "")[:10]
        d = by_day.setdefault(day, {"day": day, "received": 0, "company_share": 0, "services": 0})
        d["received"] += int(r.get("received_amount") or 0); d["company_share"] += int(r.get("company_share_amount") or 0); d["services"] += 1
    return jsonify({"rows": rows, "totals": totals, "days": list(by_day.values())})


@app.get("/api/ops/profile")
@app_v3.roles_required("technician")
def ops_profile_get():
    with app_v3.get_db() as db, db.cursor() as cur:
        data = _setting(cur, "admin_profile")
    return jsonify(data)


@app.patch("/api/ops/profile")
@app_v3.roles_required("admin")
def ops_profile_set():
    data = request.get_json() or {}
    clean = {
        "first_name": valid_text(data.get("first_name"), "نام", required=False, max_length=100),
        "last_name": valid_text(data.get("last_name"), "نام خانوادگی", required=False, max_length=100),
        "title": valid_text(data.get("title") or "مدیر AquaGold", "عنوان", required=False, max_length=120),
        "phone": valid_text(data.get("phone"), "شماره تماس", required=False, max_length=30),
        "photo": str(data.get("photo") or "")[:700000],
        "signature": str(data.get("signature") or "")[:500000],
    }
    with app_v3.get_db() as db, db.cursor() as cur:
        _save_setting(cur, "admin_profile", clean)
        app_v3.audit(cur, "app_setting", "admin_profile", "update", after={"name": f"{clean['first_name']} {clean['last_name']}".strip()})
    return jsonify(clean)


@app.get("/api/ops/recurring")
@app_v3.roles_required("technician")
def ops_recurring():
    try:
        days = max(0, min(int(request.args.get("days") or 30), 365))
    except (TypeError, ValueError):
        days = 30
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("""
          with latest as (
            select distinct on (v.customer_id) v.id,v.customer_id,v.next_service_at,v.service_type
            from service_visits v where v.status='completed'
            order by v.customer_id,coalesce(v.visited_at,v.created_at) desc,v.created_at desc
          )
          select v.id::text service_id,v.customer_id::text,trim(concat_ws(' ',c.first_name,c.last_name)) customer_name,
                 (select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone,
                 c.address,v.next_service_at,v.service_type
          from latest v join customers_v2 c on c.id=v.customer_id
          where v.next_service_at is not null and v.next_service_at <= now() + (%s||' days')::interval
          order by v.next_service_at asc limit 500
        """, (days,))
        rows = [app_v3.row_json(r) for r in cur.fetchall()]
    return jsonify(rows)


@app.get("/api/ops/customer/<customer_id>/timeline")
@app_v3.roles_required("technician")
def ops_customer_timeline(customer_id):
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("""select id::text,coalesce(visited_at,created_at) at,'service' kind,service_type title,description,
                              received_amount amount,next_service_at,created_at
                       from service_visits where customer_id=%s::uuid order by coalesce(visited_at,created_at) desc limit 300""", (customer_id,))
        services = [app_v3.row_json(r) for r in cur.fetchall()]
        cur.execute("select id::text,created_at at,'note' kind,note_type title,note_text description,null::bigint amount,null::timestamptz next_service_at,created_at,audio_data_url,audio_mime_type from customer_notes where customer_id=%s::uuid order by created_at desc limit 300", (customer_id,))
        notes = [app_v3.row_json(r) for r in cur.fetchall()]
        cur.execute("""select id::text,issued_at at,'invoice' kind,'فاکتور '||invoice_no title,notes description,total amount,null::timestamptz next_service_at,created_at
                       from invoices where customer_id=%s::uuid order by issued_at desc limit 200""", (customer_id,))
        invoices = [app_v3.row_json(r) for r in cur.fetchall()]
        cur.execute("""select m.id::text,m.created_at at,'media' kind,
                              case m.kind when 'before' then 'تصویر قبل از کار' else 'تصویر بعد از کار' end title,
                              null::text description,null::bigint amount,null::timestamptz next_service_at,
                              m.created_at,m.data_url,m.kind media_kind
                       from service_media m join service_visits v on v.id=m.service_visit_id
                       where v.customer_id=%s::uuid order by m.created_at desc limit 300""", (customer_id,))
        media = [app_v3.row_json(r) for r in cur.fetchall()]
    rows = services + notes + invoices + media
    rows.sort(key=lambda x: str(x.get("at") or x.get("created_at") or ""), reverse=True)
    return jsonify(rows)


@app.post("/api/ops/customer/<customer_id>/notes")
@app_v3.roles_required("technician")
def ops_customer_note_add(customer_id):
    data = request.get_json() or {}
    text = valid_text(data.get("text"), "یادداشت", required=True, max_length=5000)
    note_type = str(data.get("type") or "text")
    if note_type not in {"text", "voice"}: note_type = "text"
    audio_data_url = str(data.get("audio_data_url") or "")
    audio_mime_type = str(data.get("audio_mime_type") or "")[:100]
    if note_type == "voice" and (not audio_data_url.startswith("data:audio/") or len(audio_data_url) > 3000000):
        raise ValidationError("فایل صوتی معتبر و حداکثر حدود ۲ مگابایت باشد")
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("insert into customer_notes(customer_id,note_text,note_type,audio_data_url,audio_mime_type,created_by) values(%s::uuid,%s,%s,%s,%s,%s) returning id,created_at", (customer_id,text,note_type,audio_data_url or None,audio_mime_type or None,str(request.current_user.get("user_id"))))
        row = cur.fetchone()
        app_v3.audit(cur,"customer",customer_id,"note",after={"type":note_type})
    return jsonify({"ok":True,"id":row["id"],"created_at":row["created_at"].isoformat()})


@app.get("/api/ops/service/<service_id>/media")
@app_v3.roles_required("technician")
def ops_service_media_list(service_id):
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select id,kind,data_url,created_at from service_media where service_visit_id=%s::uuid order by created_at", (service_id,))
        rows=[app_v3.row_json(r) for r in cur.fetchall()]
    return jsonify(rows)


@app.post("/api/ops/service/<service_id>/media")
@app_v3.roles_required("technician")
def ops_service_media_add(service_id):
    data=request.get_json() or {}
    kind=str(data.get("kind") or "")
    if kind not in {"before","after"}: raise ValidationError("نوع عکس معتبر نیست")
    data_url=str(data.get("data_url") or "")
    if not data_url.startswith("data:image/") or len(data_url)>1500000: raise ValidationError("عکس معتبر و حداکثر حدود ۱ مگابایت باشد")
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("insert into service_media(service_visit_id,kind,data_url,created_by) values(%s::uuid,%s,%s,%s) returning id", (service_id,kind,data_url,str(request.current_user.get("user_id"))))
        row=cur.fetchone()
    return jsonify({"ok":True,"id":row["id"]})


@app.post("/api/ops/bale/jobs/<job_id>/restore")
@app_v3.roles_required("technician")
def ops_restore_cancelled(job_id):
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select status from bale_jobs where id=%s::uuid for update",(job_id,)); row=cur.fetchone()
        if not row or row["status"]!="cancelled": raise ValidationError("این کار کنسل‌شده نیست")
        cur.execute("update bale_jobs set status='new',cancel_reason=null,cancelled_at=null,updated_at=now() where id=%s::uuid",(job_id,))
        app_v3.audit(cur,"bale_job",job_id,"restore",before={"status":"cancelled"},after={"status":"new"})
    return jsonify({"ok":True})


@app.get("/api/ops/health")
@app_v3.roles_required("technician")
def ops_health():
    status = {"database": False, "bale": False, "reporting_bot": False, "groq": False, "elevenlabs": False, "push": False, "last_sync": None}
    try:
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("select 1 ok"); status["database"] = cur.fetchone()["ok"] == 1
            vapid = _ensure_vapid(cur); status["push"] = bool(vapid.get("public_key"))
            cur.execute("select max(run_at) last_sync from ops_cron_runs")
            row = cur.fetchone(); status["last_sync"] = row["last_sync"].isoformat() if row and row["last_sync"] else None
    except Exception:
        pass
    try:
        bs = bale_bridge._load_settings(); status["bale"] = bool(bs.get("enabled") and bs.get("bot_token"))
    except Exception:
        pass
    try:
        rs = _reporting_settings(); status["reporting_bot"] = bool(rs.get("bot_token") and rs.get("chat_id"))
    except Exception:
        pass
    try:
        ai = aqua_ai.configuration_status(); status["groq"] = bool(ai.get("brain")); status["elevenlabs"] = bool(ai.get("voice"))
    except Exception:
        pass
    return jsonify(status)


@app.get("/api/ops/notifications")
@app_v3.roles_required("technician")
def notifications_list():
    user_id = str(request.current_user.get("user_id"))
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("""select id::text,title,body,page,category,created_at,read_at
                       from app_notifications
                       where dismissed_at is null and (user_id is null or user_id=%s)
                       order by created_at desc limit 200""", (user_id,))
        rows = [app_v3.row_json(row) for row in cur.fetchall()]
    return jsonify({"rows": rows, "unread": sum(1 for row in rows if not row.get("read_at"))})


@app.patch("/api/ops/notifications/<notification_id>")
@app_v3.roles_required("technician")
def notification_update(notification_id):
    data = request.get_json() or {}
    action = str(data.get("action") or "read")
    if action not in {"read", "dismiss"}:
        raise ValidationError("عملیات اعلان معتبر نیست")
    column = "read_at" if action == "read" else "dismissed_at"
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(f"update app_notifications set {column}=now() where id=%s::uuid and (user_id is null or user_id=%s) returning id", (notification_id, str(request.current_user.get("user_id"))))
        if not cur.fetchone():
            return jsonify({"error": "اعلان پیدا نشد"}), 404
    return jsonify({"ok": True})


@app.post("/api/ops/notifications/read-all")
@app_v3.roles_required("technician")
def notifications_read_all():
    user_id = str(request.current_user.get("user_id"))
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("update app_notifications set read_at=coalesce(read_at,now()) where dismissed_at is null and (user_id is null or user_id=%s)", (user_id,))
    return jsonify({"ok": True})


@app.get("/api/ops/reporting-bot/settings")
@app_v3.roles_required("admin")
def reporting_settings_get():
    s = _reporting_settings()
    return jsonify({"enabled": s["enabled"], "chat_id": s["chat_id"], "send_nightly": s["send_nightly"], "send_backup": s["send_backup"], "token_configured": bool(s["bot_token"]), "token_mask": f"••••{s['bot_token'][-4:]}" if s["bot_token"] else ""})


@app.patch("/api/ops/reporting-bot/settings")
@app_v3.roles_required("admin")
def reporting_settings_set():
    data = request.get_json() or {}
    with app_v3.get_db() as db, db.cursor() as cur:
        current = _reporting_settings(cur)
        token = current.get("bot_token") or ""
        if data.get("bot_token") not in (None, "", "********"):
            token = valid_text(data.get("bot_token"), "توکن ربات گزارش", required=True, max_length=500)
        stored = {
            "enabled": bool(data.get("enabled", current.get("enabled", True))),
            "chat_id": str(data.get("chat_id", current.get("chat_id") or "")).strip(),
            "send_nightly": bool(data.get("send_nightly", current.get("send_nightly", True))),
            "send_backup": bool(data.get("send_backup", current.get("send_backup", True))),
            "bot_token_cipher": bale_bridge._encrypt(token) if token else current.get("bot_token_cipher", ""),
        }
        _save_setting(cur, "reporting_bot", stored)
    return reporting_settings_get()


@app.post("/api/ops/reporting-bot/test")
@app_v3.roles_required("admin")
def reporting_test():
    s = _reporting_settings()
    if not s["bot_token"]:
        raise ValidationError("توکن ربات گزارش تنظیم نشده")
    me = bale_bridge._bale_call(s["bot_token"], "getMe")
    if s["chat_id"]:
        bale_bridge._bale_call(s["bot_token"], "sendMessage", {"chat_id": s["chat_id"], "text": "✅ ربات گزارش AquaGold متصل شد"})
    return jsonify({"ok": True, "bot": me.get("result") or me})


@app.get("/api/ops/reporting-bot/discover")
@app_v3.roles_required("admin")
def reporting_discover():
    s = _reporting_settings()
    if not s["bot_token"]: raise ValidationError("توکن ربات گزارش تنظیم نشده")
    data = bale_bridge._bale_call(s["bot_token"], "getUpdates", {"limit": 30, "timeout": 0})
    chats = {}
    for upd in data.get("result") or []:
        msg = upd.get("channel_post") or upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            chats[str(chat["id"])] = {"id": str(chat["id"]), "title": chat.get("title") or chat.get("username") or str(chat["id"]), "type": chat.get("type")}
    return jsonify(list(chats.values()))


@app.get("/api/ops/backup")
@app_v3.roles_required("admin")
def ops_backup_download():
    data = _backup_bytes()
    name = "AquaGold-backup-" + datetime.now(TEHRAN).strftime("%Y%m%d-%H%M") + ".json.gz"
    return send_file(io.BytesIO(data), as_attachment=True, download_name=name, mimetype="application/gzip")


@app.post("/api/ops/backup/send")
@app_v3.roles_required("admin")
def ops_backup_send():
    s = _reporting_settings()
    if not s.get("bot_token") or not s.get("chat_id"):
        raise ValidationError("ابتدا ربات گزارش و کانال مقصد را تنظیم کن")
    data = _backup_bytes()
    name = "AquaGold-backup-" + datetime.now(TEHRAN).strftime("%Y%m%d-%H%M") + ".json.gz"
    result = _bale_document(s["bot_token"], s["chat_id"], name, data, "🛡 بکاپ AquaGold")
    return jsonify({"ok": bool(result.get("ok", True))})


@app.get("/api/ops/push/public-key")
@app_v3.token_required
def push_public_key():
    with app_v3.get_db() as db, db.cursor() as cur:
        vapid = _ensure_vapid(cur)
    return jsonify({"public_key": vapid["public_key"]})


@app.post("/api/ops/push/subscribe")
@app_v3.token_required
def push_subscribe():
    sub = request.get_json() or {}
    if not sub.get("endpoint"):
        raise ValidationError("اشتراک Push معتبر نیست")
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("""insert into push_subscriptions(user_id,subscription,active,updated_at)
                       values(%s,%s,true,now()) on conflict(subscription) do update set active=true,updated_at=now()""",
                    (str(request.current_user.get("user_id")), app_v3.Jsonb(sub)))
    return jsonify({"ok": True})


@app.post("/api/ops/push/test")
@app_v3.roles_required("admin")
def push_test():
    sent = _send_push("AquaGold", "اعلان آزمایشی با موفقیت ارسال شد", "/", "test")
    if not sent:
        return jsonify({"ok": False, "sent": 0, "error": "اعلان به هیچ دستگاه فعالی تحویل نشد؛ ابتدا Push را روی PWA نصب‌شده فعال کن"}), 409
    return jsonify({"ok": True, "sent": sent})


def _nightly_text():
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("""select count(*)::int services,coalesce(sum(received_amount),0)::bigint received,
                       coalesce(sum(company_share_amount),0)::bigint company_share
                       from service_visits where (coalesce(visited_at,created_at) at time zone 'Asia/Tehran')::date=(now() at time zone 'Asia/Tehran')::date""")
        r = cur.fetchone()
        cur.execute("select count(*)::int c from bale_jobs where status='cancelled' and (coalesce(cancelled_at,updated_at) at time zone 'Asia/Tehran')::date=(now() at time zone 'Asia/Tehran')::date")
        cancelled = int(cur.fetchone()["c"] or 0)
        cur.execute("select count(*)::int c from bale_jobs where status in ('new','review')")
        pending = int(cur.fetchone()["c"] or 0)
    own = int(r["received"] or 0) - int(r["company_share"] or 0)
    def fa(value):
        grouped = f"{int(value or 0):,}".replace(",", "،")
        return grouped.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    return ("🌙 گزارش شبانه AquaGold\n\n"
            f"سرویس‌های امروز: {fa(r['services'])}\n"
            f"دریافتی: {fa(r['received'])} تومان\n"
            f"سهم شرکت: {fa(r['company_share'])} تومان\n"
            f"سهم شما: {fa(own)} تومان\n"
            f"کنسلی امروز: {fa(cancelled)}\n"
            f"کارهای تعیین‌تکلیف‌نشده: {fa(pending)}")


@app.get("/api/ops/nightly")
@app_v3.limiter.exempt
def ops_nightly():
    auth = request.headers.get("Authorization", "")
    cron_secret = os.getenv("CRON_SECRET", "")
    schedule = request.headers.get("x-vercel-cron-schedule", "")
    if cron_secret:
        if auth != f"Bearer {cron_secret}":
            return jsonify({"ok": False}), 401
    elif schedule != "0 20 * * *":
        return jsonify({"ok": False}), 401
    run_key = "nightly:" + datetime.now(TEHRAN).strftime("%Y-%m-%d")
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("insert into ops_cron_runs(run_key) values(%s) on conflict do nothing returning run_key", (run_key,))
        if not cur.fetchone():
            cur.execute("select result from ops_cron_runs where run_key=%s", (run_key,))
            previous = dict((cur.fetchone() or {}).get("result") or {})
            if previous.get("ok") is True:
                return jsonify({"ok": True, "duplicate": True, "run_key": run_key, "result": previous})
    s = _reporting_settings()
    sent, errors = {}, {}
    if s["enabled"] and (s["send_nightly"] or s["send_backup"]) and (not s["bot_token"] or not s["chat_id"]):
        errors["configuration"] = "ربات گزارش یا کانال مقصد تنظیم نشده است"
    elif s["enabled"] and s["bot_token"] and s["chat_id"]:
        if s["send_nightly"]:
            try:
                sent["report"] = bale_bridge._bale_call(s["bot_token"], "sendMessage", {"chat_id": s["chat_id"], "text": _nightly_text()})
            except Exception as exc:
                errors["report"] = str(exc)[:180]
        if s["send_backup"]:
            try:
                data = _backup_bytes(); name = "AquaGold-backup-" + datetime.now(TEHRAN).strftime("%Y%m%d") + ".json.gz"
                sent["backup"] = _bale_document(s["bot_token"], s["chat_id"], name, data, "🛡 بکاپ شبانه AquaGold")
            except Exception as exc:
                errors["backup"] = str(exc)[:180]
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("""with latest as (
                         select distinct on (customer_id) id,customer_id,next_service_at
                         from service_visits where status='completed'
                         order by customer_id,coalesce(visited_at,created_at) desc,created_at desc
                       )
                       select v.id::text service_id,c.id::text,trim(concat_ws(' ',c.first_name,c.last_name)) name,v.next_service_at
                       from latest v join customers_v2 c on c.id=v.customer_id
                       where v.next_service_at between now()-interval '48 hours' and now()+interval '24 hours' limit 200""")
        due = [app_v3.row_json(r) for r in cur.fetchall()]
    due_sent = 0
    for c in due:
        reminder_key = f"recurring:{c['service_id']}:{c['next_service_at'].date().isoformat()}"
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("select 1 from ops_cron_runs where run_key=%s", (reminder_key,))
            if cur.fetchone():
                continue
            cur.execute("""insert into app_notifications(title,body,page,category,dedupe_key)
                           values(%s,%s,'recurring','recurring',%s) on conflict(dedupe_key) do nothing""",
                        ("موعد سرویس دوره‌ای", f"موعد سرویس دوره‌ای مشتری {c['name']} رسیده است.", reminder_key))
        count = _send_push("موعد سرویس دوره‌ای", f"موعد سرویس دوره‌ای مشتری {c['name']} رسیده است.", "/?open=recurring", "recurring-"+c["id"])
        if count:
            with app_v3.get_db() as db, db.cursor() as cur:
                cur.execute("insert into ops_cron_runs(run_key,result) values(%s,%s) on conflict do nothing", (reminder_key, app_v3.Jsonb({"sent": count})))
            due_sent += 1
    summary = {"ok": not errors, "due": len(due), "due_sent": due_sent, "sent": {k: bool(v) for k,v in sent.items()}, "errors": errors, "run_key": run_key}
    try:
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("update ops_cron_runs set result=%s where run_key=%s", (app_v3.Jsonb(summary), run_key))
    except Exception:
        pass
    return jsonify(summary), (200 if not errors else 502)
