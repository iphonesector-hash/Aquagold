import os
import re
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
import psycopg
from psycopg.rows import dict_row
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

from smart_intake import parse_intake


def _database_url():
    preferred = ["AQUAGOLD_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL", "NEON_DATABASE_URL", "AQUAGOLD_URL"]
    for key in preferred:
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
allowed_origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "").split(",") if x.strip()]
if allowed_origins:
    CORS(app, origins=allowed_origins)
else:
    CORS(app)

def get_db():
    if not DATABASE_URL: raise RuntimeError("AquaGold database URL is not configured")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)

def normalize_name(first_name,last_name): return re.sub(r"\s+"," ",f"{first_name or ''} {last_name or ''}".strip().lower())
def create_token(user):
    now=datetime.now(timezone.utc); return jwt.encode({"user_id":user["id"],"role":user["role"],"iat":now,"exp":now+timedelta(hours=TOKEN_EXPIRY_HOURS)},SECRET_KEY,algorithm="HS256")
def token_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        auth=request.headers.get("Authorization","")
        if not auth.startswith("Bearer "): return jsonify({"error":"Authentication required"}),401
        try: request.current_user=jwt.decode(auth[7:],SECRET_KEY,algorithms=["HS256"])
        except jwt.PyJWTError: return jsonify({"error":"Token is invalid or expired"}),401
        return fn(*args,**kwargs)
    return wrapper

def bootstrap_admin_if_requested():
    username=os.getenv("AQUAGOLD_ADMIN_USERNAME"); password=os.getenv("AQUAGOLD_ADMIN_PASSWORD")
    if not DATABASE_URL or not username or not password: return
    with get_db() as db,db.cursor() as cur:
        cur.execute("select id from users where username=%s",(username,))
        if not cur.fetchone(): cur.execute("insert into users(username,password_hash,first_name,last_name,role,active) values(%s,%s,%s,%s,'superadmin',true)",(username,generate_password_hash(password),"مدیر","AquaGold"))
try: bootstrap_admin_if_requested()
except Exception: pass

@app.get("/")
def index(): return send_from_directory(".","index.html")
@app.get("/smart")
def smart_page(): return send_from_directory(".","smart.html")
@app.get("/health")
def health():
    if not DATABASE_URL: return jsonify({"status":"unhealthy","database":"not_configured"}),503
    try:
        with get_db() as db,db.cursor() as cur: cur.execute("select 1"); cur.fetchone()
        return jsonify({"status":"healthy","database":"neon"})
    except Exception as exc: return jsonify({"status":"unhealthy","error":str(exc)}),503
@app.post("/api/login")
def login():
    data=request.get_json() or {}
    with get_db() as db,db.cursor() as cur: cur.execute("select * from users where username=%s and active=true",(data.get("username",""),)); user=cur.fetchone()
    if not user or not check_password_hash(user["password_hash"],data.get("password","")): return jsonify({"error":"Invalid credentials"}),401
    return jsonify({"token":create_token(user),"user":{k:user[k] for k in ("id","username","first_name","last_name","role")}})
@app.post("/api/logout")
def logout(): return jsonify({"message":"Logged out successfully"})
@app.get("/api/stats")
@token_required
def stats():
    with get_db() as db,db.cursor() as cur:
        cur.execute("select count(*)::int count,coalesce(sum(amount),0)::bigint total from service_visits where created_at::date=current_date"); today=cur.fetchone(); cur.execute("select count(*)::int count from customers_v2"); customers=cur.fetchone()["count"]; cur.execute("select count(*)::int count from inventory where quantity<=min_quantity and quantity>0"); low=cur.fetchone()["count"]; cur.execute("select count(*)::int count from inventory where quantity=0"); out=cur.fetchone()["count"]
    return jsonify({"today":today,"total_customers":customers,"low_stock":low,"out_of_stock":out})
