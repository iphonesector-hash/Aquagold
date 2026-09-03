"""Read-only API surface for the Aqua Aria custom GPT.

This module is intentionally isolated from the browser cookie/CSRF session flow.
It accepts only GET requests and authenticates with a dedicated bearer secret
stored in AQUAGOLD_GPT_ACTIONS_KEY.
"""
from __future__ import annotations

import hmac
import os
from datetime import date, datetime, time, timedelta, timezone
from functools import wraps
from zoneinfo import ZoneInfo

from flask import jsonify, request

import app_v3

TEHRAN = ZoneInfo("Asia/Tehran")
ACTION_KEY_ENV = "AQUAGOLD_GPT_ACTIONS_KEY"
DEFAULT_RATE_LIMIT = os.getenv("AQUAGOLD_GPT_ACTIONS_RATE_LIMIT", "60 per minute")
PAYMENT_LABELS = {
    "cash": "نقدی",
    "card": "کارتخوان",
    "transfer": "کارت به کارت",
    "cheque": "چک",
    "credit": "اعتباری",
    "other": "سایر",
    None: "ثبت نشده",
}


def _error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def _configured_key():
    return (os.getenv(ACTION_KEY_ENV) or "").strip()


def gpt_action_required(fn):
    """Require a dedicated high-entropy Bearer token and fail closed if unset."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        expected = _configured_key()
        if len(expected) < 32:
            app_v3.logger.error("gpt_actions_key_not_configured")
            return _error("Aqua Aria Actions are not configured", 503)

        header = request.headers.get("Authorization", "")
        supplied = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if not supplied or not hmac.compare_digest(supplied, expected):
            return _error("Unauthorized", 401)

        return fn(*args, **kwargs)

    return wrapper


def _limit(raw, default=20, maximum=50):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


def _parse_iso_date(raw, label):
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError as exc:
        raise ValueError(f"{label} باید به شکل YYYY-MM-DD باشد") from exc


def _day_window(raw=None):
    chosen = _parse_iso_date(raw, "تاریخ") or datetime.now(TEHRAN).date()
    start_local = datetime.combine(chosen, time.min, tzinfo=TEHRAN)
    end_local = start_local + timedelta(days=1)
    return chosen, start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _range_window(raw_from=None, raw_to=None):
    from_day = _parse_iso_date(raw_from, "از تاریخ")
    to_day = _parse_iso_date(raw_to, "تا تاریخ")

    if from_day is None and to_day is None:
        from_day = to_day = datetime.now(TEHRAN).date()
    elif from_day is None:
        from_day = to_day
    elif to_day is None:
        to_day = from_day

    if to_day < from_day:
        raise ValueError("تا تاریخ نمی‌تواند قبل از از تاریخ باشد")
    if (to_day - from_day).days > 366:
        raise ValueError("بازه گزارش حداکثر ۳۶۶ روز است")

    start_local = datetime.combine(from_day, time.min, tzinfo=TEHRAN)
    end_local = datetime.combine(to_day + timedelta(days=1), time.min, tzinfo=TEHRAN)
    return (
        from_day,
        to_day,
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


def _rows(rows):
    return [app_v3.row_json(row) for row in rows]


@app_v3.app.get("/api/gpt/health")
@app_v3.limiter.limit(DEFAULT_RATE_LIMIT)
@gpt_action_required
def gpt_health():
    """Safe health check for the custom GPT. Does not expose provider secrets."""

    try:
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("select 1")
            cur.fetchone()
        database = "healthy"
        status = 200
    except Exception:
        app_v3.logger.exception("gpt_actions_health_db_failed")
        database = "unavailable"
        status = 503

    return (
        jsonify(
            {
                "ok": status == 200,
                "service": "AquaGold Aqua Aria Actions",
                "mode": "read_only",
                "database": database,
                "timezone": "Asia/Tehran",
            }
        ),
        status,
    )


@app_v3.app.get("/api/gpt/customers/search")
@app_v3.limiter.limit(DEFAULT_RATE_LIMIT)
@gpt_action_required
def gpt_search_customers():
    q = str(request.args.get("q") or "").strip()
    if len(q) < 2 or len(q) > 160:
        return _error("برای جست‌وجوی مشتری حداقل ۲ و حداکثر ۱۶۰ نویسه وارد کنید")

    limit = _limit(request.args.get("limit"), default=10, maximum=20)
    normalized_phone = app_v3.normalize_phone(q)
    phone_term = normalized_phone if normalized_phone.startswith("09") else q

    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select
                c.id,c.first_name,c.last_name,c.address,c.map_label,c.unit_no,c.plaque,c.device_model,
                c.created_at,c.updated_at,
                case when c.location is null then null else st_y(c.location::geometry) end latitude,
                case when c.location is null then null else st_x(c.location::geometry) end longitude,
                coalesce((
                    select array_agg(p.phone order by p.is_primary desc,p.id)
                    from customer_phones p where p.customer_id=c.id
                ), '{}') phones,
                (select count(*)::int from service_visits s where s.customer_id=c.id) service_count,
                (
                    select jsonb_build_object(
                        'id',s.id,
                        'service_type',s.service_type,
                        'status',s.status,
                        'received_amount',s.received_amount,
                        'visited_at',s.visited_at,
                        'created_at',s.created_at
                    )
                    from service_visits s
                    where s.customer_id=c.id
                    order by coalesce(s.visited_at,s.created_at) desc
                    limit 1
                ) latest_service
            from customers_v2 c
            where c.archived=false
              and (
                    c.normalized_name ilike '%%'||%s||'%%'
                    or coalesce(c.address,'') ilike '%%'||%s||'%%'
                    or coalesce(c.map_label,'') ilike '%%'||%s||'%%'
                    or exists (
                        select 1 from customer_phones p
                        where p.customer_id=c.id and p.phone ilike '%%'||%s||'%%'
                    )
              )
            order by c.updated_at desc,c.created_at desc
            limit %s
            """,
            (q, q, q, phone_term, limit),
        )
        rows = cur.fetchall()

    return jsonify({"ok": True, "query": q, "count": len(rows), "customers": _rows(rows)})


