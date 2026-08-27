import os
from datetime import datetime, timezone

from flask import jsonify, request

import app_v3


def _authorized():
    expected = os.getenv("FARANGIS_INTEGRATION_TOKEN", "")
    if not expected:
        return False
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {expected}"


def _require_bridge_auth():
    if not _authorized():
        return jsonify({"error": "Farangis integration authentication failed"}), 401
    return None


def _find_customer(cur, name):
    name = (name or "").strip()
    if not name:
        return None
    cur.execute(
        """
        select c.id,c.first_name,c.last_name,c.address,c.map_label,c.device_model,
               (select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone
        from customers_v2 c
        where c.archived=false and (
          c.normalized_name ilike %s or c.last_name ilike %s or trim(concat_ws(' ',c.first_name,c.last_name)) ilike %s
        )
        order by c.updated_at desc
        limit 1
        """,
        (f"%{name.lower()}%", f"%{name}%", f"%{name}%"),
    )
    return cur.fetchone()


@app_v3.app.post("/api/farangis/customer-payment")
def farangis_customer_payment():
    denied = _require_bridge_auth()
    if denied:
        return denied
    data = request.get_json() or {}
    customer_name = (data.get("customerName") or "").strip()
    amount = app_v3.as_int(data.get("amount"), 0)
    if not customer_name:
        return jsonify({"error": "نام مشتری لازم است"}), 400
    if amount <= 0:
        return jsonify({"error": "مبلغ معتبر لازم است"}), 400

    with app_v3.get_db() as db, db.cursor() as cur:
        customer = _find_customer(cur, customer_name)
        if not customer:
            return jsonify({"error": "مشتری پیدا نشد", "needsCustomerSelection": True, "query": customer_name}), 404

        pct = app_v3.finance_percent(cur)
        company = round(amount * pct / 100)
        cur.execute(
            """
            insert into service_visits(
              customer_id,service_type,description,amount,invoice_amount,received_amount,
              company_share_percent,company_share_amount,customer_balance,payment_method,status,visited_at
            ) values(%s,%s,%s,%s,%s,%s,%s,%s,0,%s,'completed',%s) returning id
            """,
            (
                customer["id"],
                data.get("serviceType") or "فرمان صوتی فرنگیس",
                data.get("description") or data.get("raw") or "ثبت توسط Farangis",
                amount,
                amount,
                amount,
                pct,
                company,
                data.get("paymentMethod") or "unknown",
                data.get("visitedAt") or datetime.now(timezone.utc),
            ),
        )
        visit_id = cur.fetchone()["id"]
        app_v3.audit(cur, "service_visit", visit_id, "farangis_create", after={"customer": customer_name, "amount": amount, "source": "farangis"})

    return jsonify({
        "message": "سرویس و مبلغ مشتری در AquaGold ثبت شد",
        "customer": {
            "id": str(customer["id"]),
            "name": " ".join(x for x in [customer.get("first_name"), customer.get("last_name")] if x).strip(),
            "phone": customer.get("phone"),
            "address": customer.get("address"),
        },
        "visitId": str(visit_id),
        "receivedAmount": amount,
        "companyShareAmount": company,
    }), 201


@app_v3.app.post("/api/farangis/customer-history")
def farangis_customer_history():
    denied = _require_bridge_auth()
    if denied:
        return denied
    data = request.get_json() or {}
    query = (data.get("query") or data.get("customerName") or "").strip()
    if not query:
        return jsonify({"error": "نام یا عبارت جستجو لازم است"}), 400

    with app_v3.get_db() as db, db.cursor() as cur:
        customer = _find_customer(cur, query)
        if not customer:
            return jsonify({"error": "مشتری پیدا نشد", "query": query}), 404
        cur.execute(
            """
            select id,service_type,description,invoice_amount,received_amount,payment_method,status,
                   coalesce(visited_at,created_at) visited_at,next_service_at
            from service_visits
            where customer_id=%s
            order by coalesce(visited_at,created_at) desc
            limit 10
            """,
            (customer["id"],),
        )
        rows = cur.fetchall()

    visits = []
    for row in rows:
        item = app_v3.row_json(row)
        item["id"] = str(item["id"])
        for key in ("visited_at", "next_service_at"):
            value = item.get(key)
            if hasattr(value, "isoformat"):
                item[key] = value.isoformat()
        visits.append(item)

    name = " ".join(x for x in [customer.get("first_name"), customer.get("last_name")] if x).strip()
    latest = visits[0] if visits else None
    return jsonify({
        "message": "سابقه مشتری پیدا شد",
        "customer": {"id": str(customer["id"]), "name": name, "phone": customer.get("phone"), "address": customer.get("address"), "deviceModel": customer.get("device_model")},
        "latest": latest,
        "visits": visits,
    })
