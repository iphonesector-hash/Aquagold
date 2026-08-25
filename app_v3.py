import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import wraps
from uuid import UUID

import jwt
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

from smart_intake import parse_intake

DIGIT_TRANS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _database_url():
    for key in ("AQUAGOLD_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL", "NEON_DATABASE_URL", "AQUAGOLD_URL"):
        value = os.getenv(key)
        if value:
            return value
    for key, value in os.environ.items():
        if key.startswith("AQUAGOLD") and key.endswith("_URL") and value.startswith(("postgres://", "postgresql://")):
            return value
    return None


DATABASE_URL = _database_url()
SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("AQUAGOLD_SECRET_KEY") or "aquagold-local-dev-only"
TOKEN_EXPIRY_HOURS = 24
app = Flask(__name__, static_folder=".", static_url_path="")
origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "").split(",") if x.strip()]
CORS(app, origins=origins) if origins else CORS(app)


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("AquaGold database URL is not configured")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)


def normalize_name(first_name, last_name):
    return re.sub(r"\s+", " ", f"{first_name or ''} {last_name or ''}".strip().lower())


def normalize_phone(value):
    value = str(value or "").translate(DIGIT_TRANS)
    digits = re.sub(r"\D", "", value)
    if digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "0" + digits
    return digits


def as_int(value, default=0):
    if value in (None, ""):
        return default
    if isinstance(value, str):
        value = re.sub(r"[^0-9-]", "", value.translate(DIGIT_TRANS))
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def row_json(row):
    out = {}
    for k, v in dict(row).items():
        if isinstance(v, Decimal):
            v = float(v)
        elif isinstance(v, UUID):
            v = str(v)
        out[k] = v
    return out


def create_token(user):
    now = datetime.now(timezone.utc)
    return jwt.encode({"user_id": str(user["id"]), "role": user["role"], "iat": now, "exp": now + timedelta(hours=TOKEN_EXPIRY_HOURS)}, SECRET_KEY, algorithm="HS256")


def token_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Authentication required"}), 401
        try:
            request.current_user = jwt.decode(auth[7:], SECRET_KEY, algorithms=["HS256"])
        except jwt.PyJWTError:
            return jsonify({"error": "Token is invalid or expired"}), 401
        return fn(*args, **kwargs)
    return wrapper


def audit(cur, entity_type, entity_id, action, before=None, after=None):
    user = getattr(request, "current_user", {}) or {}
    cur.execute(
        "insert into audit_log(entity_type,entity_id,action,before_data,after_data,changed_by) values(%s,%s,%s,%s,%s,%s)",
        (entity_type, str(entity_id), action, Jsonb(before) if before is not None else None, Jsonb(after) if after is not None else None, str(user.get("user_id")) if user else None),
    )


def finance_percent(cur):
    cur.execute("select value from app_settings where key='finance'")
    row = cur.fetchone()
    try:
        return float((row or {}).get("value", {}).get("company_share_percent", 50))
    except Exception:
        return 50.0


def bootstrap_admin_if_requested():
    username, password = os.getenv("AQUAGOLD_ADMIN_USERNAME"), os.getenv("AQUAGOLD_ADMIN_PASSWORD")
    if not DATABASE_URL or not username or not password:
        return
    with get_db() as db, db.cursor() as cur:
        cur.execute("select id from users where username=%s", (username,))
        if not cur.fetchone():
            cur.execute("insert into users(username,password_hash,first_name,last_name,role,active) values(%s,%s,%s,%s,'superadmin',true)", (username, generate_password_hash(password), "مدیر", "AquaGold"))


try:
    bootstrap_admin_if_requested()
except Exception:
    pass


@app.get("/")
def index():
    return send_from_directory(".", "index.html")


