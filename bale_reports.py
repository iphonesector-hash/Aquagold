"""Bale management alerts and scheduled AquaGold reports."""

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
CRON_SCHEDULE = "30 19 * * *"
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
FA_CHARS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})


def _settings(cur=None):
    own = cur is None
    ctx = app_v3.get_db() if own else None
    db = ctx.__enter__() if own else None
    cursor = db.cursor() if own else cur
    try:
        cursor.execute("select value from app_settings where key=%s", (REPORTS_KEY,))
        row = cursor.fetchone()
        raw = dict((row or {}).get("value") or {})
    finally:
        if own:
            cursor.close()
            ctx.__exit__(None, None, None)
    return raw


def _save_settings(cur, raw):
    cur.execute(
        """insert into app_settings(key,value,updated_at) values(%s,%s,now())
           on conflict(key) do update set value=excluded.value,updated_at=now()""",
        (REPORTS_KEY, app_v3.Jsonb(raw)),
    )


def _register_private_chat(chat_id, sender_id):
    chat_id = str(chat_id)
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select value from app_settings where key=%s for update", (REPORTS_KEY,))
        row = cur.fetchone()
        raw = dict((row or {}).get("value") or {})
        existing = str(raw.get("chat_id") or "")
        if existing and existing != chat_id:
            return False
        raw.update(
            enabled=True,
            chat_id=chat_id,
            registered_by=str(sender_id or ""),
            registered_at=datetime.now(timezone.utc).isoformat(),
        )
        _save_settings(cur, raw)
    return True


def _fa_number(value):
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        number = 0
    return f"{number:,}".replace(",", "٬").translate(FA_DIGITS)


def _sort_key(value):
    return re.sub(r"[\u200c\s]+", " ", str(value or "").translate(FA_CHARS)).strip().casefold()


def _g2j(gy, gm, gd):
    month_days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + month_days[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def _j2g(jy, jm, jd):
    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
    days += 31 * (jm - 1) if jm < 7 else 186 + 30 * (jm - 7)
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
    lengths = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    for length in lengths:
        if gd <= length:
            break
        gd -= length
        gm += 1
    return gy, gm, gd


def _fa_date(value):
    jy, jm, jd = _g2j(value.year, value.month, value.day)
    months = ("", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
    return f"{str(jd).translate(FA_DIGITS)} {months[jm]} {str(jy).translate(FA_DIGITS)}"


def _month_start(local_now):
    jy, jm, _ = _g2j(local_now.year, local_now.month, local_now.day)
    gy, gm, gd = _j2g(jy, jm, 1)
    return datetime.combine(date(gy, gm, gd), time.min, tzinfo=TEHRAN)


def _jalali_month_end(local_now):
    tomorrow = (local_now + timedelta(days=1)).date()
    return _g2j(tomorrow.year, tomorrow.month, tomorrow.day)[2] == 1


def _window(period, local_now):
    if period == "daily":
        start = datetime.combine(local_now.date(), time.min, tzinfo=TEHRAN)
        return start, local_now, local_now.date().isoformat(), "گزارش پایان کار روزانه", _fa_date(local_now.date())
    if period == "weekly":
        start_date = local_now.date() - timedelta(days=6)
        start = datetime.combine(start_date, time.min, tzinfo=TEHRAN)
        return start, local_now, local_now.date().isoformat(), "گزارش هفتگی", f"{_fa_date(start_date)} تا {_fa_date(local_now.date())}"
    if period == "monthly":
        start = _month_start(local_now)
        jy, jm, _ = _g2j(local_now.year, local_now.month, local_now.day)
        return start, local_now, f"{jy:04d}-{jm:02d}", "گزارش ماهانه", f"{_fa_date(start.date())} تا {_fa_date(local_now.date())}"
    raise ValueError("invalid report period")


def _fetch_report(start_local, end_local):
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """select coalesce(nullif(trim(c.last_name),''),nullif(trim(c.first_name),''),'بدون نام') customer_name,
                      coalesce(s.received_amount,0)::bigint received_amount,
                      coalesce(s.company_share_amount,0)::bigint company_share_amount
               from service_visits s join customers_v2 c on c.id=s.customer_id
               where s.status not in ('cancelled','scheduled')
                 and coalesce(s.visited_at,s.created_at)>=%s
                 and coalesce(s.visited_at,s.created_at)<%s""",
            (start_utc, end_utc),
        )
        rows = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """select count(*)::int count from bale_jobs
               where status='cancelled' and cancelled_at>=%s and cancelled_at<%s""",
            (start_utc, end_utc),
        )
        cancelled = int((cur.fetchone() or {}).get("count") or 0)
    rows.sort(key=lambda row: _sort_key(row.get("customer_name")))
    return rows, cancelled


