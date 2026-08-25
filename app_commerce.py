from decimal import Decimal, InvalidOperation
from uuid import UUID

from flask import jsonify, request

from app_v3 import app, audit, get_db, row_json, token_required


def _safe_int(value, default=0, minimum=0):
    try:
        result = int(str(value or default).replace(",", "").replace("٬", ""))
    except (TypeError, ValueError):
        result = default
    return max(result, minimum)


def _uuid_or_none(value, label="شناسه"):
    if value in (None, ""):
        return None
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{label} نامعتبر است")


def _clean_product(data):
    return {
        "name": (data.get("name") or "").strip(),
        "category": (data.get("category") or "filter").strip(),
        "description": (data.get("description") or "").strip() or None,
        "price": _safe_int(data.get("price"), 0, 0),
        "image_url": (data.get("image_url") or "").strip() or None,
        "badge": (data.get("badge") or "").strip() or None,
        "origin": (data.get("origin") or "").strip() or None,
        "lifetime_text": (data.get("lifetime_text") or "").strip() or None,
        "is_active": bool(data.get("is_active", True)),
        "sort_order": _safe_int(data.get("sort_order"), 0, 0),
    }


def _clean_invoice_items(items):
    clean_items = []
    subtotal = 0
    for idx, item in enumerate(items or []):
        title = (item.get("title") or "").strip()
        if not title:
            continue
        try:
            qty = Decimal(str(item.get("quantity") or 1))
            if not qty.is_finite() or qty <= 0:
                qty = Decimal("1")
        except (InvalidOperation, TypeError, ValueError):
            qty = Decimal("1")
        unit = _safe_int(item.get("unit_price"), 0, 0)
        line = int(qty * unit)
        subtotal += line
        clean_items.append(
            {
                "product_id": _uuid_or_none(item.get("product_id"), "شناسه محصول"),
                "title": title,
                "quantity": qty,
                "unit_price": unit,
                "line_total": line,
                "sort_order": idx,
            }
        )
    return clean_items, subtotal


def _invoice_payload(row, items=None):
    out = row_json(row)
    if items is not None:
        out["items"] = [row_json(x) for x in items]
    return out


@app.get("/api/products")
@token_required
def products_list():
    include_inactive = request.args.get("all") == "1"
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            """select * from products where (%s or is_active=true)
               order by sort_order asc, created_at desc""",
            (include_inactive,),
        )
        rows = cur.fetchall()
    return jsonify([row_json(r) for r in rows])


@app.post("/api/products")
@token_required
def product_create():
    data = _clean_product(request.get_json() or {})
    if not data["name"]:
        return jsonify({"error": "نام محصول الزامی است"}), 400
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            """insert into products(name,category,description,price,image_url,badge,origin,lifetime_text,is_active,sort_order)
               values(%(name)s,%(category)s,%(description)s,%(price)s,%(image_url)s,%(badge)s,%(origin)s,%(lifetime_text)s,%(is_active)s,%(sort_order)s)
               returning *""",
            data,
        )
        row = cur.fetchone()
        audit(cur, "product", row["id"], "create", None, row_json(row))
    return jsonify(row_json(row)), 201


@app.patch("/api/products/<product_id>")
@token_required
def product_update(product_id):
    try:
        product_id = _uuid_or_none(product_id, "شناسه محصول")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    incoming = request.get_json() or {}
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from products where id=%s", (product_id,))
        before = cur.fetchone()
        if not before:
            return jsonify({"error": "محصول پیدا نشد"}), 404
        merged = dict(before)
        merged.update(incoming)
        data = _clean_product(merged)
        if not data["name"]:
            return jsonify({"error": "نام محصول الزامی است"}), 400
        cur.execute(
            """update products set name=%(name)s,category=%(category)s,description=%(description)s,price=%(price)s,
               image_url=%(image_url)s,badge=%(badge)s,origin=%(origin)s,lifetime_text=%(lifetime_text)s,
               is_active=%(is_active)s,sort_order=%(sort_order)s,updated_at=now()
               where id=%(id)s returning *""",
            {**data, "id": product_id},
        )
        row = cur.fetchone()
        audit(cur, "product", product_id, "update", row_json(before), row_json(row))
    return jsonify(row_json(row))


