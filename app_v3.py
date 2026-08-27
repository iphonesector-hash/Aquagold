import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import wraps
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from flask import Flask, jsonify, make_response, request, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from aquagold_validation import (
    ValidationError,
    boolean as valid_boolean,
    choice as valid_choice,
    coordinates as valid_coordinates,
    decimal_number as valid_decimal,
    integer as valid_integer,
    phones as valid_phones,
    text as valid_text,
    timestamp as valid_timestamp,
    uuid as valid_uuid,
)
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


def _pooled_database_url(value):
    """Prefer Neon's PgBouncer endpoint in bursty serverless runtimes."""
    if not value or os.getenv("AQUAGOLD_DISABLE_POOLER") == "1":
        return value
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if ".neon.tech" not in host or host.split(".", 1)[0].endswith("-pooler"):
        return value
    pooled_host = host.replace(".neon.tech", "-pooler.neon.tech", 1)
    netloc = parsed.netloc.replace(host, pooled_host, 1)
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


DATABASE_URL = _pooled_database_url(_database_url())
APP_ENV = (os.getenv("AQUAGOLD_ENV") or os.getenv("VERCEL_ENV") or "development").lower()
IS_PRODUCTION = APP_ENV in {"production", "prod"}
SECRET_KEY = os.getenv("AQUAGOLD_SECRET_KEY") or os.getenv("SECRET_KEY") or ""
if IS_PRODUCTION and (len(SECRET_KEY) < 32 or SECRET_KEY == "aquagold-local-dev-only"):
    raise RuntimeError("AQUAGOLD_SECRET_KEY must be a unique value of at least 32 characters in production")
if not SECRET_KEY:
    SECRET_KEY = "aquagold-local-dev-only"

SESSION_COOKIE = "aquagold_session"
CSRF_COOKIE = "aquagold_csrf"
SESSION_HOURS = max(1, min(int(os.getenv("AQUAGOLD_SESSION_HOURS", "24")), 168))
COOKIE_SECURE = IS_PRODUCTION or os.getenv("AQUAGOLD_SECURE_COOKIE") == "1"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ROLE_LEVELS = {"viewer": 10, "technician": 20, "admin": 30, "superadmin": 40}
logger = logging.getLogger("aquagold")

app = Flask(__name__, static_folder=".", static_url_path="")
app.config.update(
    SECRET_KEY=SECRET_KEY,
    MAX_CONTENT_LENGTH=int(os.getenv("AQUAGOLD_MAX_REQUEST_BYTES", str(2 * 1024 * 1024))),
    JSON_SORT_KEYS=False,
)
origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "").split(",") if x.strip()]
if origins:
    CORS(app, origins=origins, supports_credentials=True, allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"])
elif not IS_PRODUCTION:
    CORS(app, origins=[r"http://localhost:\d+", r"http://127\.0\.0\.1:\d+"], supports_credentials=True)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    default_limits=[os.getenv("AQUAGOLD_GLOBAL_RATE_LIMIT", "600 per hour")],
)


@app.errorhandler(ValidationError)
def validation_error(exc):
    return jsonify({"error": str(exc)}), 400


@app.errorhandler(psycopg.errors.UniqueViolation)
def unique_violation(_exc):
    return jsonify({"error": "اطلاعات تکراری است؛ شماره تلفن یا شناسه قبلاً ثبت شده"}), 409


@app.errorhandler(413)
def request_too_large(_exc):
    return jsonify({"error": "حجم درخواست بیش از حد مجاز است"}), 413


@app.errorhandler(HTTPException)
def http_error(exc):
    if request.path.startswith("/api/") or request.path == "/health":
        return jsonify({"error": exc.description or "درخواست نامعتبر است"}), exc.code
    return exc


@app.errorhandler(Exception)
def unexpected_error(exc):
    logger.exception("unhandled_request_error: %s", exc)
    if request.path.startswith("/api/") or request.path == "/health":
        return jsonify({"error": "خطای داخلی سرویس"}), 500
    return "Internal Server Error", 500


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


def pagination_args(*, default_per_page=100, max_per_page=250):
    page = valid_integer(request.args.get("page"), "صفحه", minimum=1, maximum=1_000_000, default=1)
    per_page = valid_integer(
        request.args.get("per_page"), "تعداد هر صفحه", minimum=1,
        maximum=max_per_page, default=default_per_page,
    )
    return page, per_page, (page - 1) * per_page


