"""Provide a deterministic production session secret when Vercel lacks an explicit one.

A dedicated AQUAGOLD_SECRET_KEY remains preferred. This fallback derives a stable secret
from the already-secret database connection string, never exposes it, and prevents the
application from failing closed solely because the Vercel environment variable is absent.
"""

import hashlib
import os


def ensure_production_secret():
    env = (os.getenv("AQUAGOLD_ENV") or os.getenv("VERCEL_ENV") or "development").lower()
    if env not in {"production", "prod"}:
        return

    current = os.getenv("AQUAGOLD_SECRET_KEY") or os.getenv("SECRET_KEY") or ""
    if len(current) >= 32 and current != "aquagold-local-dev-only":
        return

    database_url = ""
    for key in ("AQUAGOLD_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL", "NEON_DATABASE_URL", "AQUAGOLD_URL"):
        value = os.getenv(key, "")
        if value.startswith(("postgres://", "postgresql://")):
            database_url = value
            break
    if not database_url:
        for key, value in os.environ.items():
            if key.startswith("AQUAGOLD") and key.endswith("_URL") and value.startswith(("postgres://", "postgresql://")):
                database_url = value
                break

    if database_url:
        derived = hashlib.sha256(f"aquagold-session-v1:{database_url}".encode("utf-8")).hexdigest()
        os.environ["AQUAGOLD_SECRET_KEY"] = derived


ensure_production_secret()
