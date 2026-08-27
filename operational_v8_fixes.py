"""Final compatibility fixes discovered during AquaGold v8 release QA."""
import base64
import os
from datetime import datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from flask import jsonify, request

import app_v3
import bale_bridge
import operational_v8


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _fa_num(value):
    digits = str(int(value or 0))
    grouped = f"{int(digits):,}".replace(",", "،")
    return grouped.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _ensure_vapid_compatible(cur):
    """Store private VAPID key as base64 DER accepted by pywebpush/py_vapid."""
    data = operational_v8._setting(cur, "web_push")
    private_value = bale_bridge._decrypt(data.get("private_cipher"))
    public_key = data.get("public_key") or ""
    if private_value and public_key:
        if "-----BEGIN" not in private_value:
            return {"private_pem": private_value, "public_key": public_key}
        key = serialization.load_pem_private_key(private_value.encode(), password=None)
    else:
        key = ec.generate_private_key(ec.SECP256R1())
    private_der = key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    numbers = key.public_key().public_numbers()
    public_raw = b"\x04" + numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
    private_encoded = _b64url(private_der)
    public_key = _b64url(public_raw)
    operational_v8._save_setting(
        cur,
        "web_push",
        {"private_cipher": bale_bridge._encrypt(private_encoded), "public_key": public_key},
    )
    return {"private_pem": private_encoded, "public_key": public_key}


operational_v8._ensure_vapid = _ensure_vapid_compatible


def _ops_company_share_fixed():
    clause, params = operational_v8._range_clause()
    settle_clause, settle_params = operational_v8._range_clause("s.settled_at")
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(f"""
            select (coalesce(v.visited_at,v.created_at) at time zone 'Asia/Tehran')::date as report_day,
                   count(*)::int as services,
                   coalesce(sum(v.received_amount),0)::bigint as received,
                   coalesce(sum(v.company_share_amount),0)::bigint as company_share,
                   coalesce(sum(v.received_amount-v.company_share_amount),0)::bigint as own_share
            from service_visits v where {clause}
            group by 1 order by 1 desc
        """, params)
        days = []
        for row in cur.fetchall():
            item = app_v3.row_json(row)
            item["day"] = item.pop("report_day")
            days.append(item)
        cur.execute(f"select coalesce(sum(s.amount),0)::bigint as settled from company_settlements s where {settle_clause}", settle_params)
        settled = int(cur.fetchone()["settled"] or 0)
    company_share = sum(int(x.get("company_share") or 0) for x in days)
    received = sum(int(x.get("received") or 0) for x in days)
    own_share = sum(int(x.get("own_share") or 0) for x in days)
    return jsonify({
        "days": days,
        "totals": {
            "company_share": company_share,
            "settled": settled,
            "due": max(company_share - settled, 0),
            "received": received,
            "own_share": own_share,
        },
    })


operational_v8.app.view_functions["ops_company_share"] = app_v3.roles_required("technician")(_ops_company_share_fixed)


def _ops_recurring_fixed():
    try:
        days = max(0, min(int(request.args.get("days") or 30), 365))
    except (TypeError, ValueError):
        days = 30
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("""
          with latest as (
            select distinct on (v.customer_id)
                   v.id,v.customer_id,v.next_service_at,v.service_type,coalesce(v.visited_at,v.created_at) as service_at
            from service_visits v
            where v.status='completed'
            order by v.customer_id,coalesce(v.visited_at,v.created_at) desc,v.created_at desc
          )
          select l.id::text as service_id,l.customer_id::text,
                 trim(concat_ws(' ',c.first_name,c.last_name)) as customer_name,
                 (select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) as phone,
                 c.address,l.next_service_at,l.service_type
          from latest l join customers_v2 c on c.id=l.customer_id
          where l.next_service_at is not null and l.next_service_at <= now() + (%s||' days')::interval
          order by l.next_service_at asc limit 500
        """, (days,))
        rows = [app_v3.row_json(r) for r in cur.fetchall()]
    return jsonify(rows)


operational_v8.app.view_functions["ops_recurring"] = app_v3.roles_required("technician")(_ops_recurring_fixed)


def _ops_backup_send_fixed():
    settings = operational_v8._reporting_settings()
    if not settings.get("bot_token") or not settings.get("chat_id"):
        return jsonify({"error": "ابتدا ربات گزارش و کانال مقصد را در تنظیمات مشخص کن"}), 400
    data = operational_v8._backup_bytes()
    name = "AquaGold-backup-" + datetime.now(operational_v8.TEHRAN).strftime("%Y%m%d-%H%M") + ".json.gz"
    result = operational_v8._bale_document(
        settings["bot_token"], settings["chat_id"], name, data, "🛡 بکاپ AquaGold"
    )
    return jsonify({"ok": bool(result.get("ok", True))})


operational_v8.app.view_functions["ops_backup_send"] = app_v3.roles_required("admin")(_ops_backup_send_fixed)