@app.get("/api/invoices")
@token_required
def invoices_list():
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            """select i.*, trim(concat_ws(' ',c.first_name,c.last_name)) customer_name,
                      coalesce((select p.phone from customer_phones p where p.customer_id=c.id order by p.is_primary desc,p.id limit 1),'') customer_phone,
                      (select count(*) from invoice_items x where x.invoice_id=i.id) item_count
               from invoices i left join customers_v2 c on c.id=i.customer_id
               order by i.issued_at desc, i.invoice_no desc limit 300"""
        )
        rows = cur.fetchall()
    return jsonify([row_json(r) for r in rows])


@app.get("/api/invoices/<invoice_id>")
@token_required
def invoice_detail(invoice_id):
    try:
        invoice_id = _uuid_or_none(invoice_id, "شناسه فاکتور")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            """select i.*, trim(concat_ws(' ',c.first_name,c.last_name)) customer_name,
                      coalesce((select p.phone from customer_phones p where p.customer_id=c.id order by p.is_primary desc,p.id limit 1),'') customer_phone
               from invoices i left join customers_v2 c on c.id=i.customer_id where i.id=%s""",
            (invoice_id,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "فاکتور پیدا نشد"}), 404
        cur.execute("select * from invoice_items where invoice_id=%s order by sort_order,id", (invoice_id,))
        items = cur.fetchall()
    return jsonify(_invoice_payload(row, items))


@app.post("/api/invoices")
@token_required
def invoice_create():
    data = request.get_json() or {}
    try:
        customer_id = _uuid_or_none(data.get("customer_id"), "شناسه مشتری")
        clean_items, subtotal = _clean_invoice_items(data.get("items") or [])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not clean_items:
        return jsonify({"error": "حداقل یک ردیف معتبر فاکتور لازم است"}), 400
    discount = min(_safe_int(data.get("discount"), 0, 0), subtotal)
    total = subtotal - discount
    with get_db() as db, db.cursor() as cur:
        if customer_id:
            cur.execute("select 1 from customers_v2 where id=%s", (customer_id,))
            if not cur.fetchone():
                return jsonify({"error": "مشتری انتخاب‌شده پیدا نشد"}), 400
        product_ids = sorted({x["product_id"] for x in clean_items if x["product_id"]})
        if product_ids:
            cur.execute("select id::text id from products where id=any(%s::uuid[])", (product_ids,))
            found = {r["id"] for r in cur.fetchall()}
            missing = [x for x in product_ids if x not in found]
            if missing:
                return jsonify({"error": "یک یا چند محصول انتخاب‌شده دیگر وجود ندارد"}), 400
        cur.execute(
            """insert into invoices(customer_id,issued_at,subtotal,discount,total,notes,status,created_by)
               values(%s,coalesce(%s::timestamptz,now()),%s,%s,%s,%s,%s,%s) returning *""",
            (
                customer_id,
                data.get("issued_at") or None,
                subtotal,
                discount,
                total,
                (data.get("notes") or "").strip() or None,
                data.get("status") or "issued",
                str(request.current_user.get("user_id")),
            ),
        )
        inv = cur.fetchone()
        for item in clean_items:
            cur.execute(
                """insert into invoice_items(invoice_id,product_id,title,quantity,unit_price,line_total,sort_order)
                   values(%s,%s,%s,%s,%s,%s,%s)""",
                (
                    inv["id"],
                    item["product_id"],
                    item["title"],
                    item["quantity"],
                    item["unit_price"],
                    item["line_total"],
                    item["sort_order"],
                ),
            )
        audit(
            cur,
            "invoice",
            inv["id"],
            "create",
            None,
            {"invoice_no": inv["invoice_no"], "total": total, "items": len(clean_items)},
        )
        cur.execute("select * from invoice_items where invoice_id=%s order by sort_order,id", (inv["id"],))
        saved_items = cur.fetchall()
    return jsonify(_invoice_payload(inv, saved_items)), 201


@app.patch("/api/invoices/<invoice_id>")
@token_required
def invoice_update(invoice_id):
    try:
        invoice_id = _uuid_or_none(invoice_id, "شناسه فاکتور")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    data = request.get_json() or {}
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from invoices where id=%s", (invoice_id,))
        before = cur.fetchone()
        if not before:
            return jsonify({"error": "فاکتور پیدا نشد"}), 404
        cur.execute(
            """update invoices set notes=coalesce(%s,notes), status=coalesce(%s,status), updated_at=now()
               where id=%s returning *""",
            (data.get("notes"), data.get("status"), invoice_id),
        )
        row = cur.fetchone()
        audit(cur, "invoice", invoice_id, "update", row_json(before), row_json(row))
    return jsonify(row_json(row))