def paginated(items, total, page, per_page):
    pages = max(1, (total + per_page - 1) // per_page)
    return jsonify({
        "items": items,
        "pagination": {"page": page, "per_page": per_page, "total": total, "pages": pages},
    })


def row_json(row):
    out = {}
    for k, v in dict(row).items():
        if isinstance(v, Decimal):
            v = float(v)
        elif isinstance(v, UUID):
            v = str(v)
        out[k] = v
    return out


def _sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_session(cur, user):
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    cur.execute(
        """insert into auth_sessions(user_id,token_hash,csrf_hash,expires_at,user_agent,ip_address)
           values(%s,%s,%s,%s,%s,%s) returning id""",
        (
            user["id"], _sha256(token), _sha256(csrf), expires_at,
            (request.user_agent.string or "")[:500], (request.headers.get("X-Forwarded-For") or request.remote_addr or "")[:100],
        ),
    )
    return token, csrf, expires_at


def _request_token():
    cookie_token = request.cookies.get(SESSION_COOKIE)
    if cookie_token:
        return cookie_token, True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and os.getenv("AQUAGOLD_ALLOW_BEARER_TOKENS") == "1":
        return auth[7:].strip(), False
    return None, False


def _idempotency_begin(user_id):
    raw_key = request.headers.get("Idempotency-Key")
    if not raw_key or request.method in SAFE_METHODS or request.path in {"/api/smart/parse", "/api/route/optimize"}:
        return None, None
    key = valid_uuid(raw_key, "کلید تکرارناپذیری")
    request_hash = _sha256(f"{request.method}:{request.path}:" + request.get_data(cache=True, as_text=True))
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            """insert into api_idempotency(user_id,idempotency_key,request_path,request_hash)
               values(%s,%s,%s,%s) on conflict do nothing returning idempotency_key""",
            (user_id, key, request.path, request_hash),
        )
        inserted = cur.fetchone()
        if inserted:
            return key, None
        cur.execute(
            """select request_path,request_hash,status_code,response_body
               from api_idempotency where user_id=%s and idempotency_key=%s and expires_at>now()""",
            (user_id, key),
        )
        row = cur.fetchone()
    if not row:
        raise ValidationError("کلید تکرارناپذیری منقضی شده است")
    if row["request_path"] != request.path or row["request_hash"] != request_hash:
        return key, (jsonify({"error": "این کلید برای درخواست متفاوتی استفاده شده است"}), 409)
    if row["status_code"] is None:
        return key, (jsonify({"error": "این درخواست در حال پردازش است"}), 409)
    response = jsonify(row["response_body"] or {})
    response.status_code = row["status_code"]
    response.headers["Idempotency-Replayed"] = "true"
    return key, response


def _idempotency_finish(user_id, key, response):
    if not key:
        return
    if response.status_code >= 500:
        _idempotency_abort(user_id, key)
        return
    body = response.get_json(silent=True)
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            """update api_idempotency set status_code=%s,response_body=%s
               where user_id=%s and idempotency_key=%s""",
            (response.status_code, Jsonb(body if isinstance(body, (dict, list)) else {}), user_id, key),
        )


def _idempotency_abort(user_id, key):
    if not key:
        return
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            "delete from api_idempotency where user_id=%s and idempotency_key=%s and status_code is null",
            (user_id, key),
        )


def token_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token, via_cookie = _request_token()
        if not token:
            return jsonify({"error": "Authentication required"}), 401
        try:
            with get_db() as db, db.cursor() as cur:
                cur.execute(
                    """select s.id session_id,s.csrf_hash,s.expires_at,u.id user_id,u.username,u.first_name,u.last_name,u.role
                       from auth_sessions s join users u on u.id=s.user_id
                       where s.token_hash=%s and s.revoked_at is null and s.expires_at>now() and u.active=true""",
                    (_sha256(token),),
                )
                session = cur.fetchone()
        except Exception:
            logger.exception("session_lookup_failed")
            return jsonify({"error": "Authentication service unavailable"}), 503
        if not session:
            return jsonify({"error": "Token is invalid or expired"}), 401
        if via_cookie and request.method not in SAFE_METHODS:
            supplied = request.headers.get("X-CSRF-Token", "")
            if not supplied or not hmac.compare_digest(_sha256(supplied), session["csrf_hash"]):
                return jsonify({"error": "CSRF validation failed"}), 403
        request.current_user = {
            "user_id": str(session["user_id"]), "username": session["username"],
            "first_name": session["first_name"], "last_name": session["last_name"],
            "role": session["role"], "session_id": str(session["session_id"]),
            "expires_at": session["expires_at"],
        }
        idem_key, replay = _idempotency_begin(session["user_id"])
        if replay is not None:
            return replay
        try:
            response = make_response(fn(*args, **kwargs))
        except Exception:
            _idempotency_abort(session["user_id"], idem_key)
            raise
        _idempotency_finish(session["user_id"], idem_key, response)
        return response
    return wrapper


