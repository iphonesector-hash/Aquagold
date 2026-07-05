"""
Aqua Gold v2.1.1 — Production Hotfix
Fixes: __name__/__file__ typos, space in keys, password_hash leak, login crash,
       hardcoded values, /health endpoint for Docker.
No new features. No endpoint changes (except /health for stability).
"""
import sqlite3, json, os, uuid, secrets, logging, hashlib
from datetime import datetime, timedelta
from functools import wraps

# --- Optional / third-party imports are guarded so a missing package never
# prevents the process from starting. Each has a safe degraded fallback. ---
try:
    import bcrypt
except Exception as ex:
    bcrypt = None
    logging.warning("bcrypt import failed (%s); falling back to a degraded "
                     "password hashing mode. Install bcrypt as soon as possible.", ex)

from flask import Flask, request, jsonify, g

try:
    from flask_cors import CORS
except Exception as ex:
    CORS = None
    logging.warning("flask_cors import failed (%s); CORS will not be configured.", ex)

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except Exception as ex:
    Limiter = None
    get_remote_address = None
    logging.warning("flask_limiter import failed (%s); rate limiting disabled.", ex)

try:
    import config
except Exception as ex:
    config = None
    logging.warning("config module failed to import (%s); falling back to "
                     "built-in default configuration values.", ex)


class _DefaultConfig:
    """Fallback values used whenever config.py is missing or a specific
    attribute is not defined on it. Keeps the app booting under any
    circumstances instead of crashing on startup."""
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    SECRET_KEY = secrets.token_hex(32)
    CORS_ORIGINS = "*"
    RATE_LIMIT_STORAGE = "memory://"
    RATE_LIMIT_DEFAULT = "200 per hour"
    LOGIN_RATE_LIMIT = "10 per minute"
    DATABASE_PATH = os.path.join("data", "app.db")
    DEFAULT_COMPANY_NAME = "Aqua Gold"
    DEFAULT_OWNER_SHARE = 50
    DEFAULT_UNCLE_SHARE = 50
    DEFAULT_ADMIN_USERNAME = "admin"
    DEFAULT_ADMIN_PASSWORD = "admin1234"
    DEFAULT_FALLBACK_PASSWORD = "changeme123"
    TOKEN_EXPIRE_HOURS = 24
    MAX_TOKENS_IN_MEMORY = 5000
    DEFAULT_SERVICE_INTERVAL = 180
    HOST = "0.0.0.0"
    PORT = 5000
    DEBUG = False


_defaults = _DefaultConfig()


def cfg(name):
    """Safely read a config value, falling back to a sane default if the
    config module is missing entirely or just missing that one attribute."""
    val = getattr(config, name, None) if config is not None else None
    if val is None:
        val = getattr(_defaults, name, None)
        logging.warning("config.%s missing or invalid; using default: %r", name, val)
    return val


logging.basicConfig(level=cfg("LOG_LEVEL"), format=cfg("LOG_FORMAT"))
log = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = cfg("SECRET_KEY")

if CORS is not None:
    try:
        CORS(app, origins=cfg("CORS_ORIGINS"))
    except Exception as ex:
        log.error("CORS initialization failed (%s); continuing without CORS.", ex)
else:
    log.warning("CORS not available; cross-origin requests will use Flask defaults.")


class _DummyLimiter:
    """No-op limiter used only if flask_limiter is unavailable or fails to
    initialize entirely, so the app never refuses to start because of it."""
    def limit(self, *a, **k):
        def dec(f):
            return f
        return dec


def _build_limiter(storage_uri):
    return Limiter(
        app=app, key_func=get_remote_address,
        storage_uri=storage_uri,
        default_limits=[cfg("RATE_LIMIT_DEFAULT")],
    )


if Limiter is not None and get_remote_address is not None:
    try:
        limiter = _build_limiter(cfg("RATE_LIMIT_STORAGE"))
    except Exception as ex:
        log.error("Limiter init with configured storage_uri failed (%s); "
                  "falling back to in-memory storage.", ex)
        try:
            limiter = _build_limiter("memory://")
        except Exception as ex2:
            log.error("Limiter fallback init also failed (%s); rate limiting "
                      "is disabled for this process.", ex2)
            limiter = _DummyLimiter()
else:
    limiter = _DummyLimiter()

DB = cfg("DATABASE_PATH")
try:
    _db_dir = os.path.dirname(os.path.abspath(DB))
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)
except Exception as ex:
    log.error("db_error: failed to create database directory for %s: %s", DB, ex)

ROLE_PERMS = {
    "superadmin": {"dashboard","services","customers","inventory","users",
                   "reports","settings","reminders","edit","delete","restore","bin","assign"},
    "admin":      {"dashboard","services","customers","inventory","reports",
                   "settings","reminders","edit","delete","restore","bin","assign"},
    "technician": {"dashboard","services","reminders"},
    "operator":   {"dashboard","services","customers","reminders","edit"},
}
ROLE_LABELS = {"superadmin":"مدیرکل","admin":"مدیر","technician":"تکنسین","operator":"اپراتور"}
STATUS_LABELS = {
    "registered":"ثبت شده","pending":"در انتظار","scheduled":"برنامه‌ریزی شده",
    "in_progress":"در حال انجام","completed":"تکمیل شده","cancelled":"لغو شده","revisit":"نیاز به مراجعه",
}
VALID_STATUSES = set(STATUS_LABELS.keys())

