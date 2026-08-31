"""Management notifications and scheduled Bale reports for AquaGold.

This module intentionally layers on top of ``bale_bridge`` so the existing
Bale work-ingest flow stays untouched.
"""

from __future__ import annotations

import hmac
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import jsonify, request

import app_v3
import bale_bridge

TEHRAN = ZoneInfo("Asia/Tehran")
REPORTS_KEY = "bale_reports"
PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
ARABIC_TO_PERSIAN = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})


def _load_report_settings(cur=None):
    own = cur is None
    ctx = app_v3.get_db() if own else None
    db = ctx.__enter__() if own else None
    cursor = db.cursor() if own else cur
    try:
        cursor.execute("select value from app_settings where key=%s", (REPORTS_KEY,))
        row = cursor.fetchone()
        data = dict((row or {}).get("value") or {})
    finally:
        if own:
            cursor.close()
            ctx.__exit__(None, None, None)
    return {
        "enabled": bool(data.get("enabled", True)),
        "chat_id": str(data.get("chat_id") or ""),
        "registered_by": str(data.get("registered_by") or ""),
        "registered_at": str(data.get("registered_at") or ""),
        "last_daily": str(data.get("last_daily") or ""),
        "last_weekly": str(data.get("last_weekly") or ""),
        "last_monthly": str(data.get("last_monthly") or ""),
    }


def _store_report_settings(cur, data):
    cur.execute(
        """insert into app_settings(key,value,updated_at)
           values(%s,%s,now())
           on conflict(key) do update set value=excluded.value,updated_at=now()""",
        (REPORTS_KEY, app_v3.Jsonb(data)),
    )