def _nightly_text_fixed():
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("""select count(*)::int services,coalesce(sum(received_amount),0)::bigint received,
                       coalesce(sum(company_share_amount),0)::bigint company_share
                       from service_visits where (coalesce(visited_at,created_at) at time zone 'Asia/Tehran')::date=(now() at time zone 'Asia/Tehran')::date""")
        row = cur.fetchone()
        cur.execute("select count(*)::int c from bale_jobs where status='cancelled' and (coalesce(cancelled_at,updated_at) at time zone 'Asia/Tehran')::date=(now() at time zone 'Asia/Tehran')::date")
        cancelled = int(cur.fetchone()["c"] or 0)
        cur.execute("select count(*)::int c from bale_jobs where status in ('new','review')")
        pending = int(cur.fetchone()["c"] or 0)
    received = int(row["received"] or 0)
    company = int(row["company_share"] or 0)
    own = received - company
    return (
        "🌙 گزارش شبانه AquaGold\n\n"
        f"سرویس‌های امروز: {_fa_num(row['services'])}\n"
        f"دریافتی: {_fa_num(received)} تومان\n"
        f"سهم شرکت: {_fa_num(company)} تومان\n"
        f"سهم شما: {_fa_num(own)} تومان\n"
        f"کنسلی امروز: {_fa_num(cancelled)}\n"
        f"کارهای تعیین‌تکلیف‌نشده: {_fa_num(pending)}"
    )


operational_v8._nightly_text = _nightly_text_fixed


def ops_nightly_fixed():
    """Nightly report + backup + retry-safe recurring push processing."""
    auth = request.headers.get("Authorization", "")
    cron_secret = os.getenv("CRON_SECRET", "")
    schedule = request.headers.get("x-vercel-cron-schedule", "")
    if cron_secret:
        if auth != f"Bearer {cron_secret}":
            return jsonify({"ok": False}), 401
    elif schedule != "0 20 * * *":
        return jsonify({"ok": False}), 401

    run_key = "nightly:" + datetime.now(operational_v8.TEHRAN).strftime("%Y-%m-%d")
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("insert into ops_cron_runs(run_key) values(%s) on conflict do nothing returning run_key", (run_key,))
        inserted = cur.fetchone()
        if not inserted:
            cur.execute("select result from ops_cron_runs where run_key=%s", (run_key,))
            previous = cur.fetchone()
            result = dict((previous or {}).get("result") or {})
            if result.get("ok") is True:
                return jsonify({"ok": True, "duplicate": True, "run_key": run_key, "result": result})

    settings = operational_v8._reporting_settings()
    sent, errors = {}, {}
    if settings["enabled"] and settings["bot_token"] and settings["chat_id"]:
        if settings["send_nightly"]:
            try:
                sent["report"] = bale_bridge._bale_call(
                    settings["bot_token"], "sendMessage",
                    {"chat_id": settings["chat_id"], "text": operational_v8._nightly_text()},
                )
            except Exception as exc:
                errors["report"] = str(exc)[:180]
        if settings["send_backup"]:
            try:
                payload = operational_v8._backup_bytes()
                name = "AquaGold-backup-" + datetime.now(operational_v8.TEHRAN).strftime("%Y%m%d") + ".json.gz"
                sent["backup"] = operational_v8._bale_document(
                    settings["bot_token"], settings["chat_id"], name, payload, "🛡 بکاپ شبانه AquaGold"
                )
            except Exception as exc:
                errors["backup"] = str(exc)[:180]

    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("""
            with latest as (
              select distinct on (v.customer_id) v.id,v.customer_id,v.next_service_at
              from service_visits v where v.status='completed'
              order by v.customer_id,coalesce(v.visited_at,v.created_at) desc,v.created_at desc
            )
            select l.id::text as service_id,l.next_service_at,c.id::text as customer_id,
                   trim(concat_ws(' ',c.first_name,c.last_name)) as name
            from latest l join customers_v2 c on c.id=l.customer_id
            where l.next_service_at between now()-interval '48 hours' and now()+interval '24 hours'
            order by l.next_service_at limit 200
        """)
        candidates = [dict(r) for r in cur.fetchall()]

    due_sent = 0
    for item in candidates:
        reminder_key = "recurring:" + item["service_id"] + ":" + item["next_service_at"].date().isoformat()
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("select 1 from ops_cron_runs where run_key=%s", (reminder_key,))
            if cur.fetchone():
                continue
        count = operational_v8._send_push(
            "موعد سرویس دوره‌ای",
            f"نوبت سرویس مجدد {item['name']} رسیده",
            "/?open=recurring",
            "recurring-" + item["customer_id"],
        )
        if count > 0:
            with app_v3.get_db() as db, db.cursor() as cur:
                cur.execute(
                    "insert into ops_cron_runs(run_key,result) values(%s,%s) on conflict do nothing",
                    (reminder_key, app_v3.Jsonb({"sent": count})),
                )
            due_sent += 1

    ok = not errors
    summary = {
        "ok": ok,
        "due": len(candidates),
        "due_sent": due_sent,
        "sent": {key: bool(value) for key, value in sent.items()},
        "errors": errors,
        "run_key": run_key,
    }
    try:
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("update ops_cron_runs set result=%s where run_key=%s", (app_v3.Jsonb(summary), run_key))
    except Exception:
        pass
    return jsonify(summary), (200 if ok else 502)


operational_v8.app.view_functions["ops_nightly"] = ops_nightly_fixed