def get_db():
    try:
        c = sqlite3.connect(DB, timeout=15, check_same_thread=False)
    except Exception as ex:
        log.error("db_error: failed to connect to database at %s: %s", DB, ex)
        raise
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA busy_timeout = 15000")
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA journal_mode = WAL")
    except Exception as ex:
        log.error("db_error: pragma setup failed: %s", ex)
    return c

def _add_col(conn, table, col_def):
    try: conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
    except Exception: pass

def init_db():
    try:
        c = get_db()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL, first_name TEXT DEFAULT '', last_name TEXT DEFAULT '',
            mobile TEXT DEFAULT '', role TEXT DEFAULT 'operator', permissions TEXT DEFAULT '{}',
            is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT '', last_login TEXT DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT DEFAULT '',
            address TEXT DEFAULT '', device_model TEXT DEFAULT '', notes TEXT DEFAULT '',
            lat REAL, lng REAL, created_at TEXT DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, name TEXT DEFAULT '', phone TEXT DEFAULT '',
            address TEXT DEFAULT '', date TEXT DEFAULT '', deviceType TEXT DEFAULT '',
            filters TEXT DEFAULT '[]', amount REAL DEFAULT 0, paymentType TEXT DEFAULT '',
            note TEXT DEFAULT '', status TEXT DEFAULT 'registered', assigned_to TEXT,
            customer_id TEXT, next_service_date TEXT, service_interval INTEGER DEFAULT 180,
            createdAt TEXT DEFAULT '', updatedAt TEXT DEFAULT '', created_by TEXT, deleted_at TEXT)""")
        for col in ["status TEXT DEFAULT 'registered'","assigned_to TEXT","customer_id TEXT",
                    "next_service_date TEXT","service_interval INTEGER DEFAULT 180",
                    "updatedAt TEXT DEFAULT ''","created_by TEXT","deleted_at TEXT"]:
            _add_col(c, "jobs", col)
        c.execute("""CREATE TABLE IF NOT EXISTS inventory (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT DEFAULT '',
            quantity INTEGER DEFAULT 0, min_quantity INTEGER DEFAULT 5, unit TEXT DEFAULT 'عدد',
            notes TEXT DEFAULT '', created_at TEXT DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS inventory_tx (
            id TEXT PRIMARY KEY, item_id TEXT NOT NULL, tx_type TEXT NOT NULL,
            quantity INTEGER NOT NULL, job_id TEXT, note TEXT DEFAULT '',
            created_by TEXT, created_at TEXT DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '')""")
        for k, v in [("company_name", cfg("DEFAULT_COMPANY_NAME")),
                     ("owner_share", str(cfg("DEFAULT_OWNER_SHARE"))),
                     ("uncle_share", str(cfg("DEFAULT_UNCLE_SHARE")))]:
            c.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (k, v))
        c.execute("""CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, action TEXT NOT NULL,
            details TEXT DEFAULT '', ip TEXT DEFAULT '', created_at TEXT DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, type TEXT NOT NULL,
            title TEXT DEFAULT '', body TEXT DEFAULT '', is_read INTEGER DEFAULT 0,
            ref_type TEXT, ref_id TEXT, created_at TEXT DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, created_by TEXT NOT NULL,
            is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS conversation_members (
            conv_id TEXT NOT NULL, user_id TEXT NOT NULL, PRIMARY KEY (conv_id, user_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY, conv_id TEXT NOT NULL, sender_id TEXT NOT NULL,
            body TEXT DEFAULT '', msg_type TEXT DEFAULT 'text',
            is_deleted INTEGER DEFAULT 0, created_at TEXT DEFAULT '')""")
        if not c.execute("SELECT id FROM users WHERE role='superadmin'").fetchone():
            uid = str(uuid.uuid4())
            pw_hash = hash_pw(cfg("DEFAULT_ADMIN_PASSWORD"))
            perms = json.dumps({k: True for k in ROLE_PERMS["superadmin"]})
            c.execute("""INSERT INTO users
                (id,username,password_hash,first_name,last_name,role,permissions,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (uid, cfg("DEFAULT_ADMIN_USERNAME"), pw_hash, "مدیر", "اصلی",
                 "superadmin", perms, datetime.utcnow().isoformat()))
            log.info("Default admin created: %s", cfg("DEFAULT_ADMIN_USERNAME"))
        c.commit(); c.close()
        log.info("DB initialized: %s", DB)
    except Exception as ex:
        log.critical("db_error: init_db failed, server will start but the "
                     "database may be unusable: %s", ex)
        try:
            c.close()
        except Exception:
            pass

def row2dict(r):
    if r is None: return None
    d = dict(r)
    if "filters" in d:
        try: d["filters"] = json.loads(d["filters"] or "[]")
        except Exception: d["filters"] = []
    if "amount" in d: d["amount"] = float(d.get("amount") or 0)
    if "permissions" in d:
        try: d["permissions"] = json.loads(d["permissions"] or "{}")
        except Exception: d["permissions"] = {}
    d.pop("password_hash", None)
    return d

def get_settings_dict():
    c = get_db()
    rows = c.execute("SELECT key,value FROM settings").fetchall()
    c.close()
    return {r["key"]: r["value"] for r in rows}

_FALLBACK_HASH_PREFIX = "pbkdf2_fallback$"

def _fallback_hash_pw(pw):
    # Only used if bcrypt could not be imported. Logged loudly since it is a
    # weaker scheme, but it keeps auth functional instead of crashing.
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"{_FALLBACK_HASH_PREFIX}{salt}${digest}"

def _fallback_check_pw(pw, salt_and_digest):
    try:
        salt, digest = salt_and_digest.split("$", 1)
        expected = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
        return secrets.compare_digest(expected, digest)
    except Exception:
        return False

def hash_pw(pw):
    if bcrypt is None:
        log.error("db_error: bcrypt unavailable, using degraded password hashing.")
        return _fallback_hash_pw(pw)
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def check_pw(pw, hashed):
    try:
        if hashed and hashed.startswith(_FALLBACK_HASH_PREFIX):
            return _fallback_check_pw(pw, hashed[len(_FALLBACK_HASH_PREFIX):])
        if bcrypt is None:
            log.error("db_error: bcrypt unavailable, cannot verify bcrypt hash.")
            return False
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception as ex:
        log.error("auth_fail: password check raised an exception: %s", ex)
        return False

def issue_token(user_id):
    token = secrets.token_urlsafe(40)
    expires = (datetime.utcnow() + timedelta(hours=cfg("TOKEN_EXPIRE_HOURS"))).isoformat()
    c = get_db()
    c.execute("INSERT INTO tokens (token,user_id,expires) VALUES (?,?,?)", (token, user_id, expires))
    c.commit(); c.close()
    return token

def _purge_tokens():
    c = get_db()
    c.execute("DELETE FROM tokens WHERE expires < ?", (datetime.utcnow().isoformat(),))
    c.commit(); c.close()

def _get_token(token):
    c = get_db()
    row = c.execute("SELECT user_id, expires FROM tokens WHERE token=?", (token,)).fetchone()
    c.close()
    return row

def _revoke_token(token):
    if not token: return
    c = get_db()
    c.execute("DELETE FROM tokens WHERE token=?", (token,))
    c.commit(); c.close()

def _revoke_user_tokens(user_id):
    c = get_db()
    c.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))
    c.commit(); c.close()

