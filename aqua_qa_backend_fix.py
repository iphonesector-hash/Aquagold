"""QA-branch backend repairs. Test branch only.

B1: answer read-only "how many services today" from DB; never 401 a chat
    that already passed session checks.
B2: payment-method totals include unlabeled amounts as other; skip cancelled.
B3: if the invoices table is empty, list invoices derived from service_visits.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from uuid import UUID

from flask import jsonify, request

import app_v3
import aqua_round3_backend_fix

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_MUTATION_MARKERS = (
    "تغییر بده",
    "تغییرش بده",
    "ویرایش کن",
    "ویرایشش کن",
    "درست کن",
    "اصلاح کن",
    "حذف کن",
    "کنسل",
    "لغو کن",
)
_COUNT_MARKERS = ("چند سرویس", "چندتا سرویس", "تعداد سرویس", "چند تا سرویس")


def classify_payment_method(value):
    return aqua_round3_backend_fix._payment_key(value)


def is_readonly_service_count(text):
    value = re.sub(r"\s+", " ", str(text or "").translate(_FA_DIGITS)).strip()
    if not value:
        return False
    if any(marker in value for marker in _MUTATION_MARKERS):
        return False
    has_count = any(marker in value for marker in _COUNT_MARKERS)
    has_today = "امروز" in value
    explicit_read = "فقط بگو" in value or "هیچ تغییری" in value
    return has_count and (has_today or explicit_read)


def service_visit_to_invoice(row):
    data = dict(row or {})
    visit_id = str(data.get("id") or "")
    amount = int(data.get("invoice_amount") or data.get("received_amount") or 0)
    title = str(data.get("service_type") or data.get("description") or "سرویس")
    issued = data.get("visited_at") or data.get("created_at")
    if isinstance(issued, (datetime, date)):
        issued = issued.isoformat()
    customer_id = data.get("customer_id")
    return {
        "id": visit_id,
        "invoice_no": f"SV-{visit_id[:8]}",
        "customer_id": str(customer_id) if customer_id else None,
        "customer_name": data.get("customer_name") or "مشتری آزاد",
        "customer_phone": data.get("phone") or "",
        "issued_at": issued,
        "subtotal": amount,
        "discount": 0,
        "total": amount,
        "notes": data.get("description") or "",
        "status": "issued",
        "item_count": 1,
        "source": "service_visit",
        "items": [
            {
                "id": visit_id,
                "title": title,
                "quantity": 1,
                "unit_price": amount,
                "line_total": amount,
            }
        ],
    }


def _today_service_answer():
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select
              count(*)::int as total,
              count(*) filter (where coalesce(status,'') = 'cancelled')::int as cancelled,
              count(*) filter (where coalesce(status,'') = 'completed')::int as completed
            from service_visits
            where (coalesce(visited_at, created_at) at time zone 'Asia/Tehran')::date
                = (now() at time zone 'Asia/Tehran')::date
            """
        )
        row = cur.fetchone() or {}
    total = int(row.get("total") or 0)
    completed = int(row.get("completed") or 0)
    cancelled = int(row.get("cancelled") or 0)
    return jsonify(
        {
            "answer": (
                f"امروز {total} سرویس ثبت شده"
                f" ({completed} تکمیل، {cancelled} لغو)."
                " هیچ تغییری اعمال نکردم."
            ),
            "today_services": total,
            "today_completed": completed,
            "today_cancelled": cancelled,
            "verified": True,
        }
    )


_ORIGINAL_CHAT = app_v3.app.view_functions.get("aqua_chat")


@app_v3.roles_required("technician")
def _aqua_chat_qa_guard():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    if is_readonly_service_count(text):
        try:
            return _today_service_answer()
        except Exception:
            app_v3.logger.exception("aqua_qa_today_service_count_failed")
            return jsonify({"answer": "شمارش سرویس امروز انجام نشد؛ هیچ تغییری اعمال نکردم."}), 500
    if _ORIGINAL_CHAT is None:
        return jsonify({"answer": "آریا در دسترس نیست؛ هیچ تغییری اعمال نشد."}), 503
    result = _ORIGINAL_CHAT()
    response = result if hasattr(result, "status_code") else app_v3.app.make_response(result)
    if response.status_code == 401:
        app_v3.logger.warning("aqua_qa_chat_inner_401_suppressed")
        return jsonify(
            {
                "answer": "پیام رسید و نشست هنوز معتبر است. پاسخ آریا را دوباره بفرست؛ هیچ تغییری اعمال نشد.",
                "session": "ok",
            }
        )
    return result


if _ORIGINAL_CHAT is not None:
    app_v3.app.view_functions["aqua_chat"] = _aqua_chat_qa_guard