@app.get("/health")
def health():
    if not DATABASE_URL:
        return jsonify({"status": "unhealthy", "database": "not_configured"}), 503
    try:
        with get_db() as db, db.cursor() as cur:
            cur.execute("select 1")
            cur.fetchone()
        return jsonify({"status": "healthy", "database": "neon", "version": "v3"})
    except Exception as exc:
        return jsonify({"status": "unhealthy", "error": str(exc)}), 503


@app.post("/api/login")
def login():
    data = request.get_json() or {}
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from users where username=%s and active=true", (data.get("username", ""),))
        user = cur.fetchone()
    if not user or not check_password_hash(user["password_hash"], data.get("password", "")):
        return jsonify({"error": "Invalid credentials"}), 401
    return jsonify({"token": create_token(user), "user": {k: user[k] for k in ("id", "username", "first_name", "last_name", "role")}})


@app.post("/api/logout")
def logout():
    return jsonify({"message": "Logged out"})


def customer_payload(row):
    row = row_json(row)
    phones = row.get("phones") or []
    row["id"] = str(row["id"])
    row["name"] = " ".join(x for x in [row.get("first_name"), row.get("last_name")] if x).strip()
    row["phone"] = phones[0] if phones else None
    return row


@app.get("/api/customers")
@token_required
def customers_list():
    include_archived = request.args.get("archived") == "1"
    with get_db() as db, db.cursor() as cur:
        cur.execute("""
            select c.*,case when c.location is null then null else st_y(c.location::geometry) end latitude,
                   case when c.location is null then null else st_x(c.location::geometry) end longitude,
                   coalesce(array_agg(p.phone order by p.is_primary desc,p.id) filter(where p.phone is not null),'{}') phones
            from customers_v2 c left join customer_phones p on p.customer_id=c.id
            where (%s or c.archived=false)
            group by c.id order by c.created_at desc
        """, (include_archived,))
        rows = cur.fetchall()
    return jsonify([customer_payload(r) for r in rows])


@app.post("/api/customers")
@token_required
def customer_create():
    data = request.get_json() or {}
    first = (data.get("first_name") or "").strip() or None
    last = (data.get("last_name") or data.get("name") or "").strip()
    if not last:
        return jsonify({"error": "نام خانوادگی الزامی است"}), 400
    phones = [normalize_phone(x) for x in data.get("phones", [])]
    phones = [x for x in dict.fromkeys(phones) if x]
    lat, lng = as_float(data.get("latitude")), as_float(data.get("longitude"))
    with get_db() as db, db.cursor() as cur:
        if phones:
            cur.execute("select phone,customer_id from customer_phones where phone=any(%s) limit 1", (phones,))
            hit = cur.fetchone()
            if hit:
                return jsonify({"error": "این شماره قبلاً برای مشتری دیگری ثبت شده", "phone": hit["phone"], "existing_customer_id": str(hit["customer_id"])}), 409
        common = (first,last,normalize_name(first,last),data.get("address"),data.get("map_label") or f"{first or ''} {last}".strip(),data.get("unit_no"),data.get("plaque"),data.get("device_model"),data.get("notes"),str(request.current_user.get("user_id")))
        if lat is not None and lng is not None:
            cur.execute("""insert into customers_v2(first_name,last_name,normalized_name,address,map_label,unit_no,plaque,device_model,notes,created_by,location,location_accuracy_m,location_source)
                           values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,st_setsrid(st_makepoint(%s,%s),4326)::geography,%s,%s) returning id""", common + (lng,lat,data.get("location_accuracy_m"),data.get("location_source") or "gps"))
        else:
            cur.execute("""insert into customers_v2(first_name,last_name,normalized_name,address,map_label,unit_no,plaque,device_model,notes,created_by)
                           values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""", common)
        cid = cur.fetchone()["id"]
        for i, phone in enumerate(phones):
            cur.execute("insert into customer_phones(customer_id,phone,is_primary) values(%s,%s,%s)", (cid, phone, i == 0))
        audit(cur, "customer", cid, "create", after={"name": f"{first or ''} {last}".strip(), "phones": phones, "address": data.get("address")})
    return jsonify({"id": str(cid), "message": "مشتری ثبت شد"}), 201