def _count_tokens():
    c = get_db()
    n = c.execute("SELECT COUNT(*) AS n FROM tokens").fetchone()["n"]
    c.close()
    return n

def add_log(action, details=""):
    try:
        uid = getattr(g, "user", {}).get("id") if hasattr(g, "user") and g.user else None
        c = get_db()
        c.execute("INSERT INTO logs (user_id,action,details,ip,created_at) VALUES (?,?,?,?,?)",
                  (uid, action, str(details)[:500], request.remote_addr or "",
                   datetime.utcnow().isoformat()))
        c.commit(); c.close()
    except Exception as ex: log.error("add_log failed: %s", ex)

def has_perm(perm):
    u = getattr(g, "user", None)
    return bool(u and u.get("permissions", {}).get(perm))

def require_perm(perm):
    def dec(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not has_perm(perm):
                return jsonify({"error":"forbidden","msg":"دسترسی کافی ندارید"}), 403
            return f(*args, **kwargs)
        return wrapper
    return dec

def safe_call(f):
    """Guards a route handler so any unexpected exception (bad input,
    DB hiccup, etc.) never bubbles up into a crashed worker/process.
    Always returns a generic {"error": "server_error"} JSON response
    and logs the real cause server-side."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as ex:
            log.error("server_error in %s: %s", f.__name__, ex, exc_info=True)
            return jsonify({"error": "server_error"}), 500
    return wrapper

@app.before_request
def guard():
    g.user = None
    g.token = None
    if request.method == "OPTIONS": return
    if request.path in ("/api/login", "/health"): return

    try:
        if _count_tokens() > cfg("MAX_TOKENS_IN_MEMORY"):
            _purge_tokens()
    except Exception as ex:
        log.error("db_error: token purge check failed: %s", ex)

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        log.info("auth_fail: missing/invalid Authorization header for %s", request.path)
        return jsonify({"error":"unauthorized"}), 401
    token = auth[7:]

    try:
        info = _get_token(token)
    except Exception as ex:
        log.error("db_error: token lookup failed: %s", ex)
        return jsonify({"error":"unauthorized"}), 401

    if not info:
        log.info("auth_fail: unknown token for %s", request.path)
        return jsonify({"error":"unauthorized","msg":"session_expired"}), 401

    try:
        expired = datetime.utcnow() > datetime.fromisoformat(info["expires"])
    except Exception as ex:
        log.error("auth_fail: could not parse token expiry (%s); revoking token.", ex)
        try: _revoke_token(token)
        except Exception as ex2: log.error("db_error: revoke_token failed: %s", ex2)
        return jsonify({"error":"unauthorized","msg":"invalid_token"}), 401

    if expired:
        try: _revoke_token(token)
        except Exception as ex: log.error("db_error: revoke_token failed: %s", ex)
        log.info("auth_fail: expired session for %s", request.path)
        return jsonify({"error":"unauthorized","msg":"session_expired"}), 401

    try:
        c = get_db()
        row = c.execute("SELECT * FROM users WHERE id=? AND is_active=1", (info["user_id"],)).fetchone()
        c.close()
    except Exception as ex:
        log.error("db_error: user lookup during auth failed: %s", ex)
        return jsonify({"error":"unauthorized"}), 401

    if not row:
        log.info("auth_fail: user inactive or not found for token on %s", request.path)
        return jsonify({"error":"unauthorized"}), 401
    g.user = row2dict(row); g.token = token

@app.route("/api/login", methods=["POST"])
@limiter.limit(cfg("LOGIN_RATE_LIMIT"))
def login():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error":"missing_fields"}), 400
    c = get_db()
    row = c.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE AND is_active=1",
                    (username,)).fetchone()
    if not row:
        c.close()
        add_log("login_failed", f"username:{username}")
        return jsonify({"error":"invalid_credentials","msg":"نام کاربری یا رمز اشتباه است"}), 401
    if not check_pw(password, row["password_hash"]):
        c.close()
        add_log("login_failed", f"username:{username}")
        return jsonify({"error":"invalid_credentials","msg":"نام کاربری یا رمز اشتباه است"}), 401
    user_dict = row2dict(row)
    c.execute("UPDATE users SET last_login=? WHERE id=?",
              (datetime.utcnow().isoformat(), user_dict["id"]))
    c.commit(); c.close()
    token = issue_token(user_dict["id"])
    add_log("login_success")
    return jsonify({"token": token, "user": user_dict, "settings": get_settings_dict()})

@app.route("/api/logout", methods=["POST"])
def logout():
    _revoke_token(getattr(g, "token", ""))
    add_log("logout")
    return jsonify({"ok": True})

@app.route("/api/me", methods=["GET"])
def me(): return jsonify(g.user)

@app.route("/api/users", methods=["GET"])
@safe_call
def list_users():
    role_filter = request.args.get("role")
    c = get_db()
    if role_filter:
        rows = c.execute("SELECT * FROM users WHERE role=? AND is_active=1 ORDER BY first_name",
                         (role_filter,)).fetchall()
    else:
        rows = c.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    c.close()
    users = [row2dict(r) for r in rows]
    if not has_perm("users"):
        users = [{"id":u["id"],"first_name":u["first_name"],"last_name":u["last_name"],
                  "username":u["username"],"role":u["role"],"is_active":u["is_active"]} for u in users]
    return jsonify(users)

@app.route("/api/users", methods=["POST"])
@require_perm("users")
@safe_call
def create_user():
    data = request.get_json(force=True) or {}
    role = data.get("role", "operator")
    if role not in ROLE_PERMS: return jsonify({"error":"invalid_role"}), 400
    pw = data.get("password") or cfg("DEFAULT_FALLBACK_PASSWORD")
    if len(pw) < 4:
        return jsonify({"error":"password_too_short","msg":"رمز باید حداقل ۴ کاراکتر باشد"}), 400
    perms = json.dumps({k: True for k in ROLE_PERMS[role]})
    uid = str(uuid.uuid4())
    c = get_db()
    try:
        c.execute("""INSERT INTO users
            (id,username,password_hash,first_name,last_name,mobile,role,permissions,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (uid, data.get("username","").strip().lower(), hash_pw(pw),
             data.get("first_name",""), data.get("last_name",""),
             data.get("mobile",""), role, perms, datetime.utcnow().isoformat()))
        c.commit()
    except sqlite3.IntegrityError:
        c.close()
        return jsonify({"error":"username_exists","msg":"این نام کاربری قبلاً ثبت شده است"}), 409
    except Exception as ex:
        c.close(); log.error("create_user error: %s", ex)
        return jsonify({"error":"server_error"}), 500
    c.close()
    add_log("create_user", f"username:{data.get('username')}")
    return jsonify({"ok": True, "id": uid}), 201

@app.route("/api/users/<uid>", methods=["PUT"])
@require_perm("users")
@safe_call
def update_user(uid):
    data = request.get_json(force=True) or {}
    c = get_db()
    if "role" in data:
        role = data["role"]
        if role not in ROLE_PERMS:
            c.close(); return jsonify({"error":"invalid_role"}), 400
        perms = json.dumps({k: True for k in ROLE_PERMS[role]})
        c.execute("UPDATE users SET role=?,permissions=? WHERE id=?", (role, perms, uid))
    for field in ("first_name","last_name","mobile"):
        if field in data:
            c.execute(f"UPDATE users SET {field}=? WHERE id=?", (data[field], uid))
    c.commit(); c.close()
    add_log("update_user", f"id:{uid}")
    return jsonify({"ok": True})

@app.route("/api/users/<uid>/password", methods=["PUT"])
@safe_call
def change_password(uid):
    if (g.user or {}).get("id") != uid and not has_perm("users"):
        return jsonify({"error":"forbidden"}), 403
    data = request.get_json(force=True) or {}
    pw = data.get("password", "")
    if len(pw) < 4:
        return jsonify({"error":"too_short","msg":"رمز باید حداقل ۴ کاراکتر باشد"}), 400
    c = get_db()
    c.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_pw(pw), uid))
    c.commit(); c.close()
    _revoke_user_tokens(uid)
    add_log("password_change", f"id:{uid}")
    return jsonify({"ok": True})

