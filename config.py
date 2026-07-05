"""
config.py — Loads all settings from .env or OS environment.
Fails fast if required variables are missing.
"""
import os, sys
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent

def _require(key):
    val = os.getenv(key)
    if not val:
        print(f"❌ FATAL: Missing required environment variable: {key}", file=sys.stderr)
        print(f"   Copy .env.example to .env and fill in all values.", file=sys.stderr)
        sys.exit(2)
    return val

def _optional(key, default=""):
    return os.getenv(key, default)

HOST = _optional("FLASK_HOST", "0.0.0.0")
PORT = int(_optional("FLASK_PORT", "5000"))
DEBUG = _optional("FLASK_DEBUG", "False").lower() in ("true","1","yes")

SECRET_KEY = _require("SECRET_KEY")
if len(SECRET_KEY) < 32:
    print("❌ FATAL: SECRET_KEY must be at least 32 characters", file=sys.stderr)
    sys.exit(2)

CORS_ORIGINS = [o.strip() for o in _optional("CORS_ORIGINS","*").split(",") if o.strip()]

DATABASE_PATH = str(BASE_DIR / _optional("DATABASE_PATH","data/aquagold.db"))
UPLOAD_DIR = str(BASE_DIR / _optional("UPLOAD_DIR","uploads"))
BACKUP_DIR = str(BASE_DIR / _optional("BACKUP_DIR","backups"))
LOG_DIR = str(BASE_DIR / _optional("LOG_DIR","logs"))
for d in (UPLOAD_DIR, BACKUP_DIR, LOG_DIR, str(Path(DATABASE_PATH).parent)):
    os.makedirs(d, exist_ok=True)

TOKEN_EXPIRE_HOURS = int(_optional("TOKEN_EXPIRE_HOURS","24"))
DEFAULT_ADMIN_USERNAME = _optional("DEFAULT_ADMIN_USERNAME","admin")
DEFAULT_ADMIN_PASSWORD = _require("DEFAULT_ADMIN_PASSWORD")
DEFAULT_FALLBACK_PASSWORD = _optional("DEFAULT_FALLBACK_PASSWORD","Aqua@1234")
MAX_TOKENS_IN_MEMORY = int(_optional("MAX_TOKENS_IN_MEMORY","200"))

LOGIN_RATE_LIMIT = _optional("LOGIN_RATE_LIMIT","10/minute")
RATE_LIMIT_STORAGE = _optional("RATE_LIMIT_STORAGE","memory://")
RATE_LIMIT_DEFAULT = _optional("RATE_LIMIT_DEFAULT","600/day,120/hour")

LOG_LEVEL = _optional("LOG_LEVEL","INFO").upper()
LOG_FORMAT = _optional("LOG_FORMAT","%(asctime)s %(levelname)s %(message)s")

DEFAULT_COMPANY_NAME = _optional("DEFAULT_COMPANY_NAME","Aqua Gold")
DEFAULT_OWNER_SHARE = int(_optional("DEFAULT_OWNER_SHARE","50"))
DEFAULT_UNCLE_SHARE = int(_optional("DEFAULT_UNCLE_SHARE","50"))
DEFAULT_SERVICE_INTERVAL = int(_optional("DEFAULT_SERVICE_INTERVAL","180"))
