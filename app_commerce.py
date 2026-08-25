from decimal import Decimal

from flask import jsonify, request

from app_v3 import app, audit, get_db, row_json, token_required


def _clean_product(data):
    return {
        "name": (data.get("name") or "").strip(),
        "category": (data.get("category") or "filter").strip(),
        "description": (data.get("description") or "").strip() or None,
        "price": max(int(data.get("price") or 0), 0),
        "image_url": (data.get("image_url") or "").strip() or None,
        "badge": (data.get("badge") or "").strip() or None,
        "origin": (data.get("origin") or "").strip() or None,
        "lifetime_text": (data.get("lifetime_text") or "").strip() or None,
        "is_active": bool(data.get("is_active", True)),
        "sort_order": int(data.get("sort_order") or 0),
    }


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
    incoming = request.get_json() or {}
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from products where id=%s", (product_id,))
        before = cur.fetchone()
        if not before:
            return jsonify({"error": "محصول پیدا نشد"}), 404
        merged = dict(before)
        merged.update(incoming)
        data = _clean_product(merged)
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
    items = data.get("items") or []
    if not items:
        return jsonify({"error": "حداقل یک ردیف فاکتور لازم است"}), 400
    clean_items = []
    subtotal = 0
    for idx, item in enumerate(items):
        title = (item.get("title") or "").strip()
        if not title:
            continue
        qty = Decimal(str(item.get("quantity") or 1))
        if qty <= 0:
            qty = Decimal("1")
        unit = max(int(item.get("unit_price") or 0), 0)
        line = int(qty * unit)
        subtotal += line
        clean_items.append({"product_id": item.get("product_id") or None, "title": title, "quantity": qty, "unit_price": unit, "line_total": line, "sort_order": idx})
    if not clean_items:
        return jsonify({"error": "ردیف معتبر فاکتور وجود ندارد"}), 400
    discount = min(max(int(data.get("discount") or 0), 0), subtotal)
    total = subtotal - discount
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            """insert into invoices(customer_id,issued_at,subtotal,discount,total,notes,status,created_by)
               values(%s,coalesce(%s::timestamptz,now()),%s,%s,%s,%s,%s,%s) returning *""",
            (data.get("customer_id") or None, data.get("issued_at") or None, subtotal, discount, total,
             (data.get("notes") or "").strip() or None, data.get("status") or "issued", str(request.current_user.get("user_id"))),
        )
        inv = cur.fetchone()
        for item in clean_items:
            cur.execute(
                """insert into invoice_items(invoice_id,product_id,title,quantity,unit_price,line_total,sort_order)
                   values(%s,%s,%s,%s,%s,%s,%s)""",
                (inv["id"], item["product_id"], item["title"], item["quantity"], item["unit_price"], item["line_total"], item["sort_order"]),
            )
        audit(cur, "invoice", inv["id"], "create", None, {"invoice_no": inv["invoice_no"], "total": total, "items": len(clean_items)})
        cur.execute("select * from invoice_items where invoice_id=%s order by sort_order,id", (inv["id"],))
        saved_items = cur.fetchall()
    return jsonify(_invoice_payload(inv, saved_items)), 201


@app.patch("/api/invoices/<invoice_id>")
@token_required
def invoice_update(invoice_id):
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