@app.route("/api/users/<uid>/toggle", methods=["POST"])
@require_perm("users")
@safe_call
def toggle_user(uid):
    if uid == (g.user or {}).get("id"):
        return jsonify({"error":"cannot_deactivate_self"}), 400
    c = get_db()
    row = c.execute("SELECT is_active FROM users WHERE id=?", (uid,)).fetchone()
    if not row: c.close(); return jsonify({"error":"not_found"}), 404
    new_val = 0 if row["is_active"] else 1
    c.execute("UPDATE users SET is_active=? WHERE id=?", (new_val, uid))
    c.commit(); c.close()
    if new_val == 0:
        _revoke_user_tokens(uid)
    add_log("toggle_user", f"id:{uid} active:{new_val}")
    return jsonify({"ok": True, "is_active": new_val})

@app.route("/api/users/<uid>", methods=["DELETE"])
@require_perm("users")
@safe_call
def delete_user(uid):
    if uid == (g.user or {}).get("id"):
        return jsonify({"error":"cannot_delete_self"}), 400
    c = get_db()
    c.execute("DELETE FROM users WHERE id=?", (uid,))
    c.commit(); c.close()
    _revoke_user_tokens(uid)
    add_log("delete_user", f"id:{uid}")
    return jsonify({"ok": True})