def _register_report_chat(chat_id, sender_id):
    chat_id = str(chat_id)
    sender_id = str(sender_id or "")
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select value from app_settings where key=%s for update", (REPORTS_KEY,))
        row = cur.fetchone()
        stored = dict((row or {}).get("value") or {})
        existing = str(stored.get("chat_id") or "")
        if existing and existing != chat_id:
            return False, existing
        stored.update(
            {
                "enabled": True,
                "chat_id": chat_id,
                "registered_by": sender_id,
                "registered_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _store_report_settings(cur, stored)
    return True, chat_id


def _fa_int(value):
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{amount:,}".replace(",", "٬").translate(PERSIAN_DIGITS)


def _fa_date(d):
    jy, jm, jd = _gregorian_to_jalali(d.year, d.month, d.day)
    months = (
        "",
        "فروردین",
        "اردیبهشت",
        "خرداد",
        "تیر",
        "مرداد",
        "شهریور",
        "مهر",
        "آبان",
        "آذر",
        "دی",
        "بهمن",
        "اسفند",
    )
    return f"{_fa_int(jd)} {months[jm]} {_fa_int(jy)}"


def _normalize_sort(value):
    text = str(value or "").translate(ARABIC_TO_PERSIAN)
    text = re.sub(r"[\u200c\s]+", " ", text).strip()
    return text.casefold()


def _gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        + gd
        + g_d_m[gm - 1]
    )
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def _jalali_to_gregorian(jy, jm, jd):
    jy += 1595
    days = (
        -355668
        + (365 * jy)
        + ((jy // 33) * 8)
        + (((jy % 33) + 3) // 4)
        + jd
        + (31 * (jm - 1) if jm < 7 else (30 * (jm - 7)) + 186)
    )
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)
    month_days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    for length in month_days:
        if gd <= length:
            break
        gd -= length
        gm += 1
    return gy, gm, gd


def _month_start(local_now):
    jy, jm, _ = _gregorian_to_jalali(local_now.year, local_now.month, local_now.day)
    gy, gm, gd = _jalali_to_gregorian(jy, jm, 1)
    return datetime.combine(date(gy, gm, gd), time.min, tzinfo=TEHRAN)


def _is_jalali_month_end(local_now):
    tomorrow = (local_now + timedelta(days=1)).date()
    _, _, jd = _gregorian_to_jalali(tomorrow.year, tomorrow.month, tomorrow.day)
    return jd == 1


def _report_window(period, local_now):
    end = local_now
    if period == "daily":
        start = datetime.combine(local_now.date(), time.min, tzinfo=TEHRAN)
        key = local_now.date().isoformat()
        title = "گزارش پایان کار روزانه"
        label = _fa_date(local_now.date())
    elif period == "weekly":
        start_date = local_now.date() - timedelta(days=6)
        start = datetime.combine(start_date, time.min, tzinfo=TEHRAN)
        key = local_now.date().isoformat()
        title = "گزارش هفتگی"
        label = f"{_fa_date(start_date)} تا {_fa_date(local_now.date())}"
    elif period == "monthly":
        start = _month_start(local_now)
        jy, jm, _ = _gregorian_to_jalali(local_now.year, local_now.month, local_now.day)
        key = f"{jy:04d}-{jm:02d}"
        title = "گزارش ماهانه"
        label = f"{_fa_date(start.date())} تا {_fa_date(local_now.date())}"
    else:
        raise ValueError("invalid report period")
    return start, end, key, title, label


def _report_rows(start_local, end_local):
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """select
                   s.id,
                   coalesce(nullif(trim(c.last_name),''), nullif(trim(c.first_name),''), 'بدون نام') as customer_name,
                   coalesce(s.received_amount,0)::bigint as received_amount,
                   coalesce(s.company_share_amount,0)::bigint as company_share_amount,
                   coalesce(s.visited_at,s.created_at) as activity_at
               from service_visits s
               join customers_v2 c on c.id=s.customer_id
               where s.status='completed'
                 and coalesce(s.visited_at,s.created_at)>=%s
                 and coalesce(s.visited_at,s.created_at)<%s""",
            (start_utc, end_utc),
        )
        rows = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """select count(*)::int as count
               from bale_jobs
               where status='cancelled'
                 and cancelled_at>=%s
                 and cancelled_at<%s""",
            (start_utc, end_utc),
        )
        cancelled = int((cur.fetchone() or {}).get("count") or 0)
    rows.sort(key=lambda row: _normalize_sort(row.get("customer_name")))
    return rows, cancelled


def _format_report(period, local_now):
    start, end, key, title, label = _report_window(period, local_now)
    rows, cancelled = _report_rows(start, end)
    total_received = sum(int(row.get("received_amount") or 0) for row in rows)
    total_company = sum(int(row.get("company_share_amount") or 0) for row in rows)
    total_personal = total_received - total_company

    lines = [f"📊 {title} AquaGold", f"📅 {label}", ""]
    if rows:
        for index, row in enumerate(rows, 1):
            lines.append(
                f"{_fa_int(index)}. {row.get('customer_name') or 'بدون نام'} — "
                f"{_fa_int(row.get('received_amount'))} تومان"
            )
    else:
        lines.append("— امروز کار انجام‌شده‌ای ثبت نشده است.")

    lines.extend(
        [
            "",
            "━━━━━━━━━━",
            f"💰 کل دریافتی: {_fa_int(total_received)} تومان",
            f"🏢 سهم شرکت: {_fa_int(total_company)} تومان",
            f"👤 سهم شما: {_fa_int(total_personal)} تومان",
            "",
            f"✅ انجام‌شده: {_fa_int(len(rows))} کار",
            f"❌ کنسل‌شده: {_fa_int(cancelled)} کار",
        ]
    )
    return "\n".join(lines), key


def _send_to_management(text):
    reports = _load_report_settings()
    if not reports.get("enabled") or not reports.get("chat_id"):
        return False, "report_recipient_not_configured"
    bale = bale_bridge._load_settings()
    token = bale.get("bot_token")
    if not token:
        return False, "bale_token_not_configured"
    try:
        result = bale_bridge._bale_call(
            token,
            "sendMessage",
            {"chat_id": reports["chat_id"], "text": text},
            timeout=12,
        )
        return bool(result.get("ok", True)), None
    except Exception as exc:
        app_v3.logger.warning("bale_management_send_failed: %s", exc)
        return False, str(exc)


def _mark_sent(period, key):
    field = {"daily": "last_daily", "weekly": "last_weekly", "monthly": "last_monthly"}[period]
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select value from app_settings where key=%s for update", (REPORTS_KEY,))
        row = cur.fetchone()
        stored = dict((row or {}).get("value") or {})
        stored[field] = key
        _store_report_settings(cur, stored)


def _already_sent(period, key):
    field = {"daily": "last_daily", "weekly": "last_weekly", "monthly": "last_monthly"}[period]
    return _load_report_settings().get(field) == key


def send_report(period, local_now=None, force=False):
    local_now = local_now or datetime.now(TEHRAN)
    text, key = _format_report(period, local_now)
    if not force and _already_sent(period, key):
        return {"ok": True, "period": period, "skipped": "already_sent", "key": key}
    sent, error = _send_to_management(text)
    if not sent:
        return {"ok": False, "period": period, "error": error, "key": key}
    _mark_sent(period, key)
    return {"ok": True, "period": period, "sent": True, "key": key}


def _private_reports_command(secret):
    settings = bale_bridge._load_settings()
    expected = settings.get("webhook_secret") or ""
    if not expected or not hmac.compare_digest(str(secret), expected):
        return None

    update = request.get_json(silent=True) or {}
    message, text, chat, sender, _ = bale_bridge._message_payload(update)
    if not message or not text:
        return None

    command = str(text).strip().split()[0].lower()
    if command.split("@", 1)[0] != "/reports":
        return None

    chat_id = chat.get("id")
    sender_id = sender.get("id")
    chat_type = str(chat.get("type") or "").lower()
    if chat_id is None or (chat_type and chat_type != "private"):
        return jsonify({"ok": True, "ignored": "reports_private_only"})

    if sender_id is not None and str(sender_id) != str(chat_id):
        return jsonify({"ok": True, "ignored": "reports_sender_mismatch"})

    registered, existing = _register_report_chat(chat_id, sender_id)
    if not registered:
        bale_bridge._bale_call(
            settings.get("bot_token"),
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "🔒 گیرنده گزارش‌های مدیریتی قبلاً ثبت شده و از طریق این چت قابل تغییر نیست.",
            },
            timeout=8,
        )
        return jsonify({"ok": True, "registered": False, "locked": True})

    bale_bridge._bale_call(
        settings.get("bot_token"),
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": (
                "✅ گزارش‌های مدیریتی AquaGold برای این چت فعال شد.\n"
                "از این پس کنسلی‌ها فوری و گزارش پایان روز ساعت ۲۳:۰۰ به وقت ایران ارسال می‌شود."
            ),
        },
        timeout=8,
    )
    return jsonify({"ok": True, "reports_registered": True, "chat_id": str(existing)})