@app.patch("/api/customers/<uuid:cid>")
@token_required
def customer_update(cid):
    data = request.get_json() or {}
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from customers_v2 where id=%s", (cid,))
        before = cur.fetchone()
        if not before:
            return jsonify({"error": "مشتری پیدا نشد"}), 404
        if "phones" in data:
            phones = [normalize_phone(x) for x in data.get("phones", [])]
            phones = [x for x in dict.fromkeys(phones) if x]
            if phones:
                cur.execute("select phone,customer_id from customer_phones where phone=any(%s) and customer_id<>%s limit 1", (phones, cid))
                conflict = cur.fetchone()
                if conflict:
                    return jsonify({"error": "یکی از شماره‌ها متعلق به مشتری دیگری است", "phone": conflict["phone"], "existing_customer_id": str(conflict["customer_id"])}), 409
        else:
            phones = None
        first = data.get("first_name", before["first_name"])
        last = data.get("last_name", before["last_name"])
        cur.execute("""update customers_v2 set first_name=%s,last_name=%s,normalized_name=%s,address=%s,map_label=%s,unit_no=%s,plaque=%s,device_model=%s,notes=%s,archived=%s,updated_at=now() where id=%s""",
                    (first,last,normalize_name(first,last),data.get("address",before["address"]),data.get("map_label",before["map_label"]),data.get("unit_no",before["unit_no"]),data.get("plaque",before["plaque"]),data.get("device_model",before["device_model"]),data.get("notes",before["notes"]),bool(data.get("archived",before["archived"])),cid))
        if phones is not None:
            cur.execute("delete from customer_phones where customer_id=%s", (cid,))
            for i, phone in enumerate(phones):
                cur.execute("insert into customer_phones(customer_id,phone,is_primary) values(%s,%s,%s)", (cid, phone, i == 0))
        audit(cur, "customer", cid, "update", before={"first_name": before["first_name"], "last_name": before["last_name"], "address": before["address"]}, after=data)
    return jsonify({"message": "اطلاعات مشتری ویرایش شد"})


@app.patch("/api/customers/<uuid:cid>/location")
@token_required
def customer_location(cid):
    data = request.get_json() or {}
    lat, lng = as_float(data.get("latitude")), as_float(data.get("longitude"))
    if lat is None or lng is None or not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return jsonify({"error": "مختصات معتبر لازم است"}), 400
    with get_db() as db, db.cursor() as cur:
        cur.execute("select id,case when location is null then null else st_y(location::geometry) end latitude,case when location is null then null else st_x(location::geometry) end longitude from customers_v2 where id=%s", (cid,))
        before = cur.fetchone()
        if not before:
            return jsonify({"error": "مشتری پیدا نشد"}), 404
        cur.execute("update customers_v2 set location=st_setsrid(st_makepoint(%s,%s),4326)::geography,location_accuracy_m=%s,location_source=%s,updated_at=now() where id=%s", (lng,lat,data.get("accuracy"),data.get("source") or "manual",cid))
        audit(cur, "customer", cid, "location_update", before={"latitude": before["latitude"], "longitude": before["longitude"]}, after={"latitude": lat, "longitude": lng, "source": data.get("source") or "manual"})
    return jsonify({"message": "موقعیت مشتری ذخیره شد", "latitude": lat, "longitude": lng})