def customer_payload(row):
    phones=row.get("phones") or []; name=" ".join([x for x in [row.get("first_name"),row.get("last_name")] if x]).strip()
    return {"id":str(row["id"]),"name":name,"first_name":row.get("first_name"),"last_name":row.get("last_name"),"phone":phones[0] if phones else None,"phones":phones,"address":row.get("address"),"device_model":row.get("device_model"),"notes":row.get("notes"),"created_at":row.get("created_at"),"latitude":row.get("latitude"),"longitude":row.get("longitude"),"location_accuracy_m":row.get("location_accuracy_m")}
@app.get("/api/customers")
@token_required
def list_customers():
    with get_db() as db,db.cursor() as cur: cur.execute("select c.*,case when c.location is null then null else st_y(c.location::geometry) end latitude,case when c.location is null then null else st_x(c.location::geometry) end longitude,coalesce(array_agg(p.phone order by p.is_primary desc,p.id) filter(where p.phone is not null),'{}') phones from customers_v2 c left join customer_phones p on p.customer_id=c.id group by c.id order by c.created_at desc"); rows=cur.fetchall()
    return jsonify([customer_payload(r) for r in rows])
@app.post("/api/customers")
@token_required
def create_customer():
    data=request.get_json() or {}; first=(data.get("first_name") or "").strip() or None; last=(data.get("last_name") or data.get("name") or "").strip()
    if not last:return jsonify({"error":"name is required"}),400
    phones=data.get("phones") or ([data.get("phone")] if data.get("phone") else []); lat,lng=data.get("latitude"),data.get("longitude"); loc_sql="st_setsrid(st_makepoint(%s,%s),4326)::geography" if lat is not None and lng is not None else "null"; params=[first,last,normalize_name(first,last),data.get("address")]
    if lat is not None and lng is not None: params += [float(lng),float(lat)]
    params += [data.get("location_accuracy_m"),data.get("device_model"),data.get("notes"),str(request.current_user.get("user_id"))]; sql=f"insert into customers_v2(first_name,last_name,normalized_name,address,location,location_accuracy_m,device_model,notes,created_by) values(%s,%s,%s,%s,{loc_sql},%s,%s,%s,%s) returning id"
    with get_db() as db,db.cursor() as cur:
        cur.execute(sql,params); cid=cur.fetchone()["id"]
        for i,phone in enumerate(phones):
            if phone: cur.execute("insert into customer_phones(customer_id,phone,is_primary) values(%s,%s,%s) on conflict(customer_id,phone) do nothing",(cid,str(phone),i==0))
    return jsonify({"id":str(cid),"message":"Customer created"}),201
@app.get("/api/jobs")
@token_required
def jobs():
    with get_db() as db,db.cursor() as cur: cur.execute("select v.id,v.customer_id,v.service_type as description,v.amount,v.status,v.created_at,coalesce(v.visited_at,v.created_at) date,c.address,c.device_model,trim(concat_ws(' ',c.first_name,c.last_name)) name,(select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone from service_visits v join customers_v2 c on c.id=v.customer_id order by v.created_at desc"); rows=cur.fetchall()
    return jsonify([{**r,"id":str(r["id"]),"customer_id":str(r["customer_id"])} for r in rows])
@app.post("/api/jobs")
@token_required
def create_job():
    data=request.get_json() or {}; cid=data.get("customer_id")
    if not cid:return jsonify({"error":"customer_id required"}),400
    with get_db() as db,db.cursor() as cur: cur.execute("insert into service_visits(customer_id,registered_by,service_type,description,amount,status,visited_at) values(%s,%s,%s,%s,%s,%s,%s) returning id",(cid,str(request.current_user.get("user_id")),data.get("service_type"),data.get("description"),int(data.get("amount") or 0),data.get("status") or "registered",data.get("visited_at"))); jid=cur.fetchone()["id"]
    return jsonify({"id":str(jid),"message":"Job created"}),201