_original_bale_webhook = app_v3.app.view_functions.get("bale_webhook")


def _bale_webhook_with_reports(secret):
    handled = _private_reports_command(secret)
    if handled is not None:
        return handled
    return _original_bale_webhook(secret)


if _original_bale_webhook is not None:
    app_v3.app.view_functions["bale_webhook"] = _bale_webhook_with_reports


_original_bale_cancel = app_v3.app.view_functions.get("bale_job_cancel")


def _cancellation_details(job_id):
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """select b.id,
                      coalesce(nullif(trim(c.last_name),''), nullif(trim(b.customer_name),''), 'بدون نام') as customer_name,
                      coalesce(nullif(trim(b.job_type),''),'سرویس') as job_type,
                      coalesce(nullif(trim(b.cancel_reason),''),'بدون توضیح') as cancel_reason,
                      b.cancelled_at
               from bale_jobs b
               left join customers_v2 c on c.id=b.customer_id
               where b.id=%s::uuid""",
            (job_id,),
        )
        return cur.fetchone()


def _bale_job_cancel_with_management(job_id):
    response = app_v3.app.make_response(_original_bale_cancel(job_id))
    if response.status_code < 300 and response.headers.get("Idempotency-Replayed") != "true":
        try:
            row = _cancellation_details(job_id)
            if row:
                local_dt = row.get("cancelled_at")
                if local_dt:
                    local_dt = local_dt.astimezone(TEHRAN)
                    when = f"{_fa_date(local_dt.date())}، ساعت {_fa_int(local_dt.hour)}:{_fa_int(local_dt.minute).rjust(2, '۰')}"
                else:
                    when = "همین حالا"
                _send_to_management(
                    "\n".join(
                        [
                            "❌ لغو کار AquaGold",
                            f"👤 مشتری: {row.get('customer_name')}",
                            f"🔧 کار: {row.get('job_type')}",
                            f"📝 دلیل: {row.get('cancel_reason')}",
                            f"🕘 زمان: {when}",
                        ]
                    )
                )
        except Exception as exc:
            app_v3.logger.warning("bale_cancel_management_notification_failed: %s", exc)
    return response


if _original_bale_cancel is not None:
    app_v3.app.view_functions["bale_job_cancel"] = _bale_job_cancel_with_management


def _cron_authorized():
    secret = os.getenv("CRON_SECRET", "")
    if not secret:
        return False
    supplied = request.headers.get("Authorization", "")
    return hmac.compare_digest(supplied, f"Bearer {secret}")


@app_v3.app.get("/api/cron/bale-reports")
@app_v3.limiter.exempt
def bale_reports_cron():
    if not _cron_authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    local_now = datetime.now(TEHRAN)
    results = [send_report("daily", local_now)]

    # Iran's working week convention: weekly close on Friday night.
    if local_now.weekday() == 4:
        results.append(send_report("weekly", local_now))

    if _is_jalali_month_end(local_now):
        results.append(send_report("monthly", local_now))

    status = 200 if all(item.get("ok") for item in results) else 503
    return jsonify({"ok": status == 200, "local_time": local_now.isoformat(), "results": results}), status


@app_v3.app.post("/api/bale/reports/send")
@app_v3.roles_required("admin")
def bale_reports_manual_send():
    payload = request.get_json(silent=True) or {}
    period = str(payload.get("period") or "daily").strip().lower()
    if period not in {"daily", "weekly", "monthly"}:
        return jsonify({"error": "period must be daily, weekly or monthly"}), 400
    return jsonify(send_report(period, datetime.now(TEHRAN), force=True))


@app_v3.app.get("/api/bale/reports/settings")
@app_v3.roles_required("admin")
def bale_reports_settings():
    settings = _load_report_settings()
    return jsonify(
        {
            "enabled": settings["enabled"],
            "recipient_configured": bool(settings["chat_id"]),
            "chat_id_mask": f"••••{settings['chat_id'][-4:]}" if settings["chat_id"] else "",
            "last_daily": settings["last_daily"],
            "last_weekly": settings["last_weekly"],
            "last_monthly": settings["last_monthly"],
            "timezone": "Asia/Tehran",
            "daily_time": "23:00",
        }
    )