def _format_report(period, local_now):
    start, end, key, title, label = _window(period, local_now)
    rows, cancelled = _fetch_report(start, end)
    received = sum(int(row.get("received_amount") or 0) for row in rows)
    company = sum(int(row.get("company_share_amount") or 0) for row in rows)

    lines = [f"📊 {title} AquaGold", f"📅 {label}", ""]
    if rows:
        for index, row in enumerate(rows, 1):
            lines.append(f"{_fa_number(index)}. {row['customer_name']} — {_fa_number(row['received_amount'])} تومان")
    else:
        lines.append("— کار انجام‌شده‌ای در این بازه ثبت نشده است.")

    lines += [
        "",
        "━━━━━━━━━━",
        f"💰 کل دریافتی: {_fa_number(received)} تومان",
        f"🏢 سهم شرکت: {_fa_number(company)} تومان",
        f"👤 سهم شما: {_fa_number(received - company)} تومان",
        "",
        f"✅ انجام‌شده: {_fa_number(len(rows))} کار",
        f"❌ کنسل‌شده: {_fa_number(cancelled)} کار",
    ]
    return "\n".join(lines), key


def _management_destinations():
    """Return private report chat plus the same Bale work group(s)."""
    report_settings = _settings()
    destinations = []
    private_chat = str(report_settings.get("chat_id") or "").strip()
    if private_chat:
        destinations.append(private_chat)

    bot = bale_bridge._load_settings()
    configured_groups = [str(x).strip() for x in (bot.get("allowed_chat_ids") or []) if str(x).strip()]
    if configured_groups:
        destinations.extend(configured_groups)
    else:
        try:
            with app_v3.get_db() as db, db.cursor() as cur:
                cur.execute(
                    """select chat_id from bale_jobs
                       where chat_id is not null and coalesce(chat_title,'')<>''
                       order by received_at desc limit 1"""
                )
                row = cur.fetchone()
                if row and row.get("chat_id") is not None:
                    destinations.append(str(row["chat_id"]))
        except Exception as exc:
            app_v3.logger.warning("bale_report_group_lookup_failed: %s", exc)

    seen = set()
    return [chat_id for chat_id in destinations if chat_id and not (chat_id in seen or seen.add(chat_id))]


def _send_management(text):
    report_settings = _settings()
    if not report_settings.get("enabled", True):
        return False, "reports_disabled"
    bot = bale_bridge._load_settings()
    if not bot.get("bot_token"):
        return False, "bale_token_not_configured"

    destinations = _management_destinations()
    if not destinations:
        return False, "report_recipient_not_configured"

    delivered = 0
    errors = []
    for chat_id in destinations:
        try:
            result = bale_bridge._bale_call(
                bot["bot_token"],
                "sendMessage",
                {"chat_id": chat_id, "text": text},
                timeout=12,
            )
            if bool(result.get("ok", True)):
                delivered += 1
            else:
                errors.append(f"{chat_id}: not_ok")
        except Exception as exc:
            errors.append(f"{chat_id}: {exc}")
            app_v3.logger.warning("bale_management_send_failed chat=%s: %s", chat_id, exc)

    if delivered:
        return True, "; ".join(errors) if errors else None
    return False, "; ".join(errors) or "delivery_failed"


def _last_key(period):
    return f"last_{period}"


def send_report(period, local_now=None, force=False):
    local_now = local_now or datetime.now(TEHRAN)
    text, key = _format_report(period, local_now)
    if not force and str(_settings().get(_last_key(period)) or "") == key:
        return {"ok": True, "period": period, "skipped": "already_sent", "key": key}
    sent, error = _send_management(text)
    if not sent:
        return {"ok": False, "period": period, "error": error, "key": key}
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select value from app_settings where key=%s for update", (REPORTS_KEY,))
        row = cur.fetchone()
        raw = dict((row or {}).get("value") or {})
        raw[_last_key(period)] = key
        _save_settings(cur, raw)
    return {"ok": True, "period": period, "sent": True, "key": key, "warning": error}


def _handle_reports_command(secret):
    bot = bale_bridge._load_settings()
    expected = str(bot.get("webhook_secret") or "")
    if not expected or not hmac.compare_digest(str(secret), expected):
        return None

    update = request.get_json(silent=True) or {}
    message, text, chat, sender, _ = bale_bridge._message_payload(update)
    if not message or not text:
        return None
    command = str(text).strip().split()[0].lower().split("@", 1)[0]
    if command != "/reports":
        return None

    chat_id = chat.get("id")
    sender_id = sender.get("id")
    chat_type = str(chat.get("type") or "").lower()
    if chat_id is None or (chat_type and chat_type != "private") or (sender_id is not None and str(sender_id) != str(chat_id)):
        return jsonify({"ok": True, "ignored": "reports_private_only"})

    registered = _register_private_chat(chat_id, sender_id)
    text = (
        "✅ گزارش‌های مدیریتی AquaGold برای این چت فعال شد.\n"
        "کنسلی‌ها فوری و گزارش‌های روزانه، هفتگی و ماهانه هم به این چت و هم گروه کاری بله ارسال می‌شوند."
        if registered
        else "🔒 گیرنده گزارش‌های مدیریتی قبلاً ثبت شده و از طریق این چت قابل تغییر نیست."
    )
    bale_bridge._bale_call(bot.get("bot_token"), "sendMessage", {"chat_id": chat_id, "text": text}, timeout=8)
    return jsonify({"ok": True, "reports_registered": registered})