@app_v3.app.get("/api/gpt/customers/<uuid:customer_id>")
@app_v3.limiter.limit(DEFAULT_RATE_LIMIT)
@gpt_action_required
def gpt_customer(customer_id):
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select
                c.*,
                case when c.location is null then null else st_y(c.location::geometry) end latitude,
                case when c.location is null then null else st_x(c.location::geometry) end longitude,
                coalesce((
                    select array_agg(p.phone order by p.is_primary desc,p.id)
                    from customer_phones p where p.customer_id=c.id
                ), '{}') phones,
                (select count(*)::int from service_visits s where s.customer_id=c.id) service_count,
                (select coalesce(sum(s.received_amount),0)::bigint from service_visits s where s.customer_id=c.id and s.status<>'cancelled') total_received,
                (select coalesce(sum(s.customer_balance),0)::bigint from service_visits s where s.customer_id=c.id and s.status<>'cancelled') total_balance,
                (
                    select jsonb_build_object(
                        'id',s.id,
                        'service_type',s.service_type,
                        'description',s.description,
                        'status',s.status,
                        'invoice_amount',s.invoice_amount,
                        'received_amount',s.received_amount,
                        'payment_method',s.payment_method,
                        'next_service_at',s.next_service_at,
                        'visited_at',s.visited_at,
                        'created_at',s.created_at
                    )
                    from service_visits s
                    where s.customer_id=c.id
                    order by coalesce(s.visited_at,s.created_at) desc
                    limit 1
                ) latest_service
            from customers_v2 c
            where c.id=%s
            """,
            (customer_id,),
        )
        row = cur.fetchone()

    if not row:
        return _error("مشتری پیدا نشد", 404)
    return jsonify({"ok": True, "customer": app_v3.row_json(row)})


@app_v3.app.get("/api/gpt/customers/<uuid:customer_id>/history")
@app_v3.limiter.limit(DEFAULT_RATE_LIMIT)
@gpt_action_required
def gpt_customer_history(customer_id):
    limit = _limit(request.args.get("limit"), default=20, maximum=50)

    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select 1 from customers_v2 where id=%s", (customer_id,))
        if not cur.fetchone():
            return _error("مشتری پیدا نشد", 404)

        cur.execute(
            """
            select
                s.id,s.service_type,s.description,s.amount,s.invoice_amount,s.received_amount,
                s.company_share_percent,s.company_share_amount,s.customer_balance,s.overpayment_amount,
                s.payment_method,s.status,s.scheduled_from,s.scheduled_until,s.visited_at,
                s.next_service_at,s.created_at,s.updated_at,
                coalesce((
                    select jsonb_agg(jsonb_build_object(
                        'item_name',x.item_name,'quantity',x.quantity,'unit_price',x.unit_price,'notes',x.notes
                    ) order by x.id)
                    from service_items x where x.service_visit_id=s.id
                ), '[]'::jsonb) items
            from service_visits s
            where s.customer_id=%s
            order by coalesce(s.visited_at,s.created_at) desc
            limit %s
            """,
            (customer_id, limit),
        )
        visits = cur.fetchall()

    return jsonify(
        {
            "ok": True,
            "customer_id": str(customer_id),
            "count": len(visits),
            "visits": _rows(visits),
        }
    )


@app_v3.app.get("/api/gpt/daily-jobs")
@app_v3.limiter.limit(DEFAULT_RATE_LIMIT)
@gpt_action_required
def gpt_daily_jobs():
    try:
        chosen, start_utc, end_utc = _day_window(request.args.get("date"))
    except ValueError as exc:
        return _error(str(exc))

    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select
                s.id,s.customer_id,
                trim(concat_ws(' ',c.first_name,c.last_name)) customer_name,
                coalesce((select p.phone from customer_phones p where p.customer_id=c.id order by p.is_primary desc,p.id limit 1),'') phone,
                c.address,s.service_type,s.description,s.status,s.invoice_amount,s.received_amount,
                s.payment_method,s.scheduled_from,s.scheduled_until,s.visited_at,s.next_service_at,s.created_at
            from service_visits s
            join customers_v2 c on c.id=s.customer_id
            where coalesce(s.visited_at,s.scheduled_from,s.created_at)>=%s
              and coalesce(s.visited_at,s.scheduled_from,s.created_at)<%s
            order by coalesce(s.scheduled_from,s.visited_at,s.created_at)
            """,
            (start_utc, end_utc),
        )
        services = cur.fetchall()

        cur.execute(
            """
            select
                b.id,b.customer_id,b.service_visit_id,b.customer_name,b.phone,b.address,b.job_type,
                b.status,b.received_amount,b.cancel_reason,b.received_at,b.completed_at,b.cancelled_at,b.updated_at
            from bale_jobs b
            where coalesce(b.completed_at,b.cancelled_at,b.received_at)>=%s
              and coalesce(b.completed_at,b.cancelled_at,b.received_at)<%s
            order by coalesce(b.completed_at,b.cancelled_at,b.received_at)
            """,
            (start_utc, end_utc),
        )
        bale_jobs = cur.fetchall()

    return jsonify(
        {
            "ok": True,
            "date": chosen.isoformat(),
            "timezone": "Asia/Tehran",
            "service_visits": _rows(services),
            "bale_jobs": _rows(bale_jobs),
        }
    )


