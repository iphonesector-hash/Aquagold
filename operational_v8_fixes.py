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


def _ensure_vapid_compatible(cur):
    """Store the private key as base64 DER, which pywebpush accepts as a string."""
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
        cur.execute("select coalesce(sum(amount),0)::bigint as settled from company_settlements")
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


def ops_nightly_fixed():
    """Nightly report + backup + exactly-once recurring-service push window."""
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
        if not cur.fetchone():
            return jsonify({"ok": True, "duplicate": True, "run_key": run_key})

    settings = operational_v8._reporting_settings()
    sent = {}
    if settings["enabled"] and settings["bot_token"] and settings["chat_id"]:
        if settings["send_nightly"]:
            sent["report"] = bale_bridge._bale_call(
                settings["bot_token"], "sendMessage",
                {"chat_id": settings["chat_id"], "text": operational_v8._nightly_text()},
            )
        if settings["send_backup"]:
            payload = operational_v8._backup_bytes()
            name = "AquaGold-backup-" + datetime.now(operational_v8.TEHRAN).strftime("%Y%m%d") + ".json.gz"
            sent["backup"] = operational_v8._bale_document(
                settings["bot_token"], settings["chat_id"], name, payload, "🛡 بکاپ شبانه AquaGold"
            )

    due_to_notify = []
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("""
            select v.id::text as service_id,v.next_service_at,c.id::text as customer_id,
                   trim(concat_ws(' ',c.first_name,c.last_name)) as name
            from service_visits v join customers_v2 c on c.id=v.customer_id
            where v.next_service_at between now()-interval '48 hours' and now()+interval '24 hours'
            order by v.next_service_at limit 200
        """)
        for row in cur.fetchall():
            reminder_key = "recurring:" + row["service_id"] + ":" + row["next_service_at"].date().isoformat()
            cur.execute(
                "insert into ops_cron_runs(run_key) values(%s) on conflict do nothing returning run_key",
                (reminder_key,),
            )
            if cur.fetchone():
                due_to_notify.append(dict(row))

    for item in due_to_notify:
        operational_v8._send_push(
            "موعد سرویس دوره‌ای",
            f"نوبت سرویس مجدد {item['name']} رسیده",
            "/?open=recurring",
            "recurring-" + item["customer_id"],
        )

    summary = {
        "ok": True,
        "due": len(due_to_notify),
        "sent": {key: bool(value) for key, value in sent.items()},
        "run_key": run_key,
    }
    try:
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("update ops_cron_runs set result=%s where run_key=%s", (app_v3.Jsonb(summary), run_key))
    except Exception:
        pass
    return jsonify(summary)


operational_v8.app.view_functions["ops_nightly"] = ops_nightly_fixed