@app_v3.token_required
def _payment_methods_with_unlabeled():
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select coalesce(nullif(btrim(payment_method), ''), 'other') method,
                   count(*)::int services,
                   coalesce(sum(received_amount), 0)::bigint amount
            from service_visits
            where coalesce(status, '') not in ('cancelled', 'scheduled')
            group by 1
            order by amount desc
            """
        )
        rows = cur.fetchall()
        cur.execute(
            """
            select coalesce(sum(received_amount), 0)::bigint received
            from service_visits
            where coalesce(status, '') not in ('cancelled', 'scheduled')
            """
        )
        received_total = int((cur.fetchone() or {}).get("received") or 0)
    totals = {"cash": 0, "transfer": 0, "card": 0, "other": 0}
    counts = {"cash": 0, "transfer": 0, "card": 0, "other": 0}
    unlabeled_amount = 0
    unlabeled_count = 0
    for row in rows:
        method = row.get("method")
        key = classify_payment_method(method)
        amount = int(row.get("amount") or 0)
        services = int(row.get("services") or 0)
        totals[key] += amount
        counts[key] += services
        if key == "other" and str(method or "").strip().lower() in {"", "other", "سایر", "نامشخص"}:
            unlabeled_amount += amount
            unlabeled_count += services
    return jsonify(
        {
            "totals": totals,
            "counts": counts,
            "received_total": received_total,
            "unlabeled": {"amount": unlabeled_amount, "services": unlabeled_count},
        }
    )


app_v3.app.view_functions["aqua_round3_payment_methods"] = _payment_methods_with_unlabeled


def _load_service_invoices(limit=300, visit_id=None):
    with app_v3.get_db() as db, db.cursor() as cur:
        if visit_id is not None:
            cur.execute(
                """
                select v.id, v.customer_id, v.service_type, v.description,
                       v.invoice_amount, v.received_amount, v.status,
                       coalesce(v.visited_at, v.created_at) visited_at, v.created_at,
                       trim(concat_ws(' ', c.first_name, c.last_name)) customer_name,
                       coalesce((select p.phone from customer_phones p
                                 where p.customer_id = c.id
                                 order by p.is_primary desc, p.id limit 1), '') phone
                from service_visits v
                left join customers_v2 c on c.id = v.customer_id
                where v.id = %s
                  and coalesce(v.status, '') <> 'cancelled'
                  and coalesce(v.invoice_amount, v.received_amount, 0) > 0
                """,
                (visit_id,),
            )
            row = cur.fetchone()
            return [service_visit_to_invoice(row)] if row else []
        cur.execute(
            """
            select v.id, v.customer_id, v.service_type, v.description,
                   v.invoice_amount, v.received_amount, v.status,
                   coalesce(v.visited_at, v.created_at) visited_at, v.created_at,
                   trim(concat_ws(' ', c.first_name, c.last_name)) customer_name,
                   coalesce((select p.phone from customer_phones p
                             where p.customer_id = c.id
                             order by p.is_primary desc, p.id limit 1), '') phone
            from service_visits v
            left join customers_v2 c on c.id = v.customer_id
            where coalesce(v.status, '') <> 'cancelled'
              and coalesce(v.invoice_amount, v.received_amount, 0) > 0
            order by coalesce(v.visited_at, v.created_at) desc
            limit %s
            """,
            (limit,),
        )
        return [service_visit_to_invoice(row) for row in cur.fetchall()]


_ORIGINAL_INVOICES_LIST = app_v3.app.view_functions.get("invoices_list")
_ORIGINAL_INVOICE_DETAIL = app_v3.app.view_functions.get("invoice_detail")


@app_v3.token_required
def _invoices_list_with_services():
    limit = 300
    try:
        limit = int(request.args.get("limit") or 300)
    except (TypeError, ValueError):
        limit = 300
    limit = max(1, min(limit, 500))
    if _ORIGINAL_INVOICES_LIST is not None:
        result = _ORIGINAL_INVOICES_LIST()
        response = result if hasattr(result, "get_json") else app_v3.app.make_response(result)
        if response.status_code == 200:
            rows = response.get_json()
            if isinstance(rows, list) and rows:
                return result
    return jsonify(_load_service_invoices(limit=limit))


@app_v3.token_required
def _invoice_detail_with_services(invoice_id):
    if _ORIGINAL_INVOICE_DETAIL is not None:
        result = _ORIGINAL_INVOICE_DETAIL(invoice_id)
        response = result if hasattr(result, "status_code") else app_v3.app.make_response(result)
        if response.status_code != 404:
            return result
    try:
        visit_id = str(UUID(str(invoice_id)))
    except (TypeError, ValueError, AttributeError):
        return jsonify({"error": "فاکتور پیدا نشد"}), 404
    rows = _load_service_invoices(visit_id=visit_id)
    if not rows:
        return jsonify({"error": "فاکتور پیدا نشد"}), 404
    return jsonify(rows[0])


if _ORIGINAL_INVOICES_LIST is not None:
    app_v3.app.view_functions["invoices_list"] = _invoices_list_with_services
if _ORIGINAL_INVOICE_DETAIL is not None:
    app_v3.app.view_functions["invoice_detail"] = _invoice_detail_with_services
