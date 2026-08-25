from decimal import Decimal, InvalidOperation
from uuid import UUID

from flask import jsonify, request

from app_v3 import app, audit, get_db, roles_required, row_json, token_required
from aquagold_validation import (
    ValidationError,
    boolean as valid_boolean,
    choice as valid_choice,
    integer as valid_integer,
    text as valid_text,
    timestamp as valid_timestamp,
    uuid as valid_uuid,
)


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
    image_url = valid_text(data.get("image_url"), "نشانی تصویر", max_length=1_500_000)
    if image_url and not image_url.startswith(("/assets/", "https://", "data:image/jpeg;base64,", "data:image/png;base64,", "data:image/webp;base64,")):
        raise ValidationError("تصویر باید فایل داخلی، HTTPS یا تصویر فشرده معتبر باشد")
    return {
        "name": valid_text(data.get("name"), "نام محصول", required=True, max_length=250),
        "category": valid_choice(data.get("category"), "دسته محصول", {"device_filter", "fridge_filter", "accessory", "service"}, default="device_filter"),
        "description": valid_text(data.get("description"), "توضیحات محصول", max_length=4000),
        "price": valid_integer(data.get("price"), "قیمت", default=0),
        "image_url": image_url,
        "badge": valid_text(data.get("badge"), "برچسب", max_length=80),
        "origin": valid_text(data.get("origin"), "کشور یا برند", max_length=120),
        "lifetime_text": valid_text(data.get("lifetime_text"), "عمر محصول", max_length=120),
        "is_active": valid_boolean(data.get("is_active"), True),
        "sort_order": valid_integer(data.get("sort_order"), "ترتیب", minimum=0, maximum=1_000_000, default=0),
    }


def _clean_invoice_items(items):
    if not isinstance(items, list):
        raise ValidationError("ردیف‌های فاکتور باید به صورت فهرست ارسال شوند")
    if len(items) > 100:
        raise ValidationError("هر فاکتور حداکثر می‌تواند ۱۰۰ ردیف داشته باشد")
    clean_items = []
    subtotal = 0
    for idx, item in enumerate(items or []):
        if not isinstance(item, dict):
            raise ValidationError("ساختار یکی از ردیف‌های فاکتور معتبر نیست")
        title = valid_text(item.get("title"), "شرح ردیف", max_length=500)
        if not title:
            continue
        raw_quantity = item.get("quantity")
        try:
            qty = Decimal(str(1 if raw_quantity in (None, "") else raw_quantity))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("تعداد یکی از ردیف‌های فاکتور معتبر نیست")
        if not qty.is_finite() or not Decimal("0") < qty <= Decimal("10000"):
            raise ValidationError("تعداد هر ردیف باید بیشتر از صفر و حداکثر ۱۰۰۰۰ باشد")
        unit = valid_integer(item.get("unit_price"), "قیمت واحد", default=0)
        line = int(qty * unit)
        subtotal += line
        if line > 10**15 or subtotal > 10**15:
            raise ValidationError("مبلغ فاکتور بیش از سقف مجاز است")
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
    include_inactive = request.args.get("all") == "1" and request.current_user.get("role") in {"admin", "superadmin"}
    limit = valid_integer(request.args.get("limit"), "تعداد محصول", minimum=1, maximum=500, default=300)
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            """select * from products where (%s or is_active=true)
               order by sort_order asc, created_at desc limit %s""",
            (include_inactive, limit),
        )
        rows = cur.fetchall()
    return jsonify([row_json(r) for r in rows])


@app.post("/api/products")
@roles_required("admin")
def product_create():
    incoming = request.get_json() or {}
    client_id = valid_uuid(incoming.get("client_id"), "شناسه آفلاین محصول", required=False)
    data = _clean_product(incoming)
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            """insert into products(id,name,category,description,price,image_url,badge,origin,lifetime_text,is_active,sort_order)
               values(coalesce(%(client_id)s::uuid,gen_random_uuid()),%(name)s,%(category)s,%(description)s,%(price)s,%(image_url)s,%(badge)s,%(origin)s,%(lifetime_text)s,%(is_active)s,%(sort_order)s)
               returning *""",
            {**data, "client_id": client_id},
        )
        row = cur.fetchone()
        audit(cur, "product", row["id"], "create", None, row_json(row))
    return jsonify(row_json(row)), 201


@app.patch("/api/products/<product_id>")
@roles_required("admin")
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
    limit = valid_integer(request.args.get("limit"), "تعداد فاکتور", minimum=1, maximum=500, default=300)
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            """select i.*, trim(concat_ws(' ',c.first_name,c.last_name)) customer_name,
                      coalesce((select p.phone from customer_phones p where p.customer_id=c.id order by p.is_primary desc,p.id limit 1),'') customer_phone,
                      (select count(*) from invoice_items x where x.invoice_id=i.id) item_count
               from invoices i left join customers_v2 c on c.id=i.customer_id
               order by i.issued_at desc, i.invoice_no desc limit %s""",
            (limit,),
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
@roles_required("technician")
def invoice_create():
    data = request.get_json() or {}
    try:
        client_id = valid_uuid(data.get("client_id"), "شناسه آفلاین فاکتور", required=False)
        customer_id = valid_uuid(data.get("customer_id"), "شناسه مشتری", required=False)
        clean_items, subtotal = _clean_invoice_items(data.get("items") or [])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not clean_items:
        return jsonify({"error": "حداقل یک ردیف معتبر فاکتور لازم است"}), 400
    discount = min(valid_integer(data.get("discount"), "تخفیف", default=0), subtotal)
    issued_at = valid_timestamp(data.get("issued_at"), "تاریخ فاکتور")
    notes = valid_text(data.get("notes"), "توضیحات فاکتور", max_length=4000)
    status = valid_choice(data.get("status"), "وضعیت فاکتور", {"draft", "issued", "paid", "void"}, default="issued")
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
            """insert into invoices(id,customer_id,issued_at,subtotal,discount,total,notes,status,created_by)
               values(coalesce(%s::uuid,gen_random_uuid()),%s,coalesce(%s::timestamptz,now()),%s,%s,%s,%s,%s,%s) returning *""",
            (
                client_id,
                customer_id,
                issued_at,
                subtotal,
                discount,
                total,
                notes,
                status,
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
@roles_required("admin")
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
        notes = valid_text(data.get("notes", before["notes"]), "توضیحات فاکتور", max_length=4000)
        status = valid_choice(data.get("status", before["status"]), "وضعیت فاکتور", {"draft", "issued", "paid", "void"}, default="issued")
        cur.execute(
            """update invoices set notes=coalesce(%s,notes), status=coalesce(%s,status), updated_at=now()
               where id=%s returning *""",
            (notes, status, invoice_id),
        )
        row = cur.fetchone()
        audit(cur, "invoice", invoice_id, "update", row_json(before), row_json(row))
    return jsonify(row_json(row))
