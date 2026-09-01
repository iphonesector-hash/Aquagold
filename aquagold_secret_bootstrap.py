"""Keep AquaGold's encryption/session secret stable across Vercel runtimes.

A dedicated AQUAGOLD_SECRET_KEY remains preferred. When it is unavailable on a
Vercel deployment, derive the same deterministic secret from the already-secret
database connection string. This keeps encrypted Aqua AI provider settings
readable on manual Preview deployments without exposing or copying API keys.
"""

import hashlib
import os


def _database_url():
    for key in ("AQUAGOLD_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL", "NEON_DATABASE_URL", "AQUAGOLD_URL"):
        value = os.getenv(key, "")
        if value.startswith(("postgres://", "postgresql://")):
            return value
    for key, value in os.environ.items():
        if key.startswith("AQUAGOLD") and key.endswith("_URL") and value.startswith(("postgres://", "postgresql://")):
            return value
    return ""


def ensure_runtime_secret():
    env = (os.getenv("AQUAGOLD_ENV") or os.getenv("VERCEL_ENV") or "development").lower()
    is_vercel = bool(os.getenv("VERCEL")) or env in {"production", "prod", "preview"}
    if not is_vercel:
        return

    current = os.getenv("AQUAGOLD_SECRET_KEY") or os.getenv("SECRET_KEY") or ""
    if len(current) >= 32 and current != "aquagold-local-dev-only":
        return

    database_url = _database_url()
    if not database_url:
        return

    derived = hashlib.sha256(f"aquagold-session-v1:{database_url}".encode("utf-8")).hexdigest()
    os.environ["AQUAGOLD_SECRET_KEY"] = derived


ensure_runtime_secret()