@app_v3.app.get("/api/gpt/daily-report")
@app_v3.limiter.limit(DEFAULT_RATE_LIMIT)
@gpt_action_required
def gpt_daily_report():
    try:
        chosen, start_utc, end_utc = _day_window(request.args.get("date"))
    except ValueError as exc:
        return _error(str(exc))

    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select
                s.id,
                coalesce(nullif(trim(c.last_name),''),nullif(trim(c.first_name),''),'بدون نام') customer_name,
                coalesce(s.received_amount,0)::bigint amount,
                s.service_type,
                coalesce(s.visited_at,s.created_at) occurred_at
            from service_visits s
            join customers_v2 c on c.id=s.customer_id
            where s.status not in ('cancelled','scheduled')
              and coalesce(s.visited_at,s.created_at)>=%s
              and coalesce(s.visited_at,s.created_at)<%s
            order by coalesce(s.visited_at,s.created_at)
            """,
            (start_utc, end_utc),
        )
        completed = cur.fetchall()

        cur.execute(
            """
            select
                b.id,b.service_visit_id,
                coalesce(nullif(trim(b.customer_name),''),'بدون نام') customer_name,
                coalesce(nullif(trim(b.cancel_reason),''),'بدون علت ثبت‌شده') cancel_reason,
                coalesce(b.cancelled_at,b.updated_at) occurred_at
            from bale_jobs b
            where b.status='cancelled'
              and coalesce(b.cancelled_at,b.updated_at)>=%s
              and coalesce(b.cancelled_at,b.updated_at)<%s
            order by coalesce(b.cancelled_at,b.updated_at)
            """,
            (start_utc, end_utc),
        )
        cancelled = cur.fetchall()

        cur.execute(
            """
            select
                coalesce(sum(s.received_amount),0)::bigint received,
                coalesce(sum(s.company_share_amount),0)::bigint company_share
            from service_visits s
            where s.status not in ('cancelled','scheduled')
              and coalesce(s.visited_at,s.created_at)>=%s
              and coalesce(s.visited_at,s.created_at)<%s
            """,
            (start_utc, end_utc),
        )
        money = dict(cur.fetchone() or {})

    received = int(money.get("received") or 0)
    company_share = int(money.get("company_share") or 0)
    return jsonify(
        {
            "ok": True,
            "date": chosen.isoformat(),
            "timezone": "Asia/Tehran",
            "completed": _rows(completed),
            "cancelled": _rows(cancelled),
            "summary": {
                "completed_count": len(completed),
                "cancelled_count": len(cancelled),
                "received": received,
                "company_share": company_share,
                "user_share": received - company_share,
            },
        }
    )


@app_v3.app.get("/api/gpt/finance/summary")
@app_v3.limiter.limit(DEFAULT_RATE_LIMIT)
@gpt_action_required
def gpt_finance_summary():
    try:
        from_day, to_day, start_utc, end_utc = _range_window(
            request.args.get("from"), request.args.get("to")
        )
    except ValueError as exc:
        return _error(str(exc))

    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select
                count(*)::int services,
                coalesce(sum(invoice_amount),0)::bigint invoiced,
                coalesce(sum(received_amount),0)::bigint received,
                coalesce(sum(company_share_amount),0)::bigint company_share,
                coalesce(sum(customer_balance),0)::bigint customer_balance,
                coalesce(sum(overpayment_amount),0)::bigint overpayment
            from service_visits
            where status not in ('cancelled','scheduled')
              and coalesce(visited_at,created_at)>=%s
              and coalesce(visited_at,created_at)<%s
            """,
            (start_utc, end_utc),
        )
        total = dict(cur.fetchone() or {})

        cur.execute(
            """
            select payment_method,count(*)::int services,coalesce(sum(received_amount),0)::bigint amount
            from service_visits
            where status not in ('cancelled','scheduled')
              and coalesce(visited_at,created_at)>=%s
              and coalesce(visited_at,created_at)<%s
            group by payment_method
            order by amount desc
            """,
            (start_utc, end_utc),
        )
        payment_rows = cur.fetchall()

        cur.execute(
            "select coalesce(sum(amount),0)::bigint amount,count(*)::int count from expenses where expense_date>=%s and expense_date<%s",
            (start_utc, end_utc),
        )
        expense = dict(cur.fetchone() or {})

        cur.execute(
            "select coalesce(sum(amount),0)::bigint amount,count(*)::int count from company_settlements where settled_at>=%s and settled_at<%s",
            (start_utc, end_utc),
        )
        settlement = dict(cur.fetchone() or {})

    received = int(total.get("received") or 0)
    company_share = int(total.get("company_share") or 0)
    expenses = int(expense.get("amount") or 0)

    methods = []
    for row in payment_rows:
        item = app_v3.row_json(row)
        item["label"] = PAYMENT_LABELS.get(item.get("payment_method"), item.get("payment_method") or "ثبت نشده")
        methods.append(item)

    return jsonify(
        {
            "ok": True,
            "from": from_day.isoformat(),
            "to": to_day.isoformat(),
            "timezone": "Asia/Tehran",
            "totals": {
                **{k: int(v or 0) for k, v in total.items()},
                "user_share": received - company_share,
                "expenses": expenses,
                "net_profit": received - company_share - expenses,
                "settled_to_company": int(settlement.get("amount") or 0),
                "expense_count": int(expense.get("count") or 0),
                "settlement_count": int(settlement.get("count") or 0),
            },
            "payment_methods": methods,
        }
    )


