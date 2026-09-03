"""Keep AquaGold's encryption/session secret stable across Vercel runtimes.

A dedicated AQUAGOLD_SECRET_KEY remains preferred. Isolated Preview databases
have different Neon connection strings, so deriving the encryption key from the
Preview URL would make settings cloned from Production unreadable. Preview may
therefore receive either AQUAGOLD_SHARED_SECRET_KEY (preferred) or the main DB
URL in AQUAGOLD_MAIN_DATABASE_URL as stable secret material. No secret is stored
in the repository.
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


def _stable_secret_material():
    shared = os.getenv("AQUAGOLD_SHARED_SECRET_KEY", "")
    if len(shared) >= 32:
        return "shared:" + shared
    main_url = os.getenv("AQUAGOLD_MAIN_DATABASE_URL", "")
    if main_url.startswith(("postgres://", "postgresql://")):
        return "database:" + main_url
    database_url = _database_url()
    return "database:" + database_url if database_url else ""


def ensure_runtime_secret():
    env = (os.getenv("AQUAGOLD_ENV") or os.getenv("VERCEL_ENV") or "development").lower()
    is_vercel = bool(os.getenv("VERCEL")) or env in {"production", "prod", "preview"}
    if not is_vercel:
        return

    current = os.getenv("AQUAGOLD_SECRET_KEY") or os.getenv("SECRET_KEY") or ""
    if len(current) >= 32 and current != "aquagold-local-dev-only":
        return

    material = _stable_secret_material()
    if not material:
        return

    if material.startswith("shared:"):
        derived = material.split(":", 1)[1]
    else:
        database_url = material.split(":", 1)[1]
        derived = hashlib.sha256(f"aquagold-session-v1:{database_url}".encode("utf-8")).hexdigest()
    os.environ["AQUAGOLD_SECRET_KEY"] = derived


ensure_runtime_secret()