def roles_required(*roles):
    minimum = min(ROLE_LEVELS[role] for role in roles)

    def decorator(fn):
        @token_required
        @wraps(fn)
        def wrapper(*args, **kwargs):
            role = request.current_user.get("role", "viewer")
            if ROLE_LEVELS.get(role, 0) < minimum:
                return jsonify({"error": "دسترسی کافی ندارید"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


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
    if len(password) < 12:
        raise RuntimeError("AQUAGOLD_ADMIN_PASSWORD must be at least 12 characters")
    with get_db() as db, db.cursor() as cur:
        cur.execute("select id from users where username=%s", (username,))
        if not cur.fetchone():
            cur.execute("insert into users(username,password_hash,first_name,last_name,role,active) values(%s,%s,%s,%s,'superadmin',true)", (username, generate_password_hash(password), "مدیر", "AquaGold"))


try:
    bootstrap_admin_if_requested()
except Exception:
    logger.exception("bootstrap_admin_failed")


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
        return jsonify({"status": "healthy", "database": "neon", "version": "v5"})
    except Exception:
        logger.exception("health_database_check_failed")
        return jsonify({"status": "unhealthy", "database": "unavailable"}), 503


@app.post("/api/login")
@limiter.limit(os.getenv("AQUAGOLD_LOGIN_RATE_LIMIT", "5 per minute; 20 per hour"))
def login():
    data = request.get_json() or {}
    username = str(data.get("username") or "").strip()[:100]
    password = str(data.get("password") or "")
    if not username or not password or len(password) > 256:
        return jsonify({"error": "Invalid credentials"}), 401
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from users where username=%s and active=true", (username,))
        user = cur.fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "Invalid credentials"}), 401
        token, csrf, expires_at = create_session(cur, user)
    payload = {
        "csrf_token": csrf,
        "expires_at": expires_at.isoformat(),
        "user": {k: user[k] for k in ("id", "username", "first_name", "last_name", "role")},
    }
    response = make_response(jsonify(payload))
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True,
        secure=COOKIE_SECURE, samesite="Strict", path="/",
    )
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=SESSION_HOURS * 3600, httponly=False,
        secure=COOKIE_SECURE, samesite="Strict", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/session")
@token_required
def session_status():
    user = {k: request.current_user.get(k) for k in ("user_id", "username", "first_name", "last_name", "role")}
    user["id"] = user.pop("user_id")
    return jsonify({"authenticated": True, "user": user, "expires_at": request.current_user["expires_at"].isoformat()})


@app.post("/api/logout")
@token_required
def logout():
    with get_db() as db, db.cursor() as cur:
        cur.execute("update auth_sessions set revoked_at=now() where id=%s", (request.current_user["session_id"],))
    response = make_response(jsonify({"message": "Logged out"}))
    response.delete_cookie(SESSION_COOKIE, path="/", secure=COOKIE_SECURE, samesite="Strict")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=COOKIE_SECURE, samesite="Strict")
    response.headers["Clear-Site-Data"] = '"cache", "storage"'
    return response


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(self)")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
        "img-src 'self' data: blob: https:; font-src 'self'; "
        "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "connect-src 'self' https://tile.openstreetmap.org; worker-src 'self' blob:; manifest-src 'self'",
    )
    if request.path.startswith("/api/") or request.path == "/health":
        response.headers.setdefault("Cache-Control", "no-store")
    if IS_PRODUCTION:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


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
    q = valid_text(request.args.get("q"), "جست‌وجو", max_length=160) or ""
    page, per_page, offset = pagination_args()
    with get_db() as db, db.cursor() as cur:
        where = """(%s or c.archived=false) and (%s='' or c.normalized_name ilike '%%'||%s||'%%'
                   or coalesce(c.address,'') ilike '%%'||%s||'%%' or coalesce(c.map_label,'') ilike '%%'||%s||'%%'
                   or exists(select 1 from customer_phones px where px.customer_id=c.id and px.phone ilike '%%'||%s||'%%'))"""
        params = (include_archived, q, q, q, q, q)
        cur.execute(f"select count(*)::int total from customers_v2 c where {where}", params)
        total = cur.fetchone()["total"]
        cur.execute("""
            select c.*,case when c.location is null then null else st_y(c.location::geometry) end latitude,
                   case when c.location is null then null else st_x(c.location::geometry) end longitude,
                   coalesce(array_agg(p.phone order by p.is_primary desc,p.id) filter(where p.phone is not null),'{}') phones,
                   (select count(*)::int from service_visits vx where vx.customer_id=c.id) service_count,
                   (select coalesce(sum(vx.received_amount),0)::bigint from service_visits vx where vx.customer_id=c.id) total_received,
                   (select coalesce(sum(vx.customer_balance),0)::bigint from service_visits vx where vx.customer_id=c.id) total_balance
            from customers_v2 c left join customer_phones p on p.customer_id=c.id
            where """ + where + """
            group by c.id order by c.created_at desc limit %s offset %s
        """, params + (per_page, offset))
        rows = cur.fetchall()
    return paginated([customer_payload(r) for r in rows], total, page, per_page)