@app.route("/api/jobs", methods=["GET"])
@safe_call
def list_jobs():
    c = get_db()
    if (g.user or {}).get("role") == "technician":
        rows = c.execute("SELECT * FROM jobs WHERE deleted_at IS NULL AND assigned_to=? "
                         "ORDER BY date DESC, createdAt DESC", ((g.user or {}).get("id"),)).fetchall()
    else:
        rows = c.execute("SELECT * FROM jobs WHERE deleted_at IS NULL "
                         "ORDER BY date DESC, createdAt DESC").fetchall()
    c.close()
    return jsonify([row2dict(r) for r in rows])

@app.route("/api/jobs", methods=["POST"])
@safe_call
def create_job():
    data = request.get_json(force=True) or {}
    jid = data.get("id") or str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    status = data.get("status", "registered")
    if status not in VALID_STATUSES: status = "registered"
    c = get_db()
    c.execute("""INSERT INTO jobs
        (id,name,phone,address,date,deviceType,filters,amount,paymentType,note,
         status,assigned_to,customer_id,next_service_date,service_interval,
         createdAt,updatedAt,created_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (jid, data.get("name",""), data.get("phone",""), data.get("address",""),
         data.get("date",""), data.get("deviceType",""),
         json.dumps(data.get("filters",[]), ensure_ascii=False),
         float(data.get("amount",0) or 0), data.get("paymentType",""), data.get("note",""),
         status, data.get("assigned_to") or None, data.get("customer_id") or None,
         data.get("next_service_date") or None,
         int(data.get("service_interval") or cfg("DEFAULT_SERVICE_INTERVAL")),
         data.get("createdAt") or now, now, (g.user or {}).get("id")))
    c.commit(); c.close()
    add_log("create_job", f"name:{data.get('name','')}")
    return jsonify({"ok": True, "id": jid}), 201

@app.route("/api/jobs/<jid>", methods=["PUT"])
@require_perm("edit")
@safe_call
def update_job(jid):
    data = request.get_json(force=True) or {}
    now = datetime.utcnow().isoformat()
    c = get_db()
    existing = c.execute("SELECT assigned_to FROM jobs WHERE id=? AND deleted_at IS NULL", (jid,)).fetchone()
    if not existing: c.close(); return jsonify({"error":"not_found"}), 404
    if (g.user or {}).get("role") == "technician" and existing["assigned_to"] != (g.user or {}).get("id"):
        c.close()
        return jsonify({"error":"forbidden","msg":"فقط می‌توانید سرویس‌های تخصیص‌یافته به خود را ویرایش کنید"}), 403

    fields, values = [], []
    if "name" in data: fields.append("name=?"); values.append(data.get("name",""))
    if "phone" in data: fields.append("phone=?"); values.append(data.get("phone",""))
    if "address" in data: fields.append("address=?"); values.append(data.get("address",""))
    if "date" in data: fields.append("date=?"); values.append(data.get("date",""))
    if "deviceType" in data: fields.append("deviceType=?"); values.append(data.get("deviceType",""))
    if "filters" in data:
        fields.append("filters=?"); values.append(json.dumps(data.get("filters",[]), ensure_ascii=False))
    if "amount" in data: fields.append("amount=?"); values.append(float(data.get("amount",0) or 0))
    if "paymentType" in data: fields.append("paymentType=?"); values.append(data.get("paymentType",""))
    if "note" in data: fields.append("note=?"); values.append(data.get("note",""))
    if "status" in data:
        status = data.get("status", "registered")
        if status not in VALID_STATUSES: status = "registered"
        fields.append("status=?"); values.append(status)
    if "assigned_to" in data:
        new_assigned = data.get("assigned_to") or None
        if not has_perm("assign"):
            new_assigned = existing["assigned_to"]
        fields.append("assigned_to=?"); values.append(new_assigned)
    if "customer_id" in data:
        fields.append("customer_id=?"); values.append(data.get("customer_id") or None)
    if "next_service_date" in data:
        fields.append("next_service_date=?"); values.append(data.get("next_service_date") or None)
    if "service_interval" in data:
        fields.append("service_interval=?")
        values.append(int(data.get("service_interval") or cfg("DEFAULT_SERVICE_INTERVAL")))

    fields.append("updatedAt=?"); values.append(now)
    values.append(jid)
    c.execute(f"UPDATE jobs SET {','.join(fields)} WHERE id=? AND deleted_at IS NULL", values)
    c.commit(); c.close()
    add_log("update_job", f"id:{jid}")
    return jsonify({"ok": True})

@app.route("/api/jobs/<jid>/status", methods=["PUT"])
@safe_call
def update_status(jid):
    data = request.get_json(force=True) or {}
    status = data.get("status", "registered")
    if status not in VALID_STATUSES: return jsonify({"error":"invalid_status"}), 400
    c = get_db()
    existing = c.execute("SELECT assigned_to FROM jobs WHERE id=? AND deleted_at IS NULL", (jid,)).fetchone()
    if not existing: c.close(); return jsonify({"error":"not_found"}), 404
    if (g.user or {}).get("role") == "technician" and existing["assigned_to"] != (g.user or {}).get("id"):
        c.close(); return jsonify({"error":"forbidden"}), 403
    c.execute("UPDATE jobs SET status=?,updatedAt=? WHERE id=?",
              (status, datetime.utcnow().isoformat(), jid))
    c.commit(); c.close()
    add_log("status_change", f"id:{jid} status:{status}")
    return jsonify({"ok": True})

@app.route("/api/jobs/<jid>/assign", methods=["PUT"])
@require_perm("assign")
@safe_call
def assign_job(jid):
    data = request.get_json(force=True) or {}
    c = get_db()
    c.execute("UPDATE jobs SET assigned_to=?,updatedAt=? WHERE id=?",
              (data.get("user_id") or None, datetime.utcnow().isoformat(), jid))
    c.commit(); c.close()
    add_log("assign_job", f"id:{jid} to:{data.get('user_id')}")
    return jsonify({"ok": True})

@app.route("/api/jobs/<jid>", methods=["DELETE"])
@require_perm("delete")
@safe_call
def soft_delete(jid):
    c = get_db()
    c.execute("UPDATE jobs SET deleted_at=? WHERE id=?", (datetime.utcnow().isoformat(), jid))
    c.commit(); c.close()
    add_log("soft_delete", f"id:{jid}")
    return jsonify({"ok": True})

@app.route("/api/jobs/<jid>/restore", methods=["POST"])
@require_perm("restore")
@safe_call
def restore_job(jid):
    c = get_db()
    c.execute("UPDATE jobs SET deleted_at=NULL WHERE id=?", (jid,))
    c.commit(); c.close()
    add_log("restore", f"id:{jid}")
    return jsonify({"ok": True})

@app.route("/api/jobs/<jid>/permanent", methods=["DELETE"])
@require_perm("delete")
@safe_call
def perm_delete(jid):
    c = get_db()
    c.execute("DELETE FROM jobs WHERE id=?", (jid,))
    c.commit(); c.close()
    add_log("permanent_delete", f"id:{jid}")
    return jsonify({"ok": True})

@app.route("/api/jobs/deleted", methods=["GET"])
@require_perm("bin")
@safe_call
def list_deleted():
    c = get_db()
    rows = c.execute("SELECT * FROM jobs WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC").fetchall()
    c.close()
    return jsonify([row2dict(r) for r in rows])

@app.route("/api/customers", methods=["GET"])
@require_perm("customers")
def list_customers():
    q = request.args.get("q", "")
    c = get_db()
    if q:
        rows = c.execute("SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY name",
                         (f"%{q}%", f"%{q}%")).fetchall()
    else:
        rows = c.execute("SELECT * FROM customers ORDER BY name").fetchall()
    c.close()
    return jsonify([row2dict(r) for r in rows])

@app.route("/api/customers", methods=["POST"])
@require_perm("customers")
def create_customer():
    data = request.get_json(force=True) or {}
    if not data.get("name","").strip():
        return jsonify({"error":"name_required","msg":"نام مشتری الزامی است"}), 400
    cid = str(uuid.uuid4())
    c = get_db()
    c.execute("""INSERT INTO customers
        (id,name,phone,address,device_model,notes,lat,lng,created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (cid, data.get("name","").strip(), data.get("phone",""),
         data.get("address",""), data.get("device_model",""),
         data.get("notes",""), data.get("lat"), data.get("lng"),
         datetime.utcnow().isoformat()))
    c.commit(); c.close()
    add_log("create_customer", f"name:{data.get('name','')}")
    return jsonify({"ok": True, "id": cid}), 201

@app.route("/api/customers/<cid>", methods=["GET"])
@require_perm("customers")
def get_customer(cid):
    c = get_db()
    row = c.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
    c.close()
    if not row: return jsonify({"error":"not_found"}), 404
    return jsonify(row2dict(row))

@app.route("/api/customers/<cid>", methods=["PUT"])
@require_perm("customers")
def update_customer(cid):
    data = request.get_json(force=True) or {}
    c = get_db()
    c.execute("""UPDATE customers SET name=?,phone=?,address=?,device_model=?,
        notes=?,lat=?,lng=? WHERE id=?""",
        (data.get("name",""), data.get("phone",""), data.get("address",""),
         data.get("device_model",""), data.get("notes",""),
         data.get("lat"), data.get("lng"), cid))
    c.commit(); c.close()
    add_log("update_customer", f"id:{cid}")
    return jsonify({"ok": True})

@app.route("/api/customers/<cid>", methods=["DELETE"])
@require_perm("customers")
def delete_customer(cid):
    c = get_db()
    c.execute("DELETE FROM customers WHERE id=?", (cid,))
    c.commit(); c.close()
    add_log("delete_customer", f"id:{cid}")
    return jsonify({"ok": True})

@app.route("/api/customers/<cid>/jobs", methods=["GET"])
@require_perm("customers")
def customer_jobs(cid):
    c = get_db()
    rows = c.execute("SELECT * FROM jobs WHERE customer_id=? AND deleted_at IS NULL ORDER BY date DESC",
                     (cid,)).fetchall()
    c.close()
    return jsonify([row2dict(r) for r in rows])

@app.route("/api/inventory", methods=["GET"])
@require_perm("inventory")
@safe_call
def list_inventory():
    c = get_db()
    rows = c.execute("SELECT * FROM inventory ORDER BY category, name").fetchall()
    c.close()
    return jsonify([row2dict(r) for r in rows])

@app.route("/api/inventory", methods=["POST"])
@require_perm("inventory")
@safe_call
def create_inventory():
    data = request.get_json(force=True) or {}
    if not data.get("name","").strip(): return jsonify({"error":"name_required"}), 400
    iid = str(uuid.uuid4())
    c = get_db()
    c.execute("""INSERT INTO inventory
        (id,name,category,quantity,min_quantity,unit,notes,created_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (iid, data.get("name","").strip(), data.get("category",""),
         max(0, int(data.get("quantity",0) or 0)),
         max(0, int(data.get("min_quantity",5) or 5)),
         data.get("unit","عدد"), data.get("notes",""),
         datetime.utcnow().isoformat()))
    c.commit(); c.close()
    add_log("create_inventory", f"name:{data.get('name','')}")
    return jsonify({"ok": True, "id": iid}), 201

@app.route("/api/inventory/<iid>", methods=["PUT"])
@require_perm("inventory")
@safe_call
def update_inventory(iid):
    data = request.get_json(force=True) or {}
    c = get_db()
    c.execute("UPDATE inventory SET name=?,category=?,min_quantity=?,unit=?,notes=? WHERE id=?",
              (data.get("name",""), data.get("category",""),
               max(0, int(data.get("min_quantity",5) or 5)),
               data.get("unit","عدد"), data.get("notes",""), iid))
    c.commit(); c.close()
    return jsonify({"ok": True})

@app.route("/api/inventory/<iid>", methods=["DELETE"])
@require_perm("inventory")
@safe_call
def delete_inventory(iid):
    c = get_db()
    c.execute("DELETE FROM inventory WHERE id=?", (iid,))
    c.commit(); c.close()
    return jsonify({"ok": True})

@app.route("/api/inventory/<iid>/transaction", methods=["POST"])
@require_perm("inventory")
@safe_call
def inventory_transaction(iid):
    data = request.get_json(force=True) or {}
    tx_type = data.get("type", "in")
    if tx_type not in ("in","out"): return jsonify({"error":"invalid_type"}), 400
    try: qty = int(data.get("quantity", 0))
    except (ValueError, TypeError): return jsonify({"error":"invalid_quantity"}), 400
    if qty <= 0:
        return jsonify({"error":"invalid_quantity","msg":"مقدار باید بیشتر از صفر باشد"}), 400
    c = get_db()
    row = c.execute("SELECT quantity FROM inventory WHERE id=?", (iid,)).fetchone()
    if not row: c.close(); return jsonify({"error":"not_found"}), 404
    current_qty = row["quantity"]
    if tx_type == "out" and current_qty < qty:
        c.close()
        return jsonify({"error":"insufficient_stock","msg":"موجودی کافی نیست",
                        "available": current_qty}), 400
    new_qty = current_qty + qty if tx_type == "in" else current_qty - qty
    c.execute("UPDATE inventory SET quantity=? WHERE id=?", (new_qty, iid))
    c.execute("""INSERT INTO inventory_tx
        (id,item_id,tx_type,quantity,job_id,note,created_by,created_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), iid, tx_type, qty,
         data.get("job_id"), data.get("note",""),
         (g.user or {}).get("id"), datetime.utcnow().isoformat()))
    c.commit(); c.close()
    add_log(f"inventory_{tx_type}", f"item:{iid} qty:{qty}")
    return jsonify({"ok": True, "new_quantity": new_qty})

