from __future__ import annotations

import base64, hashlib, hmac, json, logging, os, re, urllib.error, urllib.request
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import psycopg
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, jsonify, make_response, request, send_from_directory
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

BASE_DIR = Path(__file__).resolve().parent
TEHRAN = ZoneInfo("Asia/Tehran")
APP_ENV = (os.getenv("VERCEL_ENV") or os.getenv("AQUAGOLD_ENV") or "development").lower()
IS_PRODUCTION = APP_ENV in {"production", "prod"}
SECRET_KEY = os.getenv("AQUAGOLD_SECRET_KEY") or os.getenv("SECRET_KEY") or ""
if IS_PRODUCTION and len(SECRET_KEY) < 32:
    raise RuntimeError("AQUAGOLD_SECRET_KEY is required and must be at least 32 characters")
if not SECRET_KEY:
    SECRET_KEY = "aqua-bale-local-dev-only"

def _database_url():
    for key in ("AQUAGOLD_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL", "NEON_DATABASE_URL", "AQUAGOLD_URL"):
        value = os.getenv(key)
        if value:
            return value
    return None

def _pooled_database_url(value):
    if not value or os.getenv("AQUAGOLD_DISABLE_POOLER") == "1":
        return value
    parsed = urlsplit(value); host = parsed.hostname or ""
    if ".neon.tech" not in host or host.split(".", 1)[0].endswith("-pooler"):
        return value
    pooled_host = host.replace(".neon.tech", "-pooler.neon.tech", 1)
    return urlunsplit((parsed.scheme, parsed.netloc.replace(host, pooled_host, 1), parsed.path, parsed.query, parsed.fragment))

DATABASE_URL = _pooled_database_url(_database_url())
app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
app.config.update(SECRET_KEY=SECRET_KEY, JSON_SORT_KEYS=False)
logger = logging.getLogger("aqua_bale_standalone")
MINI_COOKIE = "aqua_bale_session"
MINI_MAX_AGE = 7 * 24 * 3600
MINI_AUTH_KEY = "aqua_bale_standalone_auth"
MINI_PASSWORD_SHA256 = "49cad93a2f1e02d113ffd7e1a2b1ae72807225d95d3be5074d90e3ee0a5a18cd"
BALE_API = "https://tapi.bale.ai/bot{token}/{method}"
DIGIT_TRANS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
PHONE_RE = re.compile(r"(?:\+98|0098|0)?9[0-9۰-۹٠-٩]{9}")
PERSIAN_WORD_RE = re.compile(r"[آ-ی]{2,}")
KEYWORDS = ("فیلتر", "دستگاه", "ساید", "یخچال")
ASSISTANT_WAKE = "سکتور"
GROUP_TYPES = {"group", "supergroup"}

class ValidationError(ValueError):
    pass

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("AquaGold database URL is not configured")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)

def _serializer():
    return URLSafeTimedSerializer(SECRET_KEY, salt="aqua-bale-standalone-v1")

def _authorized():
    token = request.cookies.get(MINI_COOKIE, "")
    if not token:
        return False
    try:
        payload = _serializer().loads(token, max_age=MINI_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(payload, dict) and payload.get("u") == "admin"

def auth_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not _authorized():
            return jsonify({"error": "ورود به مینی‌اپ لازم است"}), 401
        return fn(*args, **kwargs)
    return wrapped

def _hash_password(value):
    return hashlib.sha256(str(value or "").encode()).hexdigest()

def _password_hash(cur=None):
    own = cur is None; ctx = get_db() if own else None; db = ctx.__enter__() if own else None; cursor = db.cursor() if own else cur
    try:
        cursor.execute("select value from app_settings where key=%s", (MINI_AUTH_KEY,)); row = cursor.fetchone(); value = dict((row or {}).get("value") or {})
        stored = str(value.get("password_sha256") or "").strip().lower()
        return stored if len(stored) == 64 else MINI_PASSWORD_SHA256
    finally:
        if own:
            cursor.close(); ctx.__exit__(None, None, None)

def _fernet():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()))

def _decrypt(value):
    if not value:
        return ""
    try:
        return _fernet().decrypt(str(value).encode()).decode()
    except (InvalidToken, ValueError):
        return ""