@app.get("/api/inventory")
@token_required
def inventory_list():
    with get_db() as db,db.cursor() as cur: cur.execute("select * from inventory order by created_at desc"); rows=cur.fetchall()
    return jsonify(rows)
@app.post("/api/smart/parse")
@token_required
def smart_parse():
    text=(request.get_json() or {}).get("text","")
    if not text.strip():return jsonify({"error":"text is required"}),400
    return jsonify(parse_intake(text))
@app.post("/api/smart/register")
@token_required
def smart_register():
    data=request.get_json() or {}; parsed=data.get("parsed") or parse_intake(data.get("text","")); last=(parsed.get("last_name") or "").strip()
    if not last:return jsonify({"error":"customer last name could not be detected"}),400
    phones=parsed.get("phones") or []; lat,lng,acc=data.get("latitude"),data.get("longitude"),data.get("accuracy")
    with get_db() as db,db.cursor() as cur:
        cid=None
        for phone in phones:
            cur.execute("select customer_id from customer_phones where phone=%s limit 1",(phone,)); hit=cur.fetchone()
            if hit: cid=hit["customer_id"]; break
        if cid is None:
            if lat is not None and lng is not None: cur.execute("insert into customers_v2(last_name,normalized_name,address,location,location_accuracy_m,created_by) values(%s,%s,%s,st_setsrid(st_makepoint(%s,%s),4326)::geography,%s,%s) returning id",(last,normalize_name(None,last),parsed.get("address"),float(lng),float(lat),acc,str(request.current_user.get("user_id"))))
            else: cur.execute("insert into customers_v2(last_name,normalized_name,address,created_by) values(%s,%s,%s,%s) returning id",(last,normalize_name(None,last),parsed.get("address"),str(request.current_user.get("user_id"))))
            cid=cur.fetchone()["id"]
        for i,phone in enumerate(phones): cur.execute("insert into customer_phones(customer_id,phone,is_primary) values(%s,%s,%s) on conflict(customer_id,phone) do nothing",(cid,phone,i==0))
        visit_loc="st_setsrid(st_makepoint(%s,%s),4326)::geography" if lat is not None and lng is not None else "null"; params=[cid,str(request.current_user.get("user_id")),parsed.get("visitor_code"),parsed.get("service_type"),data.get("description") or parsed.get("service_type"),int(parsed.get("amount") or 0),data.get("visited_at")]
        if lat is not None and lng is not None: params += [float(lng),float(lat)]
        params += [parsed.get("raw_text") or data.get("text")]; cur.execute(f"insert into service_visits(customer_id,registered_by,visitor_code,service_type,description,amount,status,visited_at,visit_location,raw_chat_input) values(%s,%s,%s,%s,%s,%s,'registered',%s,{visit_loc},%s) returning id",params); vid=cur.fetchone()["id"]
    return jsonify({"customer_id":str(cid),"visit_id":str(vid),"parsed":parsed}),201
@app.get("/api/customers/nearby")
@token_required
def nearby():
    try: lat=float(request.args["lat"]); lng=float(request.args["lng"]); radius=min(float(request.args.get("radius",100)),5000)
    except (KeyError,ValueError):return jsonify({"error":"lat/lng are required"}),400
    with get_db() as db,db.cursor() as cur: cur.execute("select c.id,c.first_name,c.last_name,c.address,round(st_distance(c.location,st_setsrid(st_makepoint(%s,%s),4326)::geography)::numeric,1) distance_m,(select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone,(select amount from service_visits v where v.customer_id=c.id order by coalesce(v.visited_at,v.created_at) desc limit 1) last_amount from customers_v2 c where c.location is not null and st_dwithin(c.location,st_setsrid(st_makepoint(%s,%s),4326)::geography,%s) order by distance_m limit 20",(lng,lat,lng,lat,radius)); rows=cur.fetchall()
    return jsonify([{**r,"id":str(r["id"])} for r in rows])