@app.route("/api/stats", methods=["GET"])
@safe_call
def stats():
    c = get_db()
    rows = c.execute("SELECT date, amount, assigned_to, status FROM jobs WHERE deleted_at IS NULL").fetchall()
    users_map = {r["id"]: f"{r['first_name']} {r['last_name']}".strip()
                 for r in c.execute("SELECT id,first_name,last_name FROM users").fetchall()}
    total_customers = c.execute("SELECT COUNT(*) AS n FROM customers").fetchone()["n"]
    low_stock = c.execute("SELECT COUNT(*) AS n FROM inventory WHERE quantity > 0 AND quantity <= min_quantity").fetchone()["n"]
    out_of_stock = c.execute("SELECT COUNT(*) AS n FROM inventory WHERE quantity = 0").fetchone()["n"]
    c.close()
    today = datetime.utcnow().date()
    t_str, w_str = today.isoformat(), (today - timedelta(days=today.weekday())).isoformat()
    m_str, y_str = t_str[:7], t_str[:4]
    buckets = {k: {"total":0.0,"count":0} for k in ("today","week","month","year","all")}
    status_counts = {s:0 for s in STATUS_LABELS}
    tech_totals, monthly = {}, {}
    for r in rows:
        d = r["date"] or ""; amt = float(r["amount"] or 0)
        st = r["status"] or "registered"; tid = r["assigned_to"]
        buckets["all"]["total"] += amt; buckets["all"]["count"] += 1
        if d[:4]==y_str: buckets["year"]["total"]+=amt; buckets["year"]["count"]+=1
        if d[:7]==m_str: buckets["month"]["total"]+=amt; buckets["month"]["count"]+=1
        if d>=w_str: buckets["week"]["total"]+=amt; buckets["week"]["count"]+=1
        if d==t_str: buckets["today"]["total"]+=amt; buckets["today"]["count"]+=1
        if st in status_counts: status_counts[st] += 1
        if tid: tech_totals[tid] = tech_totals.get(tid, 0.0) + amt
        m = d[:7]
        if m: monthly[m] = monthly.get(m, 0.0) + amt
    s = get_settings_dict()
    try:
        op = float(s.get("owner_share", 50) or 50) / 100
    except (ValueError, TypeError):
        log.error("stats: invalid owner_share setting %r; defaulting to 50%%", s.get("owner_share"))
        op = 0.5
    for b in buckets.values():
        b["avg"] = round(b["total"]/b["count"],0) if b["count"] else 0
        b["owner"] = round(b["total"]*op, 0); b["uncle"] = round(b["total"]*(1-op), 0)
    sorted_months = sorted(monthly.keys())[-6:]
    chart_values = [round(monthly.get(m,0),0) for m in sorted_months]
    top_tech = None
    if tech_totals:
        top_id = max(tech_totals, key=lambda x: tech_totals[x])
        top_tech = {"name": users_map.get(top_id,"نامشخص"), "amount": tech_totals[top_id]}
    tech_breakdown = [{"name": users_map.get(tid,"نامشخص"), "amount": round(a,0)}
                      for tid, a in sorted(tech_totals.items(), key=lambda x: -x[1])]
    return jsonify({**buckets, "status_counts": status_counts,
                    "chart_months": sorted_months, "chart_values": chart_values,
                    "top_tech": top_tech, "tech_breakdown": tech_breakdown,
                    "total_customers": total_customers,
                    "low_stock": low_stock, "out_of_stock": out_of_stock})