_original_webhook = app_v3.app.view_functions.get("bale_webhook")


def _webhook_with_reports(secret):
    handled = _handle_reports_command(secret)
    return handled if handled is not None else _original_webhook(secret)


if _original_webhook is not None:
    app_v3.app.view_functions["bale_webhook"] = _webhook_with_reports


_original_cancel = app_v3.app.view_functions.get("bale_job_cancel")


def _cancel_details(job_id):
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """select coalesce(nullif(trim(c.last_name),''),nullif(trim(b.customer_name),''),'بدون نام') customer_name,
                      coalesce(nullif(trim(b.job_type),''),'سرویس') job_type,
                      coalesce(nullif(trim(b.cancel_reason),''),'بدون توضیح') cancel_reason,
                      b.cancelled_at
               from bale_jobs b left join customers_v2 c on c.id=b.customer_id
               where b.id=%s::uuid""",
            (job_id,),
        )
        return cur.fetchone()


def _cancel_with_management(job_id):
    response = app_v3.app.make_response(_original_cancel(job_id))
    if response.status_code < 300 and response.headers.get("Idempotency-Replayed") != "true":
        try:
            row = _cancel_details(job_id)
            if row:
                stamp = row.get("cancelled_at")
                if stamp:
                    stamp = stamp.astimezone(TEHRAN)
                    hour = str(stamp.hour).translate(FA_DIGITS)
                    minute = str(stamp.minute).zfill(2).translate(FA_DIGITS)
                    when = f"{_fa_date(stamp.date())}، ساعت {hour}:{minute}"
                else:
                    when = "همین حالا"
                _send_management(
                    "\n".join(
                        [
                            "❌ لغو کار AquaGold",
                            f"👤 مشتری: {row['customer_name']}",
                            f"🔧 کار: {row['job_type']}",
                            f"📝 دلیل: {row['cancel_reason']}",
                            f"🕘 زمان: {when}",
                        ]
                    )
                )
        except Exception as exc:
            app_v3.logger.warning("bale_cancel_management_notification_failed: %s", exc)
    return response


if _original_cancel is not None:
    app_v3.app.view_functions["bale_job_cancel"] = _cancel_with_management


def _cron_authorized():
    secret = os.getenv("CRON_SECRET", "")
    supplied = request.headers.get("Authorization", "")
    if secret:
        return hmac.compare_digest(supplied, f"Bearer {secret}")
    now = datetime.now(TEHRAN)
    return (
        os.getenv("VERCEL") == "1"
        and request.headers.get("x-vercel-cron-schedule", "") == CRON_SCHEDULE
        and now.hour == 23
    )


@app_v3.app.get("/api/cron/bale-reports")
@app_v3.limiter.exempt
def bale_reports_cron():
    if not _cron_authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    local_now = datetime.now(TEHRAN)
    results = [send_report("daily", local_now)]
    if local_now.weekday() == 4:
        results.append(send_report("weekly", local_now))
    if _jalali_month_end(local_now):
        results.append(send_report("monthly", local_now))
    ok = all(item.get("ok") for item in results)
    return jsonify({"ok": ok, "local_time": local_now.isoformat(), "results": results}), (200 if ok else 503)


@app_v3.app.post("/api/bale/reports/send")
@app_v3.roles_required("admin")
def bale_reports_manual_send():
    period = str((request.get_json(silent=True) or {}).get("period") or "daily").lower()
    if period not in {"daily", "weekly", "monthly"}:
        return jsonify({"error": "period must be daily, weekly or monthly"}), 400
    return jsonify(send_report(period, datetime.now(TEHRAN), force=True))


@app_v3.app.get("/api/bale/reports/settings")
@app_v3.roles_required("admin")
def bale_reports_settings():
    raw = _settings()
    chat_id = str(raw.get("chat_id") or "")
    destinations = _management_destinations()
    return jsonify(
        {
            "enabled": bool(raw.get("enabled", True)),
            "recipient_configured": bool(chat_id),
            "chat_id_mask": f"••••{chat_id[-4:]}" if chat_id else "",
            "destination_count": len(destinations),
            "last_daily": str(raw.get("last_daily") or ""),
            "last_weekly": str(raw.get("last_weekly") or ""),
            "last_monthly": str(raw.get("last_monthly") or ""),
            "timezone": "Asia/Tehran",
            "daily_time": "23:00",
        }
    )