@app_v3.app.get("/api/gpt/invoices")
@app_v3.limiter.limit(DEFAULT_RATE_LIMIT)
@gpt_action_required
def gpt_invoices():
    q = str(request.args.get("q") or "").strip()
    if len(q) > 160:
        return _error("جست‌وجو بیش از حد طولانی است")
    limit = _limit(request.args.get("limit"), default=20, maximum=50)

    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select
                i.id,i.invoice_no,i.customer_id,i.issued_at,i.subtotal,i.discount,i.total,i.notes,i.status,
                trim(concat_ws(' ',c.first_name,c.last_name)) customer_name,
                coalesce((select p.phone from customer_phones p where p.customer_id=c.id order by p.is_primary desc,p.id limit 1),'') customer_phone,
                (select count(*)::int from invoice_items x where x.invoice_id=i.id) item_count
            from invoices i
            left join customers_v2 c on c.id=i.customer_id
            where (
                %s=''
                or i.invoice_no::text ilike '%%'||%s||'%%'
                or trim(concat_ws(' ',c.first_name,c.last_name)) ilike '%%'||%s||'%%'
                or exists (
                    select 1 from customer_phones p where p.customer_id=c.id and p.phone ilike '%%'||%s||'%%'
                )
            )
            order by i.issued_at desc,i.invoice_no desc
            limit %s
            """,
            (q, q, q, q, limit),
        )
        rows = cur.fetchall()

    return jsonify({"ok": True, "query": q or None, "count": len(rows), "invoices": _rows(rows)})


@app_v3.app.get("/api/gpt/products")
@app_v3.limiter.limit(DEFAULT_RATE_LIMIT)
@gpt_action_required
def gpt_products():
    q = str(request.args.get("q") or "").strip()
    if len(q) > 160:
        return _error("جست‌وجو بیش از حد طولانی است")
    limit = _limit(request.args.get("limit"), default=30, maximum=100)

    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select id,name,category,description,price,image_url,badge,origin,lifetime_text,is_active,sort_order,updated_at
            from products
            where is_active=true
              and (
                %s=''
                or name ilike '%%'||%s||'%%'
                or category ilike '%%'||%s||'%%'
                or coalesce(description,'') ilike '%%'||%s||'%%'
              )
            order by sort_order asc,updated_at desc
            limit %s
            """,
            (q, q, q, q, limit),
        )
        rows = cur.fetchall()

    return jsonify({"ok": True, "query": q or None, "count": len(rows), "products": _rows(rows)})