@app.route("/api/settings", methods=["GET"])
def get_settings_ep(): return jsonify(get_settings_dict())

@app.route("/api/settings", methods=["PUT"])
@require_perm("settings")
def update_settings():
    data = request.get_json(force=True) or {}
    allowed = {"company_name","owner_share","uncle_share"}
    c = get_db()
    for k, v in data.items():
        if k in allowed:
            c.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (k, str(v)))
    c.commit(); c.close()
    add_log("update_settings")
    return jsonify({"ok": True})

@app.route("/api/logs", methods=["GET"])
@require_perm("settings")
def get_logs():
    c = get_db()
    rows = c.execute("""SELECT l.*, u.first_name || ' ' || u.last_name AS user_name
        FROM logs l LEFT JOIN users u ON l.user_id = u.id
        ORDER BY l.created_at DESC LIMIT 300""").fetchall()
    c.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/reminders", methods=["GET"])
def get_reminders():
    today = datetime.utcnow().date()
    today_str, urgent_str = today.isoformat(), (today + timedelta(days=7)).isoformat()
    horizon_str = (today + timedelta(days=30)).isoformat()
    c = get_db()
    if (g.user or {}).get("role") == "technician":
        rows = c.execute("""SELECT * FROM jobs WHERE deleted_at IS NULL
            AND next_service_date IS NOT NULL AND next_service_date <= ?
            AND assigned_to = ? ORDER BY next_service_date""",
            (horizon_str, (g.user or {}).get("id"))).fetchall()
    else:
        rows = c.execute("""SELECT * FROM jobs WHERE deleted_at IS NULL
            AND next_service_date IS NOT NULL AND next_service_date <= ?
            ORDER BY next_service_date""", (horizon_str,)).fetchall()
    c.close()
    result = []
    for r in rows:
        d = row2dict(r); nsd = d.get("next_service_date","")
        d["reminder_status"] = ("overdue" if nsd < today_str
                                else "urgent" if nsd <= urgent_str else "upcoming")
        result.append(d)
    return jsonify(result)