@app.post("/api/customers")
@roles_required("technician")
def customer_create():
    data = request.get_json() or {}
    client_id = valid_uuid(data.get("client_id"), "شناسه آفلاین مشتری", required=False)
    first = valid_text(data.get("first_name"), "نام", max_length=100)
    last = valid_text(data.get("last_name") or data.get("name"), "نام خانوادگی", required=True, max_length=160)
    phones = valid_phones(data.get("phones", []))
    lat, lng = valid_coordinates(data.get("latitude"), data.get("longitude"))
    address = valid_text(data.get("address"), "آدرس", max_length=1500)
    map_label = valid_text(data.get("map_label"), "نام روی نقشه", max_length=160) or f"{first or ''} {last}".strip()
    unit_no = valid_text(data.get("unit_no"), "واحد", max_length=50)
    plaque = valid_text(data.get("plaque"), "پلاک", max_length=50)
    device_model = valid_text(data.get("device_model"), "مدل دستگاه", max_length=200)
    notes = valid_text(data.get("notes"), "یادداشت", max_length=4000)
    with get_db() as db, db.cursor() as cur:
        if phones:
            cur.execute("select phone,customer_id from customer_phones where phone=any(%s) limit 1", (phones,))
            hit = cur.fetchone()
            if hit:
                return jsonify({"error": "این شماره قبلاً برای مشتری دیگری ثبت شده", "phone": hit["phone"], "existing_customer_id": str(hit["customer_id"])}), 409
        common = (first,last,normalize_name(first,last),address,map_label,unit_no,plaque,device_model,notes,str(request.current_user.get("user_id")))
        if lat is not None and lng is not None:
            cur.execute("""insert into customers_v2(id,first_name,last_name,normalized_name,address,map_label,unit_no,plaque,device_model,notes,created_by,location,location_accuracy_m,location_source)
                           values(coalesce(%s::uuid,gen_random_uuid()),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,st_setsrid(st_makepoint(%s,%s),4326)::geography,%s,%s) returning id""", (client_id,) + common + (lng,lat,as_float(data.get("location_accuracy_m")),valid_choice(data.get("location_source"),"منبع موقعیت",{"gps","map","drag","manual","geocoded"},default="gps")))
        else:
            cur.execute("""insert into customers_v2(id,first_name,last_name,normalized_name,address,map_label,unit_no,plaque,device_model,notes,created_by)
                           values(coalesce(%s::uuid,gen_random_uuid()),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""", (client_id,) + common)
        cid = cur.fetchone()["id"]
        for i, phone in enumerate(phones):
            cur.execute("insert into customer_phones(customer_id,phone,is_primary) values(%s,%s,%s)", (cid, phone, i == 0))
        audit(cur, "customer", cid, "create", after={"name": f"{first or ''} {last}".strip(), "phones": phones, "address": address})
    return jsonify({"id": str(cid), "message": "مشتری ثبت شد"}), 201


@app.patch("/api/customers/<uuid:cid>")
@roles_required("technician")
def customer_update(cid):
    data = request.get_json() or {}
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from customers_v2 where id=%s", (cid,))
        before = cur.fetchone()
        if not before:
            return jsonify({"error": "مشتری پیدا نشد"}), 404
        if "phones" in data:
            phones = valid_phones(data.get("phones", []))
            if phones:
                cur.execute("select phone,customer_id from customer_phones where phone=any(%s) and customer_id<>%s limit 1", (phones, cid))
                conflict = cur.fetchone()
                if conflict:
                    return jsonify({"error": "یکی از شماره‌ها متعلق به مشتری دیگری است", "phone": conflict["phone"], "existing_customer_id": str(conflict["customer_id"])}), 409
        else:
            phones = None
        first = valid_text(data.get("first_name", before["first_name"]), "نام", max_length=100)
        last = valid_text(data.get("last_name", before["last_name"]), "نام خانوادگی", required=True, max_length=160)
        address = valid_text(data.get("address", before["address"]), "آدرس", max_length=1500)
        map_label = valid_text(data.get("map_label", before["map_label"]), "نام روی نقشه", max_length=160)
        unit_no = valid_text(data.get("unit_no", before["unit_no"]), "واحد", max_length=50)
        plaque = valid_text(data.get("plaque", before["plaque"]), "پلاک", max_length=50)
        device_model = valid_text(data.get("device_model", before["device_model"]), "مدل دستگاه", max_length=200)
        notes = valid_text(data.get("notes", before["notes"]), "یادداشت", max_length=4000)
        archived = valid_boolean(data.get("archived"), before["archived"])
        cur.execute("""update customers_v2 set first_name=%s,last_name=%s,normalized_name=%s,address=%s,map_label=%s,unit_no=%s,plaque=%s,device_model=%s,notes=%s,archived=%s,updated_at=now() where id=%s""",
                    (first,last,normalize_name(first,last),address,map_label,unit_no,plaque,device_model,notes,archived,cid))
        if phones is not None:
            cur.execute("delete from customer_phones where customer_id=%s", (cid,))
            for i, phone in enumerate(phones):
                cur.execute("insert into customer_phones(customer_id,phone,is_primary) values(%s,%s,%s)", (cid, phone, i == 0))
        audit(cur, "customer", cid, "update", before={"first_name": before["first_name"], "last_name": before["last_name"], "address": before["address"]}, after=data)
    return jsonify({"message": "اطلاعات مشتری ویرایش شد"})