@app.get("/api/customers/suggest")
@token_required
def customers_suggest():
    surname = (request.args.get("surname") or "").strip()
    phone = normalize_phone(request.args.get("phone"))
    lat, lng = as_float(request.args.get("lat")), as_float(request.args.get("lng"))
    with get_db() as db, db.cursor() as cur:
        if phone:
            cur.execute("select c.id,c.first_name,c.last_name,c.address,c.map_label,p.phone,0::numeric distance_m from customer_phones p join customers_v2 c on c.id=p.customer_id where p.phone=%s and c.archived=false limit 10", (phone,))
        elif lat is not None and lng is not None:
            cur.execute("""select c.id,c.first_name,c.last_name,c.address,c.map_label,(select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone,
                           round(st_distance(c.location,st_setsrid(st_makepoint(%s,%s),4326)::geography)::numeric,1) distance_m
                           from customers_v2 c where c.location is not null and c.archived=false and (%s='' or c.last_name ilike '%%'||%s||'%%')
                           and st_dwithin(c.location,st_setsrid(st_makepoint(%s,%s),4326)::geography,250) order by distance_m limit 10""", (lng,lat,surname,surname,lng,lat))
        else:
            cur.execute("""select c.id,c.first_name,c.last_name,c.address,c.map_label,(select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone,null::numeric distance_m
                           from customers_v2 c where c.archived=false and %s<>'' and c.last_name ilike '%%'||%s||'%%' order by c.updated_at desc limit 10""", (surname,surname))
        rows = cur.fetchall()
    return jsonify([{**row_json(r), "id": str(r["id"])} for r in rows])


@app.get("/api/jobs")
@token_required
def jobs_list():
    with get_db() as db, db.cursor() as cur:
        cur.execute("""select v.id,v.customer_id,v.service_type,v.description,v.amount,v.invoice_amount,v.received_amount,v.company_share_percent,v.company_share_amount,v.customer_balance,v.payment_method,v.status,v.next_service_at,v.visitor_code,v.created_at,coalesce(v.visited_at,v.created_at) date,c.address,c.device_model,c.map_label,trim(concat_ws(' ',c.first_name,c.last_name)) name,(select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone from service_visits v join customers_v2 c on c.id=v.customer_id order by coalesce(v.visited_at,v.created_at) desc""")
        rows = cur.fetchall()
    return jsonify([{**row_json(r), "id": str(r["id"]), "customer_id": str(r["customer_id"])} for r in rows])