@app.route("/health")
def health():
    try:
        try:
            c = get_db(); c.execute("SELECT 1").fetchone(); c.close(); db_ok = True
        except Exception as ex:
            log.error("db_error: health check DB probe failed: %s", ex)
            db_ok = False
        return jsonify({"status": "ok" if db_ok else "degraded",
                        "version": "2.1.1",
                        "timestamp": datetime.utcnow().isoformat()}), 200 if db_ok else 503
    except Exception as ex:
        # Absolute last resort: /health must always respond, even if jsonify
        # or datetime somehow fail.
        log.critical("health endpoint itself failed: %s", ex)
        return '{"status":"degraded"}', 503, {"Content-Type": "application/json"}

@app.errorhandler(429)
def rate_limit_handler(e):
    return jsonify({"error":"too_many_requests","msg":"درخواست زیاد — لطفاً کمی صبر کنید"}), 429

@app.errorhandler(404)
def not_found_handler(e): return jsonify({"error":"not_found"}), 404

@app.errorhandler(500)
def server_error_handler(e):
    log.error("500 error: %s", e)
    return jsonify({"error":"server_error"}), 500

if __name__ == "__main__":
    init_db()
    app.run(host=cfg("HOST"), port=cfg("PORT"), debug=cfg("DEBUG"))
