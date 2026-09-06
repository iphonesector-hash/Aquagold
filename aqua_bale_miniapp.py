"""AquaGold Bale Mini App: isolated read-only reporting surface."""
from __future__ import annotations

import hashlib
import hmac
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import jsonify, make_response, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import app_v3
from aquagold_validation import ValidationError

TEHRAN = ZoneInfo("Asia/Tehran")
MINI_COOKIE = "aqua_bale_mini_session"
MINI_MAX_AGE = 7 * 24 * 3600
# SHA-256 of the private operator password. Keep the plaintext out of this public repo.
MINI_PASSWORD_SHA256 = "49cad93a2f1e02d113ffd7e1a2b1ae72807225d95d3be5074d90e3ee0a5a18cd"


def _serializer():
    return URLSafeTimedSerializer(str(app_v3.app.secret_key), salt="aqua-bale-mini-v1")


def _mini_authorized():
    token = request.cookies.get(MINI_COOKIE, "")
    if not token:
        return False
    try:
        payload = _serializer().loads(token, max_age=MINI_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return bool(isinstance(payload, dict) and payload.get("u") == "admin")


def mini_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not _mini_authorized():
            return jsonify({"error": "ورود به مینی‌اپ لازم است"}), 401
        return fn(*args, **kwargs)

    return wrapped


def _parse_day(raw):
    try:
        return date.fromisoformat(str(raw or ""))
    except ValueError as exc:
        raise ValidationError("تاریخ معتبر نیست") from exc


def _day_bounds(day):
    local_start = datetime.combine(day, datetime.min.time(), tzinfo=TEHRAN)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _json_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__float__") and not isinstance(value, (str, bytes, int, float, bool)):
        try:
            return float(value)
        except Exception:
            pass
    return value


def _row(row):
    return {k: _json_value(v) for k, v in dict(row).items()}


def _jalali_to_gregorian(jy, jm, jd):
    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += (jm - 7) * 30 + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        gy += 100 * ((days - 1) // 36524)
        days = (days - 1) % 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)
    sal = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > sal[gm]:
        gd -= sal[gm]
        gm += 1
    return date(gy, gm, gd)


def _gregorian_to_jalali(g):
    gy, gm, gd = g.year, g.month, g.day
    gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + gdm[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def _period_bounds(anchor, period):
    if period == "daily":
        return anchor, anchor + timedelta(days=1)
    if period == "weekly":
        # Iranian week: Saturday through Friday.
        start = anchor - timedelta(days=(anchor.weekday() - 5) % 7)
        return start, start + timedelta(days=7)
    if period == "monthly":
        jy, jm, _ = _gregorian_to_jalali(anchor)
        start = _jalali_to_gregorian(jy, jm, 1)
        if jm == 12:
            end = _jalali_to_gregorian(jy + 1, 1, 1)
        else:
            end = _jalali_to_gregorian(jy, jm + 1, 1)
        return start, end
    raise ValidationError("بازه گزارش معتبر نیست")


def _utc_bounds(start_day, end_day):
    start = datetime.combine(start_day, datetime.min.time(), tzinfo=TEHRAN).astimezone(timezone.utc)
    end = datetime.combine(end_day, datetime.min.time(), tzinfo=TEHRAN).astimezone(timezone.utc)
    return start, end


@app_v3.app.get("/bale-mini")
def aqua_bale_mini_page():
    return app_v3.app.send_static_file("aqua-bale-miniapp.html")


@app_v3.app.get("/api/mini/session")
def aqua_bale_mini_session():
    return jsonify({"authenticated": _mini_authorized(), "username": "admin" if _mini_authorized() else None})


@app_v3.app.post("/api/mini/login")
@app_v3.limiter.limit("10 per minute")
def aqua_bale_mini_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip().lower()
    password = str(data.get("password") or "")
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if username != "admin" or not hmac.compare_digest(digest, MINI_PASSWORD_SHA256):
        return jsonify({"error": "نام کاربری یا رمز عبور اشتباه است"}), 401
    token = _serializer().dumps({"u": "admin"})
    response = make_response(jsonify({"ok": True, "username": "admin"}))
    response.set_cookie(
        MINI_COOKIE,
        token,
        max_age=MINI_MAX_AGE,
        httponly=True,
        secure=app_v3.COOKIE_SECURE,
        samesite="Lax",
        path="/",
    )
    return response


@app_v3.app.post("/api/mini/logout")
def aqua_bale_mini_logout():
    response = make_response(jsonify({"ok": True}))
    response.delete_cookie(MINI_COOKIE, path="/")
    return response


@app_v3.app.get("/api/mini/day")
@mini_required
def aqua_bale_mini_day():
    day = _parse_day(request.args.get("date"))
    start, end = _day_bounds(day)
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select b.id,b.customer_name,b.phone,b.address,b.job_type,b.status,b.received_at,
                   b.completed_at,b.cancelled_at,b.cancel_reason,b.customer_id,b.service_visit_id,
                   coalesce(b.received_amount,s.received_amount,0)::bigint received_amount,
                   coalesce(s.company_share_amount,0)::bigint company_share_amount
              from bale_jobs b
              left join service_visits s on s.id=b.service_visit_id
             where b.received_at >= %s and b.received_at < %s
             order by b.received_at asc
            """,
            (start, end),
        )
        jobs = [_row(r) for r in cur.fetchall()]
    completed = sum(1 for x in jobs if x["status"] == "completed")
    cancelled = sum(1 for x in jobs if x["status"] == "cancelled")
    received = sum(int(x.get("received_amount") or 0) for x in jobs if x["status"] == "completed")
    company = sum(int(x.get("company_share_amount") or 0) for x in jobs if x["status"] == "completed")
    return jsonify({
        "date": day.isoformat(),
        "jobs": jobs,
        "summary": {
            "total": len(jobs),
            "completed": completed,
            "cancelled": cancelled,
            "received": received,
            "company_share": company,
        },
    })


@app_v3.app.get("/api/mini/customers")
@mini_required
def aqua_bale_mini_customers():
    q = str(request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"%{q}%"
    phone_like = f"%{app_v3.normalize_phone(q)}%" if any(ch.isdigit() for ch in q.translate(app_v3.DIGIT_TRANS)) else "%__never__%"
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select c.id,c.first_name,c.last_name,c.address,c.plaque,c.unit_no,c.device_model,c.notes,c.created_at,
                   coalesce((select json_agg(p.phone order by p.is_primary desc,p.id) from customer_phones p where p.customer_id=c.id),'[]'::json) phones,
                   (select count(*)::int from service_visits s where s.customer_id=c.id) total_services,
                   (select count(*)::int from service_visits s where s.customer_id=c.id and s.status='completed') completed_services,
                   (select count(*)::int from bale_jobs b where b.customer_id=c.id and b.status='cancelled') cancelled_services,
                   coalesce((select sum(s.received_amount)::bigint from service_visits s where s.customer_id=c.id and s.status='completed'),0) total_received,
                   (select max(coalesce(s.visited_at,s.created_at)) from service_visits s where s.customer_id=c.id) last_service_at
              from customers_v2 c
             where not c.archived
               and (
                    concat_ws(' ',c.first_name,c.last_name) ilike %s
                    or coalesce(c.address,'') ilike %s
                    or exists(select 1 from customer_phones p where p.customer_id=c.id and p.phone like %s)
               )
             order by c.updated_at desc
             limit 20
            """,
            (like, like, phone_like),
        )
        rows = [_row(r) for r in cur.fetchall()]
    return jsonify(rows)


@app_v3.app.get("/api/mini/customers/<customer_id>")
@mini_required
def aqua_bale_mini_customer_detail(customer_id):
    customer_id = app_v3.valid_uuid(customer_id, "شناسه مشتری")
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """select c.id,c.first_name,c.last_name,c.address,c.plaque,c.unit_no,c.device_model,c.notes,c.created_at,
                      coalesce((select json_agg(p.phone order by p.is_primary desc,p.id) from customer_phones p where p.customer_id=c.id),'[]'::json) phones
                 from customers_v2 c where c.id=%s::uuid""",
            (str(customer_id),),
        )
        customer = cur.fetchone()
        if not customer:
            return jsonify({"error": "مشتری پیدا نشد"}), 404
        cur.execute(
            """select id,service_type,description,status,payment_method,invoice_amount,received_amount,company_share_amount,
                      scheduled_from,scheduled_until,visited_at,created_at
                 from service_visits where customer_id=%s::uuid
                 order by coalesce(visited_at,created_at) desc limit 100""",
            (str(customer_id),),
        )
        visits = [_row(r) for r in cur.fetchall()]
        cur.execute(
            """select id,job_type,status,received_amount,cancel_reason,received_at,completed_at,cancelled_at
                 from bale_jobs where customer_id=%s::uuid and (service_visit_id is null or status='cancelled')
                 order by received_at desc limit 100""",
            (str(customer_id),),
        )
        bale_jobs = [_row(r) for r in cur.fetchall()]
    return jsonify({"customer": _row(customer), "visits": visits, "bale_jobs": bale_jobs})