@app.patch("/api/customers/<uuid:cid>/location")
@roles_required("technician")
def customer_location(cid):
    data = request.get_json() or {}
    lat, lng = valid_coordinates(data.get("latitude"), data.get("longitude"), required=True)
    source = valid_choice(data.get("source"), "منبع موقعیت", {"gps", "map", "drag", "manual", "geocoded"}, default="manual")
    with get_db() as db, db.cursor() as cur:
        cur.execute("select id,case when location is null then null else st_y(location::geometry) end latitude,case when location is null then null else st_x(location::geometry) end longitude from customers_v2 where id=%s", (cid,))
        before = cur.fetchone()
        if not before:
            return jsonify({"error": "مشتری پیدا نشد"}), 404
        cur.execute("update customers_v2 set location=st_setsrid(st_makepoint(%s,%s),4326)::geography,location_accuracy_m=%s,location_source=%s,updated_at=now() where id=%s", (lng,lat,as_float(data.get("accuracy")),source,cid))
        audit(cur, "customer", cid, "location_update", before={"latitude": before["latitude"], "longitude": before["longitude"]}, after={"latitude": lat, "longitude": lng, "source": source})
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
    q = valid_text(request.args.get("q"), "جست‌وجو", max_length=160) or ""
    page, per_page, offset = pagination_args()
    with get_db() as db, db.cursor() as cur:
        where = """(%s='' or c.normalized_name ilike '%%'||%s||'%%' or coalesce(c.address,'') ilike '%%'||%s||'%%'
                    or coalesce(v.description,'') ilike '%%'||%s||'%%' or coalesce(v.service_type,'') ilike '%%'||%s||'%%'
                    or exists(select 1 from customer_phones px where px.customer_id=c.id and px.phone ilike '%%'||%s||'%%'))"""
        params = (q, q, q, q, q, q)
        cur.execute(f"select count(*)::int total from service_visits v join customers_v2 c on c.id=v.customer_id where {where}", params)
        total = cur.fetchone()["total"]
        cur.execute("""select v.id,v.customer_id,v.service_type,v.description,v.amount,v.invoice_amount,v.received_amount,v.company_share_percent,v.company_share_amount,v.customer_balance,v.overpayment_amount,v.payment_method,v.status,v.next_service_at,v.visitor_code,v.created_at,coalesce(v.visited_at,v.created_at) date,c.address,c.device_model,c.map_label,trim(concat_ws(' ',c.first_name,c.last_name)) name,(select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone from service_visits v join customers_v2 c on c.id=v.customer_id where """ + where + """ order by coalesce(v.visited_at,v.created_at) desc limit %s offset %s""", params + (per_page, offset))
        rows = cur.fetchall()
    items = [{**row_json(r), "id": str(r["id"]), "customer_id": str(r["customer_id"])} for r in rows]
    return paginated(items, total, page, per_page)


@app.get("/api/customers/<uuid:cid>/jobs")
@token_required
def customer_jobs(cid):
    page, per_page, offset = pagination_args(default_per_page=50, max_per_page=100)
    with get_db() as db, db.cursor() as cur:
        cur.execute("select count(*)::int total from service_visits where customer_id=%s", (cid,))
        total = cur.fetchone()["total"]
        cur.execute(
            """select v.*,coalesce(v.visited_at,v.created_at) date
               from service_visits v where customer_id=%s
               order by coalesce(v.visited_at,v.created_at) desc limit %s offset %s""",
            (cid, per_page, offset),
        )
        rows = cur.fetchall()
    return paginated([row_json(row) for row in rows], total, page, per_page)