def _normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\u200c", " ")).strip()

def _normalize_phone(value):
    digits = re.sub(r"\D", "", str(value or "").translate(DIGIT_TRANS))
    if digits.startswith("98") and len(digits) == 12: digits = "0" + digits[2:]
    elif digits.startswith("9") and len(digits) == 10: digits = "0" + digits
    return digits

def _json_value(value):
    if isinstance(value, (datetime, date)): return value.isoformat()
    if hasattr(value, "__float__") and not isinstance(value, (str, bytes, int, float, bool)):
        try: return float(value)
        except Exception: pass
    return value

def _row(row):
    return {k: _json_value(v) for k, v in dict(row).items()}

def _parse_day(raw):
    try: return date.fromisoformat(str(raw or ""))
    except ValueError as exc: raise ValidationError("تاریخ معتبر نیست") from exc

def _day_bounds(day):
    start = datetime.combine(day, datetime.min.time(), tzinfo=TEHRAN)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)

def _tehran_today(): return datetime.now(TEHRAN).date()

def _gregorian_to_jalali(g):
    gy, gm, gd = g.year, g.month, g.day; gdm = [0,31,59,90,120,151,181,212,243,273,304,334]; gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365*gy + (gy2+3)//4 - (gy2+99)//100 + (gy2+399)//400 + gd + gdm[gm-1]
    jy = -1595 + 33*(days//12053); days %= 12053; jy += 4*(days//1461); days %= 1461
    if days > 365: jy += (days-1)//365; days = (days-1)%365
    return (jy, 1+days//31, 1+days%31) if days < 186 else (jy, 7+(days-186)//30, 1+(days-186)%30)

def _jalali_to_gregorian(jy,jm,jd):
    jy += 1595; days = -355668 + 365*jy + (jy//33)*8 + ((jy%33)+3)//4 + jd; days += (jm-1)*31 if jm < 7 else (jm-7)*30 + 186
    gy = 400*(days//146097); days %= 146097
    if days > 36524:
        gy += 100*((days-1)//36524); days=(days-1)%36524
        if days >= 365: days += 1
    gy += 4*(days//1461); days %= 1461
    if days > 365: gy += (days-1)//365; days=(days-1)%365
    gd = days+1; leap = gy%4==0 and (gy%100!=0 or gy%400==0); sal=[0,31,29 if leap else 28,31,30,31,30,31,31,30,31,30,31]; gm=1
    while gm <= 12 and gd > sal[gm]: gd -= sal[gm]; gm += 1
    return date(gy,gm,gd)

def _period_bounds(anchor, period):
    if period == "daily": return anchor, anchor + timedelta(days=1)
    if period == "weekly":
        start = anchor - timedelta(days=(anchor.weekday()-5)%7); return start, start + timedelta(days=7)
    if period == "monthly":
        jy,jm,_ = _gregorian_to_jalali(anchor); start = _jalali_to_gregorian(jy,jm,1); end = _jalali_to_gregorian(jy+1,1,1) if jm==12 else _jalali_to_gregorian(jy,jm+1,1); return start,end
    raise ValidationError("بازه گزارش معتبر نیست")

def _settings(cur=None):
    own = cur is None; ctx = get_db() if own else None; db = ctx.__enter__() if own else None; cursor = db.cursor() if own else cur
    try:
        cursor.execute("select value from app_settings where key='bale_bot'"); row = cursor.fetchone(); data = dict((row or {}).get("value") or {})
    finally:
        if own: cursor.close(); ctx.__exit__(None,None,None)
    env_allowed=[x.strip() for x in os.getenv("BALE_ALLOWED_CHAT_IDS","").split(",") if x.strip()]; db_allowed=[str(x) for x in (data.get("allowed_chat_ids") or [])]
    return {"bot_token":os.getenv("BALE_BOT_TOKEN") or _decrypt(data.get("bot_token_cipher")),"webhook_secret":os.getenv("BALE_WEBHOOK_SECRET") or str(data.get("webhook_secret") or ""),"allowed_chat_ids":env_allowed or db_allowed,"auto_reply":bool(data.get("auto_reply",True))}

def _bale_call(token,method,payload=None,timeout=12):
    if not token: raise RuntimeError("توکن ربات بله تنظیم نشده است")
    req=urllib.request.Request(BALE_API.format(token=token,method=method),data=json.dumps(payload or {},ensure_ascii=False).encode(),headers={"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            raw=response.read().decode(errors="replace"); return json.loads(raw) if raw else {"ok":True}
    except urllib.error.HTTPError as exc:
        detail=exc.read().decode(errors="replace")[:500]; raise RuntimeError(f"بله پاسخ نداد ({exc.code}): {detail}") from exc

def _send_chat(settings,chat_id,text,reply_to_message_id=None,reply_markup=None):
    if not settings.get("bot_token"): return None
    payload={"chat_id":chat_id,"text":text}
    if reply_to_message_id: payload["reply_to_message_id"]=reply_to_message_id
    if reply_markup: payload["reply_markup"]=reply_markup
    try: return _bale_call(settings["bot_token"],"sendMessage",payload,8)
    except Exception as exc: logger.warning("bale_send_failed: %s",exc); return None

def _message_payload(update):
    message=update.get("message") or update.get("edited_message") or update.get("channel_post") or {}; text=message.get("text") or message.get("caption") or ""; chat=message.get("chat") or {}; sender=message.get("from") or message.get("sender_chat") or {}
    sender_name=_normalize_text(" ".join(str(sender.get(k) or "") for k in ("first_name","last_name"))) or str(sender.get("title") or "")
    return message,text,chat,sender,sender_name

def _extract_job(text):
    raw=str(text or "").strip(); flat=_normalize_text(raw); phone_match=PHONE_RE.search(raw); phone=_normalize_phone(phone_match.group(0)) if phone_match else ""; keyword_hits=[w for w in KEYWORDS if w in flat]
    cleaned=PHONE_RE.sub(" ",flat)
    for junk in ("شماره","تلفن","موبایل","آدرس","کار","سرویس","تعویض","نصب","بررسی")+KEYWORDS: cleaned=cleaned.replace(junk," ")
    words=[w for w in PERSIAN_WORD_RE.findall(cleaned) if len(w)>=2]
    if not keyword_hits and not (phone and words): return None
    lines=[_normalize_text(x) for x in raw.splitlines() if _normalize_text(x)]; customer_name=""
    if phone_match:
        for line in lines:
            if PHONE_RE.search(line):
                candidate=PHONE_RE.sub("",line); candidate=re.sub(r"(?:شماره|تلفن|موبایل|آقا|خانم|مشتری)[:：]?"," ",candidate); candidate=_normalize_text(candidate)
                if PERSIAN_WORD_RE.search(candidate): customer_name=candidate[:120]; break
    if not customer_name:
        for line in lines:
            if any(k in line for k in KEYWORDS): continue
            candidate=PHONE_RE.sub("",line)
            if PERSIAN_WORD_RE.search(candidate): customer_name=_normalize_text(candidate)[:120]; break
    markers=("خیابان","خ ","کوچه","پلاک","واحد","شهرک","بلوار","میدان","اتوبان","بزرگراه","تهران","کرج"); address_lines=[line for line in lines if any(m in line for m in markers)]; address="، ".join(address_lines)[:1000] if address_lines else ""
    job_type="یخچال/ساید" if ("یخچال" in flat or "ساید" in flat) else "فیلتر" if "فیلتر" in flat else "دستگاه" if "دستگاه" in flat else "سرویس"
    return {"customer_name":customer_name,"phone":phone,"address":address,"job_type":job_type,"matched_keywords":keyword_hits}

def _find_customer_by_phone(cur,phone):
    if not phone:return None
    cur.execute("select customer_id from customer_phones where phone=%s order by is_primary desc,id limit 1",(phone,)); row=cur.fetchone(); return row["customer_id"] if row else None

def _money(v): return f"{int(v or 0):,}".replace(",","٬")+" تومان"

def _assistant_done_today(cur):
    start,end=_day_bounds(_tehran_today()); cur.execute("""select c.last_name,coalesce(s.service_type,'سرویس') service_type,coalesce(s.received_amount,0)::bigint amount,coalesce(s.visited_at,s.created_at) event_at from service_visits s join customers_v2 c on c.id=s.customer_id where s.status not in ('cancelled','scheduled') and coalesce(s.visited_at,s.created_at)>=%s and coalesce(s.visited_at,s.created_at)<%s order by coalesce(s.visited_at,s.created_at)""",(start,end)); rows=cur.fetchall()
    if not rows:return "امروز هنوز کار انجام‌شده‌ای ثبت نشده."
    lines=[f"✅ کارهای انجام‌شده امروز: {len(rows)} مورد"]
    for i,r in enumerate(rows[:25],1):
        when=r["event_at"].astimezone(TEHRAN).strftime("%H:%M") if r.get("event_at") else "—"; lines.append(f"{i}) {r.get('last_name') or 'بدون نام'} — {r.get('service_type') or 'سرویس'} — {_money(r.get('amount'))} — {when}")
    if len(rows)>25:lines.append(f"… و {len(rows)-25} مورد دیگر")
    return "\n".join(lines)

def _assistant_sales_today(cur):
    start,end=_day_bounds(_tehran_today()); cur.execute("""select count(*)::int count,coalesce(sum(received_amount),0)::bigint received,coalesce(sum(company_share_amount),0)::bigint company_share from service_visits where status not in ('cancelled','scheduled') and coalesce(visited_at,created_at)>=%s and coalesce(visited_at,created_at)<%s""",(start,end)); r=cur.fetchone(); return f"💰 فروش امروز\n• کار انجام‌شده: {r['count']} مورد\n• دریافتی: {_money(r['received'])}\n• سهم شرکت: {_money(r['company_share'])}"

def _assistant_cancelled_today(cur):
    start,end=_day_bounds(_tehran_today()); cur.execute("""select coalesce(c.last_name,nullif(b.customer_name,''),'بدون نام') last_name,coalesce(b.cancel_reason,'علت ثبت نشده') reason from bale_jobs b left join customers_v2 c on c.id=b.customer_id where b.status='cancelled' and coalesce(b.cancelled_at,b.updated_at,b.received_at)>=%s and coalesce(b.cancelled_at,b.updated_at,b.received_at)<%s order by coalesce(b.cancelled_at,b.updated_at,b.received_at)""",(start,end)); rows=cur.fetchall()
    if not rows:return "امروز کنسلی ثبت نشده."
    return "🚫 کنسلی‌های امروز:\n"+"\n".join(f"{i}) {r['last_name']} — {r['reason']}" for i,r in enumerate(rows[:25],1))

def _extract_customer_query(text):
    normalized=_normalize_text(text).replace(ASSISTANT_WAKE," ")
    for phrase in ("مشتری","کارش","کار","چیشد","چی شد","چه شد","وضعیت","رو","را","بگو","میشه","می شه","لطفا","لطفاً","فلان"): normalized=normalized.replace(phrase," ")
    normalized=re.sub(r"[^آ-یA-Za-z0-9۰-۹٠-٩\s]"," ",normalized); return " ".join([w for w in _normalize_text(normalized).split() if len(w)>=2][:4]).strip()

def _assistant_customer_status(cur,text):
    q=_extract_customer_query(text)
    if not q:return "اسم یا شماره مشتری رو هم بگو؛ مثلاً «سکتور موسوی کارش چی شد؟»"
    like=f"%{q}%"; phone=_normalize_phone(q); cur.execute("""select c.id,c.first_name,c.last_name,coalesce((select p.phone from customer_phones p where p.customer_id=c.id order by p.is_primary desc,p.id limit 1),'') phone from customers_v2 c where not c.archived and (concat_ws(' ',c.first_name,c.last_name) ilike %s or (%s<>'' and exists(select 1 from customer_phones p where p.customer_id=c.id and p.phone like %s))) order by c.updated_at desc limit 4""",(like,phone,f"%{phone}%" if phone else "%__never__%")); customers=cur.fetchall()
    if not customers:return f"مشتری «{q}» پیدا نشد."
    if len(customers)>1 and not phone:return "چند مشتری پیدا شد: "+"، ".join(_normalize_text(f"{c.get('first_name') or ''} {c.get('last_name') or ''}") for c in customers)+"\nاسم کامل‌تر یا شماره رو بگو."
    c=customers[0]; cur.execute("""select 'service' source,case when status in ('cancelled','scheduled') then status else 'completed' end status,service_type,received_amount,null::text cancel_reason,coalesce(visited_at,created_at) event_at from service_visits where customer_id=%s union all select 'bale' source,status,job_type,received_amount,cancel_reason,coalesce(cancelled_at,completed_at,updated_at,received_at) event_at from bale_jobs where customer_id=%s and status='cancelled' order by event_at desc limit 1""",(c["id"],c["id"])); latest=cur.fetchone(); name=_normalize_text(f"{c.get('first_name') or ''} {c.get('last_name') or ''}") or c.get("last_name") or "مشتری"
    if not latest:return f"برای {name} هنوز کار نهایی ثبت نشده."
    when=latest["event_at"].astimezone(TEHRAN).strftime("%Y/%m/%d %H:%M") if latest.get("event_at") else "—"
    if latest["status"]=="cancelled":return f"🚫 {name}: کنسل شده\nعلت: {latest.get('cancel_reason') or 'ثبت نشده'}\nزمان: {when}"
    return f"✅ {name}: انجام شده\nخدمت: {latest.get('service_type') or 'سرویس'}\nدریافتی: {_money(latest.get('received_amount'))}\nزمان: {when}"

def _assistant_reply(text):
    flat=_normalize_text(text)
    with get_db() as db,db.cursor() as cur:
        if "کنسل" in flat and "امروز" in flat:return _assistant_cancelled_today(cur)
        if any(w in flat for w in ("فروش","دریافتی","چقدر")) and "امروز" in flat:return _assistant_sales_today(cur)
        if "انجام" in flat and "امروز" in flat:return _assistant_done_today(cur)
        if any(w in flat for w in ("مشتری","کارش","چیشد","چی شد","وضعیت")):return _assistant_customer_status(cur,flat)
    return "می‌تونی ازم بپرسی:\n• سکتور کارهای انجام‌شده امروز رو بده\n• سکتور امروز چقدر فروش داشتیم؟\n• سکتور کنسلی‌های امروز رو بگو\n• سکتور موسوی کارش چی شد؟"

@app.errorhandler(ValidationError)
def validation_error(exc): return jsonify({"error":str(exc)}),400
@app.errorhandler(Exception)
def unexpected(exc):
    logger.exception("request_failed: %s",exc)
    return (jsonify({"error":"خطای داخلی سرویس"}),500) if request.path.startswith("/api/") else ("Internal Server Error",500)
@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"]="nosniff"; response.headers["Referrer-Policy"]="strict-origin-when-cross-origin"; response.headers["Permissions-Policy"]="camera=(), microphone=(self), geolocation=(self)"; response.headers["X-Robots-Tag"]="noindex"
    response.headers["Content-Security-Policy"]="default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; img-src 'self' data: blob: https:; font-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' https://tapi.bale.ai; connect-src 'self' https://tapi.bale.ai; worker-src 'self' blob:; manifest-src 'self'"
    return response

@app.get("/")
def index(): return send_from_directory(BASE_DIR,"aqua-bale-miniapp.html")
@app.get("/health")
def health():
    db_ok=False
    try:
        with get_db() as db,db.cursor() as cur:cur.execute("select 1 ok");db_ok=cur.fetchone()["ok"]==1
    except Exception:pass
    try:s=_settings()
    except Exception:s={}
    return jsonify({"ok":db_ok,"database":db_ok,"bale_token":bool(s.get("bot_token")),"allowed_groups":len(s.get("allowed_chat_ids") or [])})
@app.get("/api/mini/session")
def session():
    ok=_authorized();return jsonify({"authenticated":ok,"username":"admin" if ok else None})
@app.post("/api/mini/login")
def login():
    data=request.get_json(silent=True) or {};username=str(data.get("username") or "").strip().lower()
    if username!="admin" or not hmac.compare_digest(_hash_password(data.get("password")),_password_hash()):return jsonify({"error":"نام کاربری یا رمز عبور اشتباه است"}),401
    response=make_response(jsonify({"ok":True,"username":"admin"}));response.set_cookie(MINI_COOKIE,_serializer().dumps({"u":"admin"}),max_age=MINI_MAX_AGE,httponly=True,secure=IS_PRODUCTION,samesite="Lax",path="/");return response
@app.post("/api/mini/logout")
def logout():
    response=make_response(jsonify({"ok":True}));response.delete_cookie(MINI_COOKIE,path="/");return response
@app.post("/api/mini/password")
@auth_required
def change_password():
    data=request.get_json(silent=True) or {};current=str(data.get("current_password") or "");new=str(data.get("new_password") or "");confirm=str(data.get("confirm_password") or "")
    if len(new)<7:raise ValidationError("رمز جدید باید حداقل ۷ کاراکتر باشد")
    if new!=confirm:raise ValidationError("تکرار رمز جدید یکسان نیست")
    with get_db() as db,db.cursor() as cur:
        if not hmac.compare_digest(_hash_password(current),_password_hash(cur)):raise ValidationError("رمز فعلی اشتباه است")
        cur.execute("insert into app_settings(key,value,updated_at) values(%s,%s,now()) on conflict(key) do update set value=excluded.value,updated_at=now()",(MINI_AUTH_KEY,Jsonb({"password_sha256":_hash_password(new)})))
    return jsonify({"ok":True})

@app.get("/api/mini/day")
@auth_required
def mini_day():
    day=_parse_day(request.args.get("date"));start,end=_day_bounds(day)
    with get_db() as db,db.cursor() as cur:
        cur.execute("""select s.id,c.last_name customer_name,coalesce((select p.phone from customer_phones p where p.customer_id=c.id order by p.is_primary desc,p.id limit 1),'') phone,c.address,coalesce(s.service_type,'سرویس') job_type,'completed'::text status,coalesce(s.visited_at,s.created_at) received_at,coalesce(s.visited_at,s.created_at) completed_at,null::timestamptz cancelled_at,null::text cancel_reason,c.id customer_id,s.id service_visit_id,coalesce(s.received_amount,0)::bigint received_amount,coalesce(s.company_share_amount,0)::bigint company_share_amount from service_visits s join customers_v2 c on c.id=s.customer_id where s.status not in ('cancelled','scheduled') and coalesce(s.visited_at,s.created_at)>=%s and coalesce(s.visited_at,s.created_at)<%s""",(start,end));jobs=[_row(r) for r in cur.fetchall()]
        cur.execute("""select b.id,coalesce(c.last_name,nullif(b.customer_name,''),'بدون نام') customer_name,coalesce((select p.phone from customer_phones p where p.customer_id=c.id order by p.is_primary desc,p.id limit 1),b.phone,'') phone,coalesce(c.address,b.address) address,coalesce(b.job_type,'سرویس') job_type,'cancelled'::text status,coalesce(b.cancelled_at,b.updated_at,b.received_at) received_at,null::timestamptz completed_at,coalesce(b.cancelled_at,b.updated_at,b.received_at) cancelled_at,b.cancel_reason,b.customer_id,b.service_visit_id,0::bigint received_amount,0::bigint company_share_amount from bale_jobs b left join customers_v2 c on c.id=b.customer_id where b.status='cancelled' and coalesce(b.cancelled_at,b.updated_at,b.received_at)>=%s and coalesce(b.cancelled_at,b.updated_at,b.received_at)<%s""",(start,end));jobs.extend(_row(r) for r in cur.fetchall())
    jobs.sort(key=lambda x:str(x.get("received_at") or ""));completed=sum(x["status"]=="completed" for x in jobs);cancelled=sum(x["status"]=="cancelled" for x in jobs);received=sum(int(x.get("received_amount") or 0) for x in jobs if x["status"]=="completed");company=sum(int(x.get("company_share_amount") or 0) for x in jobs if x["status"]=="completed")
    return jsonify({"date":day.isoformat(),"jobs":jobs,"summary":{"total":completed+cancelled,"completed":completed,"cancelled":cancelled,"received":received,"company_share":company}})

@app.get("/api/mini/customers")
@auth_required
def mini_customers():
    q=str(request.args.get("q") or "").strip()
    if len(q)<2:return jsonify([])
    like=f"%{q}%";normalized=_normalize_phone(q);phone_like=f"%{normalized}%" if normalized else "%__never__%"
    with get_db() as db,db.cursor() as cur:
        cur.execute("""select c.id,c.first_name,c.last_name,c.address,c.plaque,c.unit_no,c.device_model,c.notes,c.created_at,coalesce((select json_agg(p.phone order by p.is_primary desc,p.id) from customer_phones p where p.customer_id=c.id),'[]'::json) phones,(select count(*)::int from service_visits s where s.customer_id=c.id and s.status not in ('cancelled','scheduled')) completed_services,(select count(*)::int from bale_jobs b where b.customer_id=c.id and b.status='cancelled') cancelled_services,coalesce((select sum(s.received_amount)::bigint from service_visits s where s.customer_id=c.id and s.status not in ('cancelled','scheduled')),0) total_received,(select max(coalesce(s.visited_at,s.created_at)) from service_visits s where s.customer_id=c.id and s.status not in ('cancelled','scheduled')) last_service_at from customers_v2 c where not c.archived and (concat_ws(' ',c.first_name,c.last_name) ilike %s or coalesce(c.address,'') ilike %s or exists(select 1 from customer_phones p where p.customer_id=c.id and p.phone like %s)) order by c.updated_at desc limit 20""",(like,like,phone_like));rows=[]
        for raw in cur.fetchall():
            item=_row(raw);item["completed_services"]=int(item.get("completed_services") or 0);item["cancelled_services"]=int(item.get("cancelled_services") or 0);item["total_services"]=item["completed_services"]+item["cancelled_services"];rows.append(item)
    return jsonify(rows)

@app.get("/api/mini/customers/<customer_id>")
@auth_required
def mini_customer_detail(customer_id):
    if not re.fullmatch(r"[0-9a-fA-F-]{36}",customer_id or ""):raise ValidationError("شناسه مشتری معتبر نیست")
    with get_db() as db,db.cursor() as cur:
        cur.execute("""select c.id,c.first_name,c.last_name,c.address,c.plaque,c.unit_no,c.device_model,c.notes,c.created_at,coalesce((select json_agg(p.phone order by p.is_primary desc,p.id) from customer_phones p where p.customer_id=c.id),'[]'::json) phones from customers_v2 c where c.id=%s::uuid""",(customer_id,));customer=cur.fetchone()
        if not customer:return jsonify({"error":"مشتری پیدا نشد"}),404
        cur.execute("""select id,service_type,description,case when status in ('cancelled','scheduled') then status else 'completed' end status,payment_method,invoice_amount,received_amount,company_share_amount,scheduled_from,scheduled_until,visited_at,created_at from service_visits where customer_id=%s::uuid order by coalesce(visited_at,created_at) desc limit 100""",(customer_id,));visits=[_row(r) for r in cur.fetchall()]
        cur.execute("""select id,job_type,status,received_amount,cancel_reason,received_at,completed_at,cancelled_at from bale_jobs where customer_id=%s::uuid and status='cancelled' order by coalesce(cancelled_at,received_at) desc limit 100""",(customer_id,));bale_jobs=[_row(r) for r in cur.fetchall()]
    return jsonify({"customer":_row(customer),"visits":visits,"bale_jobs":bale_jobs})

@app.get("/api/mini/finance")
@auth_required
def mini_finance():
    period=str(request.args.get("period") or "daily").strip().lower();anchor=_parse_day(request.args.get("date"));start_day,end_day=_period_bounds(anchor,period);start=_day_bounds(start_day)[0];end=_day_bounds(end_day)[0];chart_start=_day_bounds(start_day-timedelta(days=6) if period=="daily" else start_day)[0]
    with get_db() as db,db.cursor() as cur:
        cur.execute("""select count(*)::int service_count,coalesce(sum(invoice_amount),0)::bigint invoice_total,coalesce(sum(received_amount),0)::bigint received_total,coalesce(sum(company_share_amount),0)::bigint company_share from service_visits where status not in ('cancelled','scheduled') and coalesce(visited_at,created_at)>=%s and coalesce(visited_at,created_at)<%s""",(start,end));summary=_row(cur.fetchone());cur.execute("select coalesce(sum(amount),0)::bigint settled_total from company_settlements where settled_at>=%s and settled_at<%s",(start,end));summary.update(_row(cur.fetchone()));summary["payable"]=max(int(summary.get("company_share") or 0)-int(summary.get("settled_total") or 0),0)
        cur.execute("""select (timezone('Asia/Tehran',coalesce(visited_at,created_at)))::date as report_day,coalesce(sum(received_amount),0)::bigint received,coalesce(sum(company_share_amount),0)::bigint company_share,count(*)::int count from service_visits where status not in ('cancelled','scheduled') and coalesce(visited_at,created_at)>=%s and coalesce(visited_at,created_at)<%s group by 1 order by 1""",(chart_start,end));chart=[]
        for raw in cur.fetchall():item=_row(raw);item["day"]=item.pop("report_day");chart.append(item)
    return jsonify({"period":period,"anchor":anchor.isoformat(),"from":start_day.isoformat(),"to":(end_day-timedelta(days=1)).isoformat(),"summary":summary,"chart":chart})

@app.post("/api/bale/webhook/<secret>")
def bale_webhook(secret):
    settings=_settings();expected=settings.get("webhook_secret") or ""
    if not expected or not hmac.compare_digest(secret,expected):return jsonify({"ok":False}),404
    update=request.get_json(silent=True) or {};message,text,chat,sender,sender_name=_message_payload(update)
    if not message or not text:return jsonify({"ok":True,"ignored":"no_text"})
    chat_id=chat.get("id");message_id=message.get("message_id");chat_type=str(chat.get("type") or "").lower()
    if chat_type not in GROUP_TYPES:return jsonify({"ok":True,"ignored":"private_or_non_group"})
    allowed=set(settings.get("allowed_chat_ids") or [])
    if not allowed or str(chat_id) not in allowed:return jsonify({"ok":True,"ignored":"chat_not_allowed"})
    flat=_normalize_text(text)
    if ASSISTANT_WAKE in flat:
        _send_chat(settings,chat_id,_assistant_reply(flat),message_id);return jsonify({"ok":True,"assistant":True})
    parsed=_extract_job(text)
    if not parsed:return jsonify({"ok":True,"ignored":"not_work"})
    with get_db() as db,db.cursor() as cur:
        customer_id=_find_customer_by_phone(cur,parsed.get("phone"));cur.execute("""insert into bale_jobs(bale_update_id,chat_id,chat_title,message_id,sender_id,sender_name,raw_text,customer_name,phone,address,job_type,customer_id,parsed) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict(chat_id,message_id) do nothing returning id""",(update.get("update_id"),chat_id,chat.get("title"),message_id,sender.get("id"),sender_name,str(text)[:8000],parsed.get("customer_name"),parsed.get("phone"),parsed.get("address"),parsed.get("job_type"),customer_id,Jsonb(parsed)));row=cur.fetchone()
    if row:_send_chat(settings,chat_id,"✅ کار در AquaGold ثبت شد",message_id);return jsonify({"ok":True,"registered":True,"job_id":str(row["id"])})
    return jsonify({"ok":True,"duplicate":True})

@app.post("/api/mini/bale/activate")
@auth_required
def activate_bale():
    settings=_settings()
    if not settings.get("bot_token"):return jsonify({"error":"توکن ربات بله در تنظیمات AquaGold پیدا نشد"}),400
    if not settings.get("webhook_secret"):return jsonify({"error":"webhook secret ربات تنظیم نشده"}),400
    if not settings.get("allowed_chat_ids"):return jsonify({"error":"هیچ گروه مجازی برای ربات تعریف نشده"}),400
    base=request.host_url.rstrip("/");webhook=f"{base}/api/bale/webhook/{settings['webhook_secret']}";webhook_result=_bale_call(settings["bot_token"],"setWebhook",{"url":webhook});sent=0
    for chat_id in settings["allowed_chat_ids"]:
        markup={"inline_keyboard":[[{"text":"💧 باز کردن AquaGold","web_app":{"url":base}}]]}
        if _send_chat(settings,chat_id,"AquaGold Bale آماده است. از دکمه زیر مینی‌اپ را باز کن 👇",reply_markup=markup):sent+=1
    return jsonify({"ok":True,"webhook":webhook,"webhook_result":webhook_result,"groups":len(settings["allowed_chat_ids"]),"button_sent":sent})

if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")))