@app_v3.app.get("/api/mini/finance")
@mini_required
def aqua_bale_mini_finance():
    period = str(request.args.get("period") or "daily").strip().lower()
    anchor = _parse_day(request.args.get("date"))
    start_day, end_day = _period_bounds(anchor, period)
    start, end = _utc_bounds(start_day, end_day)

    chart_start_day = start_day
    if period == "daily":
        chart_start_day = start_day - timedelta(days=6)
    chart_start, chart_end = _utc_bounds(chart_start_day, end_day)

    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """select count(*)::int service_count,
                      coalesce(sum(invoice_amount),0)::bigint invoice_total,
                      coalesce(sum(received_amount),0)::bigint received_total,
                      coalesce(sum(company_share_amount),0)::bigint company_share
                 from service_visits
                where status='completed' and coalesce(visited_at,created_at)>=%s and coalesce(visited_at,created_at)<%s""",
            (start, end),
        )
        summary = _row(cur.fetchone())
        cur.execute(
            """select coalesce(sum(amount),0)::bigint settled_total
                 from company_settlements where settled_at>=%s and settled_at<%s""",
            (start, end),
        )
        summary.update(_row(cur.fetchone()))
        summary["payable"] = max(int(summary.get("company_share") or 0) - int(summary.get("settled_total") or 0), 0)
        cur.execute(
            """select (timezone('Asia/Tehran',coalesce(visited_at,created_at)))::date day,
                      coalesce(sum(received_amount),0)::bigint received,
                      coalesce(sum(company_share_amount),0)::bigint company_share,
                      count(*)::int count
                 from service_visits
                where status='completed' and coalesce(visited_at,created_at)>=%s and coalesce(visited_at,created_at)<%s
                group by 1 order by 1""",
            (chart_start, chart_end),
        )
        chart = []
        for r in cur.fetchall():
            item = _row(r)
            if isinstance(r["day"], date):
                item["day"] = r["day"].isoformat()
            chart.append(item)
    return jsonify({
        "period": period,
        "anchor": anchor.isoformat(),
        "from": start_day.isoformat(),
        "to": (end_day - timedelta(days=1)).isoformat(),
        "summary": summary,
        "chart": chart,
    })