@app.post("/api/jobs")
@token_required
def job_create():
    data = request.get_json() or {}
    cid = data.get("customer_id")
    if not cid:
        return jsonify({"error": "مشتری الزامی است"}), 400
    invoice = max(as_int(data.get("invoice_amount", data.get("amount", 0))), 0)
    received = max(as_int(data.get("received_amount", data.get("amount", invoice))), 0)
    with get_db() as db, db.cursor() as cur:
        pct = as_float(data.get("company_share_percent"), finance_percent(cur))
        pct = max(0, min(100, pct if pct is not None else 50))
        company = round(received * pct / 100)
        balance = max(invoice - received, 0)
        cur.execute("""insert into service_visits(customer_id,registered_by,service_type,description,amount,invoice_amount,received_amount,company_share_percent,company_share_amount,customer_balance,payment_method,status,visited_at,next_service_at,visitor_code)
                       values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                    (cid,str(request.current_user.get("user_id")),data.get("service_type"),data.get("description"),received,invoice,received,pct,company,balance,data.get("payment_method"),data.get("status") or "completed",data.get("visited_at") or None,data.get("next_service_at") or None,data.get("visitor_code")))
        jid = cur.fetchone()["id"]
        audit(cur, "service_visit", jid, "create", after={"customer_id": str(cid), "invoice": invoice, "received": received, "company_share": company, "balance": balance})
    return jsonify({"id": str(jid), "invoice_amount": invoice, "received_amount": received, "company_share_amount": company, "customer_balance": balance}), 201


@app.patch("/api/jobs/<uuid:jid>")
@token_required
def job_update(jid):
    data = request.get_json() or {}
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from service_visits where id=%s", (jid,))
        before = cur.fetchone()
        if not before:
            return jsonify({"error": "سرویس پیدا نشد"}), 404
        invoice = max(as_int(data.get("invoice_amount", before["invoice_amount"])), 0)
        received = max(as_int(data.get("received_amount", before["received_amount"])), 0)
        pct = max(0, min(100, as_float(data.get("company_share_percent"), float(before["company_share_percent"]))))
        company, balance = round(received * pct / 100), max(invoice - received, 0)
        cur.execute("""update service_visits set service_type=%s,description=%s,invoice_amount=%s,received_amount=%s,amount=%s,company_share_percent=%s,company_share_amount=%s,customer_balance=%s,payment_method=%s,status=%s,visited_at=%s,next_service_at=%s,updated_at=now() where id=%s""",
                    (data.get("service_type",before["service_type"]),data.get("description",before["description"]),invoice,received,received,pct,company,balance,data.get("payment_method",before["payment_method"]),data.get("status",before["status"]),data.get("visited_at",before["visited_at"]),data.get("next_service_at",before["next_service_at"]),jid))
        audit(cur, "service_visit", jid, "update", before={"invoice": before["invoice_amount"], "received": before["received_amount"]}, after=data)
    return jsonify({"message": "سرویس ویرایش شد", "company_share_amount": company, "customer_balance": balance})


@app.get("/api/expenses")
@token_required
def expenses_list():
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from expenses order by expense_date desc,created_at desc")
        rows = cur.fetchall()
    return jsonify([{**row_json(r), "id": str(r["id"])} for r in rows])


@app.post("/api/expenses")
@token_required
def expense_create():
    data = request.get_json() or {}
    amount = as_int(data.get("amount"))
    if not data.get("title") or amount < 0:
        return jsonify({"error": "عنوان و مبلغ معتبر لازم است"}), 400
    with get_db() as db, db.cursor() as cur:
        cur.execute("insert into expenses(category,title,amount,expense_date,service_visit_id,customer_id,notes,created_by) values(%s,%s,%s,coalesce(%s::timestamptz,now()),%s,%s,%s,%s) returning id", (data.get("category") or "other",data.get("title"),amount,data.get("expense_date") or None,data.get("service_visit_id") or None,data.get("customer_id") or None,data.get("notes"),str(request.current_user.get("user_id"))))
        eid = cur.fetchone()["id"]
        audit(cur, "expense", eid, "create", after={"title": data.get("title"), "amount": amount, "category": data.get("category")})
    return jsonify({"id": str(eid), "message": "هزینه ثبت شد"}), 201


@app.delete("/api/expenses/<uuid:eid>")
@token_required
def expense_delete(eid):
    with get_db() as db, db.cursor() as cur:
        cur.execute("delete from expenses where id=%s returning id,title,amount", (eid,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "هزینه پیدا نشد"}), 404
        audit(cur, "expense", eid, "delete", before=row_json(row))
    return jsonify({"message": "هزینه حذف شد"})


@app.get("/api/settlements")
@token_required
def settlements_list():
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from company_settlements order by settled_at desc")
        rows = cur.fetchall()
    return jsonify([{**row_json(r), "id": str(r["id"])} for r in rows])


@app.post("/api/settlements")
@token_required
def settlement_create():
    data = request.get_json() or {}
    amount = as_int(data.get("amount"))
    if amount <= 0:
        return jsonify({"error": "مبلغ تسویه باید بیشتر از صفر باشد"}), 400
    with get_db() as db, db.cursor() as cur:
        cur.execute("insert into company_settlements(amount,settled_at,period_from,period_to,notes,created_by) values(%s,coalesce(%s::timestamptz,now()),%s,%s,%s,%s) returning id", (amount,data.get("settled_at") or None,data.get("period_from") or None,data.get("period_to") or None,data.get("notes"),str(request.current_user.get("user_id"))))
        sid = cur.fetchone()["id"]
        audit(cur, "settlement", sid, "create", after={"amount": amount})
    return jsonify({"id": str(sid), "message": "تسویه ثبت شد"}), 201


@app.get("/api/settings/finance")
@token_required
def finance_settings_get():
    with get_db() as db, db.cursor() as cur:
        return jsonify({"company_share_percent": finance_percent(cur)})


@app.patch("/api/settings/finance")
@token_required
def finance_settings_set():
    data = request.get_json() or {}
    pct = as_float(data.get("company_share_percent"))
    if pct is None or not 0 <= pct <= 100:
        return jsonify({"error": "درصد باید بین صفر تا صد باشد"}), 400
    with get_db() as db, db.cursor() as cur:
        cur.execute("insert into app_settings(key,value,updated_at) values('finance',%s,now()) on conflict(key) do update set value=excluded.value,updated_at=now()", (Jsonb({"company_share_percent": pct}),))
    return jsonify({"company_share_percent": pct})


@app.get("/api/reports/daily")
@token_required
def report_daily():
    days = max(1, min(as_int(request.args.get("days"), 31), 366))
    with get_db() as db, db.cursor() as cur:
        cur.execute("""
          with s as (
            select (coalesce(visited_at,created_at) at time zone 'Asia/Tehran')::date report_date,
                   count(*)::int services,coalesce(sum(invoice_amount),0)::bigint invoice,
                   coalesce(sum(received_amount),0)::bigint received,coalesce(sum(company_share_amount),0)::bigint company_share,
                   coalesce(sum(customer_balance),0)::bigint customer_balance
            from service_visits where coalesce(visited_at,created_at)>=now()-(%s * interval '1 day') group by 1
          ), e as (
            select (expense_date at time zone 'Asia/Tehran')::date report_date,coalesce(sum(amount),0)::bigint expenses
            from expenses where expense_date>=now()-(%s * interval '1 day') group by 1
          )
          select coalesce(s.report_date,e.report_date) report_date,coalesce(services,0) services,coalesce(invoice,0) invoice,
                 coalesce(received,0) received,coalesce(company_share,0) company_share,coalesce(customer_balance,0) customer_balance,
                 coalesce(expenses,0) expenses,coalesce(received,0)-coalesce(company_share,0)-coalesce(expenses,0) net_profit
          from s full join e using(report_date) order by report_date desc
        """, (days, days))
        rows = cur.fetchall()
    return jsonify([row_json(r) for r in rows])


@app.get("/api/reports/analytics")
@token_required
def report_analytics():
    with get_db() as db, db.cursor() as cur:
        cur.execute("select coalesce(sum(invoice_amount),0)::bigint invoice,coalesce(sum(received_amount),0)::bigint received,coalesce(sum(company_share_amount),0)::bigint company_share,coalesce(sum(customer_balance),0)::bigint customer_balance,count(*)::int services from service_visits")
        totals = row_json(cur.fetchone())
        cur.execute("select coalesce(sum(amount),0)::bigint expenses from expenses")
        expenses = cur.fetchone()["expenses"]
        cur.execute("select coalesce(sum(amount),0)::bigint settled from company_settlements")
        settled = cur.fetchone()["settled"]
        cur.execute("""select date_trunc('month',coalesce(visited_at,created_at) at time zone 'Asia/Tehran')::date month,coalesce(sum(received_amount),0)::bigint received,coalesce(sum(company_share_amount),0)::bigint company_share,count(*)::int services from service_visits where coalesce(visited_at,created_at)>=now()-interval '15 months' group by 1 order by 1""")
        months = [row_json(r) for r in cur.fetchall()]
        cur.execute("select date_trunc('month',expense_date at time zone 'Asia/Tehran')::date month,coalesce(sum(amount),0)::bigint expenses from expenses where expense_date>=now()-interval '15 months' group by 1 order by 1")
        expense_map = {str(r["month"]): r["expenses"] for r in cur.fetchall()}
        for month in months:
            month["expenses"] = expense_map.get(str(month["month"]), 0)
            month["net_profit"] = month["received"] - month["company_share"] - month["expenses"]
        cur.execute("select coalesce(service_type,'نامشخص') service_type,count(*)::int count,coalesce(sum(received_amount),0)::bigint received from service_visits group by service_type order by received desc limit 10")
        service_types = [row_json(r) for r in cur.fetchall()]
    totals["expenses"] = expenses
    totals["net_profit"] = totals["received"] - totals["company_share"] - expenses
    totals["settled_company"] = settled
    totals["company_due"] = max(totals["company_share"] - settled, 0)
    return jsonify({"totals": totals, "months": months, "service_types": service_types})


@app.get("/api/reminders")
@token_required
def reminders_list():
    days = max(1, min(as_int(request.args.get("days"), 30), 365))
    with get_db() as db, db.cursor() as cur:
        cur.execute("""select v.id,v.next_service_at,v.service_type,c.id customer_id,trim(concat_ws(' ',c.first_name,c.last_name)) name,(select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone,c.address from service_visits v join customers_v2 c on c.id=v.customer_id where v.next_service_at is not null and v.next_service_at<=now()+(%s * interval '1 day') order by v.next_service_at""", (days,))
        rows = cur.fetchall()
    return jsonify([{**row_json(r), "id": str(r["id"]), "customer_id": str(r["customer_id"])} for r in rows])


@app.get("/api/stats")
@token_required
def stats():
    with get_db() as db, db.cursor() as cur:
        cur.execute("select count(*)::int count,coalesce(sum(received_amount),0)::bigint received,coalesce(sum(company_share_amount),0)::bigint company_share from service_visits where (coalesce(visited_at,created_at) at time zone 'Asia/Tehran')::date=(now() at time zone 'Asia/Tehran')::date")
        today = row_json(cur.fetchone())
        cur.execute("select count(*)::int count from customers_v2 where archived=false")
        customers = cur.fetchone()["count"]
        cur.execute("select coalesce(sum(amount),0)::bigint expenses from expenses where (expense_date at time zone 'Asia/Tehran')::date=(now() at time zone 'Asia/Tehran')::date")
        expenses = cur.fetchone()["expenses"]
    today["expenses"] = expenses
    today["net_profit"] = today["received"] - today["company_share"] - expenses
    return jsonify({"today": today, "total_customers": customers})


@app.post("/api/smart/parse")
@token_required
def smart_parse():
    text = (request.get_json() or {}).get("text", "")
    if not text.strip():
        return jsonify({"error": "متن لازم است"}), 400
    return jsonify(parse_intake(text))


@app.post("/api/smart/register")
@token_required
def smart_register():
    data = request.get_json() or {}
    parsed = data.get("parsed") or parse_intake(data.get("text", ""))
    last = (parsed.get("last_name") or "").strip()
    if not last:
        return jsonify({"error": "نام خانوادگی تشخیص داده نشد"}), 400
    phones = [normalize_phone(x) for x in parsed.get("phones", [])]
    phones = [x for x in dict.fromkeys(phones) if x]
    lat, lng, acc = as_float(data.get("latitude")), as_float(data.get("longitude")), data.get("accuracy")
    selected = data.get("customer_id")
    with get_db() as db, db.cursor() as cur:
        cid = selected
        if not cid and phones:
            cur.execute("select distinct customer_id from customer_phones where phone=any(%s)", (phones,))
            matches = [str(r["customer_id"]) for r in cur.fetchall()]
            if len(matches) == 1:
                cid = matches[0]
            elif len(matches) > 1:
                return jsonify({"error": "شماره‌ها به چند مشتری متفاوت تعلق دارند", "needs_selection": True, "customer_ids": matches}), 409
        if not cid:
            # Same surname never auto-merges. A new independent customer is created unless exact phone match exists.
            if lat is not None and lng is not None:
                cur.execute("insert into customers_v2(last_name,normalized_name,address,map_label,location,location_accuracy_m,location_source,created_by) values(%s,%s,%s,%s,st_setsrid(st_makepoint(%s,%s),4326)::geography,%s,'gps',%s) returning id", (last,normalize_name(None,last),parsed.get("address"),last,lng,lat,acc,str(request.current_user.get("user_id"))))
            else:
                cur.execute("insert into customers_v2(last_name,normalized_name,address,map_label,created_by) values(%s,%s,%s,%s,%s) returning id", (last,normalize_name(None,last),parsed.get("address"),last,str(request.current_user.get("user_id"))))
            cid = cur.fetchone()["id"]
        for i, phone in enumerate(phones):
            cur.execute("select customer_id from customer_phones where phone=%s", (phone,))
            hit = cur.fetchone()
            if not hit:
                cur.execute("insert into customer_phones(customer_id,phone,is_primary) values(%s,%s,%s)", (cid,phone,i == 0))
            elif str(hit["customer_id"]) != str(cid):
                return jsonify({"error": f"شماره {phone} متعلق به مشتری دیگری است", "needs_selection": True, "existing_customer_id": str(hit["customer_id"])}), 409
        invoice = max(as_int(data.get("invoice_amount", parsed.get("amount") or 0)), 0)
        received = max(as_int(data.get("received_amount", parsed.get("amount") or invoice)), 0)
        pct = finance_percent(cur)
        company, balance = round(received * pct / 100), max(invoice - received, 0)
        if lat is not None and lng is not None:
            visit_sql, loc_params = "st_setsrid(st_makepoint(%s,%s),4326)::geography", [lng, lat]
        else:
            visit_sql, loc_params = "null", []
        params = [cid,str(request.current_user.get("user_id")),parsed.get("visitor_code"),parsed.get("service_type"),data.get("description") or parsed.get("service_type"),received,invoice,received,pct,company,balance,data.get("visited_at") or None] + loc_params + [parsed.get("raw_text") or data.get("text")]
        cur.execute(f"insert into service_visits(customer_id,registered_by,visitor_code,service_type,description,amount,invoice_amount,received_amount,company_share_percent,company_share_amount,customer_balance,status,visited_at,visit_location,raw_chat_input) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'registered',%s,{visit_sql},%s) returning id", params)
        vid = cur.fetchone()["id"]
        audit(cur, "service_visit", vid, "smart_create", after={"customer_id": str(cid), "received": received, "raw_text": data.get("text")})
    return jsonify({"customer_id": str(cid), "visit_id": str(vid), "parsed": parsed}), 201


@app.get("/api/customers/nearby")
@token_required
def customers_nearby():
    try:
        lat, lng = float(request.args["lat"]), float(request.args["lng"])
        radius = min(max(float(request.args.get("radius", 250)), 5), 5000)
    except (KeyError, ValueError):
        return jsonify({"error": "مختصات معتبر لازم است"}), 400
    with get_db() as db, db.cursor() as cur:
        cur.execute("""select c.id,c.first_name,c.last_name,c.map_label,c.address,c.location_accuracy_m,st_y(c.location::geometry) latitude,st_x(c.location::geometry) longitude,round(st_distance(c.location,st_setsrid(st_makepoint(%s,%s),4326)::geography)::numeric,1) distance_m,(select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone,(select received_amount from service_visits v where v.customer_id=c.id order by coalesce(v.visited_at,v.created_at) desc limit 1) last_amount,(select service_type from service_visits v where v.customer_id=c.id order by coalesce(v.visited_at,v.created_at) desc limit 1) last_service from customers_v2 c where c.archived=false and c.location is not null and st_dwithin(c.location,st_setsrid(st_makepoint(%s,%s),4326)::geography,%s) order by distance_m limit 50""", (lng,lat,lng,lat,radius))
        rows = cur.fetchall()
    return jsonify([{**row_json(r), "id": str(r["id"])} for r in rows])
