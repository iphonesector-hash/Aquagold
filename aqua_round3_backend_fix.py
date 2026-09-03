"""Branch-only runtime guards and reporting helpers for the Aqua QA branch."""
from __future__ import annotations

import re

from flask import jsonify, request

import app_v3

_BYPASS_PATHS = {
    "/api/aqua-ai/chat",
    "/api/aqua-ai/transcribe",
    "/api/aqua-ai/speak",
}
_original_idempotency_begin = app_v3._idempotency_begin


def _aqua_round3_idempotency_begin(user_id):
    # Aqua AI provider calls can take several seconds and are not database-create
    # mutations. Keeping them in the generic mutation lock can strand retries in
    # a stale "request is processing" row.
    if request.path in _BYPASS_PATHS:
        return None, None
    return _original_idempotency_begin(user_id)


app_v3._idempotency_begin = _aqua_round3_idempotency_begin


def _payment_key(value):
    method = str(value or "").strip().lower().replace("\u200c", " ")
    if method == "cash" or "نقد" in method:
        return "cash"
    if method == "transfer" or re.search(r"کارت\s*به\s*کارت|card.?to.?card", method):
        return "transfer"
    if method in {"card", "pos"} or re.search(r"کارت\s*خوان|کارتخوان|card.?reader", method):
        return "card"
    return "other"


@app_v3.app.get("/api/reports/payment-methods")
@app_v3.token_required
def aqua_round3_payment_methods():
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select coalesce(nullif(payment_method,''),'other') method,
                   count(*)::int services,
                   coalesce(sum(received_amount),0)::bigint amount
            from service_visits
            group by 1
            order by amount desc
            """
        )
        rows = cur.fetchall()
    totals = {"cash": 0, "transfer": 0, "card": 0, "other": 0}
    counts = {"cash": 0, "transfer": 0, "card": 0, "other": 0}
    for row in rows:
        key = _payment_key(row.get("method"))
        totals[key] += int(row.get("amount") or 0)
        counts[key] += int(row.get("services") or 0)
    return jsonify({"totals": totals, "counts": counts})


@app_v3.app.get("/api/map/work-pins")
@app_v3.token_required
def aqua_round3_work_pins():
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """
            select distinct on (v.customer_id)
                   v.id::text id,
                   v.customer_id::text customer_id,
                   trim(concat_ws(' ',c.first_name,c.last_name)) name,
                   c.map_label,c.address,
                   st_y(c.location::geometry) latitude,
                   st_x(c.location::geometry) longitude,
                   coalesce(v.service_type,'سرویس') service_type,
                   coalesce(v.description,'') description,
                   coalesce(v.received_amount,0)::bigint received_amount,
                   coalesce(v.visited_at,v.created_at) visited_at
            from service_visits v
            join customers_v2 c on c.id=v.customer_id
            where c.archived=false and c.location is not null
            order by v.customer_id,coalesce(v.visited_at,v.created_at) desc,v.created_at desc
            limit 500
            """
        )
        rows = cur.fetchall()
    return jsonify([app_v3.row_json(row) for row in rows])