@app.post("/api/jobs")
@roles_required("technician")
def job_create():
    data = request.get_json() or {}
    client_id = valid_uuid(data.get("client_id"), "شناسه آفلاین سرویس", required=False)
    cid = valid_uuid(data.get("customer_id"), "شناسه مشتری")
    invoice = valid_integer(data.get("invoice_amount", data.get("amount", 0)), "مبلغ فاکتور", default=0)
    received = valid_integer(data.get("received_amount", data.get("amount", invoice)), "مبلغ دریافتی", default=invoice)
    service_type = valid_text(data.get("service_type"), "نوع سرویس", max_length=200)
    description = valid_text(data.get("description"), "شرح سرویس", max_length=4000)
    payment_method = valid_choice(data.get("payment_method"), "روش پرداخت", {"cash", "card", "transfer", "cheque", "credit", "other", ""}, default="") or None
    status = valid_choice(data.get("status"), "وضعیت سرویس", {"scheduled", "registered", "completed", "revisit", "cancelled", "unpaid", "partial"}, default="completed")
    visited_at = valid_timestamp(data.get("visited_at"), "زمان مراجعه")
    next_service_at = valid_timestamp(data.get("next_service_at"), "زمان سرویس بعدی")
    visitor_code = valid_text(data.get("visitor_code"), "کد ویزیتور", max_length=100)
    with get_db() as db, db.cursor() as cur:
        cur.execute("select 1 from customers_v2 where id=%s and archived=false", (cid,))
        if not cur.fetchone():
            return jsonify({"error": "مشتری پیدا نشد یا بایگانی شده است"}), 404
        pct = valid_decimal(data.get("company_share_percent"), "درصد سهم شرکت", default=finance_percent(cur))
        company = round(received * float(pct) / 100)
        balance = max(invoice - received, 0)
        overpayment = max(received - invoice, 0)
        cur.execute("""insert into service_visits(id,customer_id,registered_by,service_type,description,amount,invoice_amount,received_amount,company_share_percent,company_share_amount,customer_balance,overpayment_amount,payment_method,status,visited_at,next_service_at,visitor_code)
                       values(coalesce(%s::uuid,gen_random_uuid()),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                    (client_id,cid,str(request.current_user.get("user_id")),service_type,description,received,invoice,received,pct,company,balance,overpayment,payment_method,status,visited_at,next_service_at,visitor_code))
        jid = cur.fetchone()["id"]
        audit(cur, "service_visit", jid, "create", after={"customer_id": str(cid), "invoice": invoice, "received": received, "company_share": company, "balance": balance})
    return jsonify({"id": str(jid), "invoice_amount": invoice, "received_amount": received, "company_share_amount": company, "customer_balance": balance, "overpayment_amount": overpayment}), 201


@app.patch("/api/jobs/<uuid:jid>")
@roles_required("technician")
def job_update(jid):
    data = request.get_json() or {}
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from service_visits where id=%s", (jid,))
        before = cur.fetchone()
        if not before:
            return jsonify({"error": "سرویس پیدا نشد"}), 404
        invoice = valid_integer(data.get("invoice_amount", before["invoice_amount"]), "مبلغ فاکتور", default=0)
        received = valid_integer(data.get("received_amount", before["received_amount"]), "مبلغ دریافتی", default=0)
        pct = valid_decimal(data.get("company_share_percent", before["company_share_percent"]), "درصد سهم شرکت", default=before["company_share_percent"])
        company, balance = round(received * float(pct) / 100), max(invoice - received, 0)
        overpayment = max(received - invoice, 0)
        service_type = valid_text(data.get("service_type", before["service_type"]), "نوع سرویس", max_length=200)
        description = valid_text(data.get("description", before["description"]), "شرح سرویس", max_length=4000)
        payment_method = valid_choice(data.get("payment_method", before["payment_method"]), "روش پرداخت", {"cash", "card", "transfer", "cheque", "credit", "other", ""}, default="") or None
        status = valid_choice(data.get("status", before["status"]), "وضعیت سرویس", {"scheduled", "registered", "completed", "revisit", "cancelled", "unpaid", "partial"}, default="completed")
        visited_at = valid_timestamp(data.get("visited_at", before["visited_at"]), "زمان مراجعه")
        next_service_at = valid_timestamp(data.get("next_service_at", before["next_service_at"]), "زمان سرویس بعدی")
        cur.execute("""update service_visits set service_type=%s,description=%s,invoice_amount=%s,received_amount=%s,amount=%s,company_share_percent=%s,company_share_amount=%s,customer_balance=%s,overpayment_amount=%s,payment_method=%s,status=%s,visited_at=%s,next_service_at=%s,updated_at=now() where id=%s""",
                    (service_type,description,invoice,received,received,pct,company,balance,overpayment,payment_method,status,visited_at,next_service_at,jid))
        audit(cur, "service_visit", jid, "update", before={"invoice": before["invoice_amount"], "received": before["received_amount"]}, after=data)
    return jsonify({"message": "سرویس ویرایش شد", "company_share_amount": company, "customer_balance": balance, "overpayment_amount": overpayment})


@app.get("/api/expenses")
@token_required
def expenses_list():
    limit = valid_integer(request.args.get("limit"), "تعداد هزینه", minimum=1, maximum=500, default=300)
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from expenses order by expense_date desc,created_at desc limit %s", (limit,))
        rows = cur.fetchall()
    return jsonify([{**row_json(r), "id": str(r["id"])} for r in rows])


@app.post("/api/expenses")
@roles_required("technician")
def expense_create():
    data = request.get_json() or {}
    client_id = valid_uuid(data.get("client_id"), "شناسه آفلاین هزینه", required=False)
    amount = valid_integer(data.get("amount"), "مبلغ هزینه", minimum=1)
    title = valid_text(data.get("title"), "عنوان هزینه", required=True, max_length=250)
    category = valid_choice(data.get("category"), "دسته هزینه", {"goods", "fuel", "parking", "tools", "food", "other"}, default="other")
    expense_date = valid_timestamp(data.get("expense_date"), "تاریخ هزینه")
    service_visit_id = valid_uuid(data.get("service_visit_id"), "شناسه سرویس", required=False)
    customer_id = valid_uuid(data.get("customer_id"), "شناسه مشتری", required=False)
    notes = valid_text(data.get("notes"), "توضیحات", max_length=4000)
    with get_db() as db, db.cursor() as cur:
        cur.execute("insert into expenses(id,category,title,amount,expense_date,service_visit_id,customer_id,notes,created_by) values(coalesce(%s::uuid,gen_random_uuid()),%s,%s,%s,coalesce(%s,now()),%s,%s,%s,%s) returning id", (client_id,category,title,amount,expense_date,service_visit_id,customer_id,notes,str(request.current_user.get("user_id"))))
        eid = cur.fetchone()["id"]
        audit(cur, "expense", eid, "create", after={"title": title, "amount": amount, "category": category})
    return jsonify({"id": str(eid), "message": "هزینه ثبت شد"}), 201


@app.delete("/api/expenses/<uuid:eid>")
@roles_required("admin")
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
    limit = valid_integer(request.args.get("limit"), "تعداد تسویه", minimum=1, maximum=500, default=300)
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from company_settlements order by settled_at desc limit %s", (limit,))
        rows = cur.fetchall()
    return jsonify([{**row_json(r), "id": str(r["id"])} for r in rows])


@app.post("/api/settlements")
@roles_required("admin")
def settlement_create():
    data = request.get_json() or {}
    client_id = valid_uuid(data.get("client_id"), "شناسه آفلاین تسویه", required=False)
    amount = valid_integer(data.get("amount"), "مبلغ تسویه", minimum=1)
    settled_at = valid_timestamp(data.get("settled_at"), "تاریخ تسویه")
    period_from = valid_timestamp(data.get("period_from"), "ابتدای دوره")
    period_to = valid_timestamp(data.get("period_to"), "انتهای دوره")
    if period_from and period_to and period_from > period_to:
        raise ValidationError("ابتدای دوره نمی‌تواند بعد از انتهای دوره باشد")
    notes = valid_text(data.get("notes"), "توضیحات", max_length=4000)
    with get_db() as db, db.cursor() as cur:
        cur.execute("insert into company_settlements(id,amount,settled_at,period_from,period_to,notes,created_by) values(coalesce(%s::uuid,gen_random_uuid()),%s,coalesce(%s,now()),%s,%s,%s,%s) returning id", (client_id,amount,settled_at,period_from,period_to,notes,str(request.current_user.get("user_id"))))
        sid = cur.fetchone()["id"]
        audit(cur, "settlement", sid, "create", after={"amount": amount})
    return jsonify({"id": str(sid), "message": "تسویه ثبت شد"}), 201


@app.get("/api/settings/finance")
@token_required
def finance_settings_get():
    with get_db() as db, db.cursor() as cur:
        return jsonify({"company_share_percent": finance_percent(cur)})


@app.patch("/api/settings/finance")
@roles_required("admin")
def finance_settings_set():
    data = request.get_json() or {}
    pct = valid_decimal(data.get("company_share_percent"), "درصد سهم شرکت")
    with get_db() as db, db.cursor() as cur:
        cur.execute("insert into app_settings(key,value,updated_at) values('finance',%s,now()) on conflict(key) do update set value=excluded.value,updated_at=now()", (Jsonb({"company_share_percent": float(pct)}),))
    return jsonify({"company_share_percent": float(pct)})


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
    text = valid_text((request.get_json() or {}).get("text"), "متن", required=True, max_length=8000)
    return jsonify(parse_intake(text))


@app.post("/api/smart/register")
@roles_required("technician")
def smart_register():
    data = request.get_json() or {}
    parsed = data.get("parsed") or parse_intake(data.get("text", ""))
    last = valid_text(parsed.get("last_name"), "نام خانوادگی", required=True, max_length=160)
    phones = valid_phones(parsed.get("phones", []))
    lat, lng = valid_coordinates(data.get("latitude"), data.get("longitude"))
    acc = as_float(data.get("accuracy"))
    selected = valid_uuid(data.get("customer_id"), "شناسه مشتری", required=False)
    address = valid_text(parsed.get("address"), "آدرس", max_length=1500)
    service_type = valid_text(parsed.get("service_type"), "نوع سرویس", max_length=200)
    description = valid_text(data.get("description") or parsed.get("description") or service_type, "شرح سرویس", max_length=4000)
    visitor_code = valid_text(parsed.get("visitor_code"), "کد ویزیتور", max_length=100)
    raw_text = valid_text(parsed.get("raw_text") or data.get("text"), "متن خام", max_length=8000)
    visited_at = valid_timestamp(data.get("visited_at"), "زمان مراجعه")
    with get_db() as db, db.cursor() as cur:
        cid = selected
        if cid:
            cur.execute("select 1 from customers_v2 where id=%s and archived=false", (cid,))
            if not cur.fetchone():
                return jsonify({"error": "مشتری انتخاب‌شده پیدا نشد"}), 404
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
                cur.execute("insert into customers_v2(last_name,normalized_name,address,map_label,location,location_accuracy_m,location_source,created_by) values(%s,%s,%s,%s,st_setsrid(st_makepoint(%s,%s),4326)::geography,%s,'gps',%s) returning id", (last,normalize_name(None,last),address,last,lng,lat,acc,str(request.current_user.get("user_id"))))
            else:
                cur.execute("insert into customers_v2(last_name,normalized_name,address,map_label,created_by) values(%s,%s,%s,%s,%s) returning id", (last,normalize_name(None,last),address,last,str(request.current_user.get("user_id"))))
            cid = cur.fetchone()["id"]
        for i, phone in enumerate(phones):
            cur.execute("select customer_id from customer_phones where phone=%s", (phone,))
            hit = cur.fetchone()
            if not hit:
                cur.execute("insert into customer_phones(customer_id,phone,is_primary) values(%s,%s,%s)", (cid,phone,i == 0))
            elif str(hit["customer_id"]) != str(cid):
                return jsonify({"error": f"شماره {phone} متعلق به مشتری دیگری است", "needs_selection": True, "existing_customer_id": str(hit["customer_id"])}), 409
        invoice = valid_integer(data.get("invoice_amount", parsed.get("amount") or 0), "مبلغ فاکتور", default=0)
        received = valid_integer(data.get("received_amount", parsed.get("amount") or invoice), "مبلغ دریافتی", default=invoice)
        pct = finance_percent(cur)
        company, balance = round(received * pct / 100), max(invoice - received, 0)
        overpayment = max(received - invoice, 0)
        if lat is not None and lng is not None:
            visit_sql, loc_params = "st_setsrid(st_makepoint(%s,%s),4326)::geography", [lng, lat]
        else:
            visit_sql, loc_params = "null", []
        params = [cid,str(request.current_user.get("user_id")),visitor_code,service_type,description,received,invoice,received,pct,company,balance,overpayment,visited_at] + loc_params + [raw_text]
        cur.execute(f"insert into service_visits(customer_id,registered_by,visitor_code,service_type,description,amount,invoice_amount,received_amount,company_share_percent,company_share_amount,customer_balance,overpayment_amount,status,visited_at,visit_location,raw_chat_input) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'registered',%s,{visit_sql},%s) returning id", params)
        vid = cur.fetchone()["id"]
        audit(cur, "service_visit", vid, "smart_create", after={"customer_id": str(cid), "received": received, "raw_text": data.get("text")})
    return jsonify({"customer_id": str(cid), "visit_id": str(vid), "parsed": parsed}), 201


@app.get("/api/customers/nearby")
@token_required
def customers_nearby():
    lat, lng = valid_coordinates(request.args.get("lat"), request.args.get("lng"), required=True)
    radius = float(valid_decimal(request.args.get("radius"), "شعاع", minimum=5, maximum=5000, default=250))
    with get_db() as db, db.cursor() as cur:
        cur.execute("""select c.id,c.first_name,c.last_name,c.map_label,c.address,c.location_accuracy_m,st_y(c.location::geometry) latitude,st_x(c.location::geometry) longitude,round(st_distance(c.location,st_setsrid(st_makepoint(%s,%s),4326)::geography)::numeric,1) distance_m,(select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone,(select received_amount from service_visits v where v.customer_id=c.id order by coalesce(v.visited_at,v.created_at) desc limit 1) last_amount,(select service_type from service_visits v where v.customer_id=c.id order by coalesce(v.visited_at,v.created_at) desc limit 1) last_service from customers_v2 c where c.archived=false and c.location is not null and st_dwithin(c.location,st_setsrid(st_makepoint(%s,%s),4326)::geography,%s) order by distance_m limit 50""", (lng,lat,lng,lat,radius))
        rows = cur.fetchall()
    return jsonify([{**row_json(r), "id": str(r["id"])} for r in rows])
