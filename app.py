from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import jsonify, request

# Reuse AquaGold's existing stable secret derivation. This keeps encrypted
# Bale settings readable without requiring a separate AQUAGOLD_SECRET_KEY
# when the production project already derives it from its database settings.
import aquagold_secret_bootstrap  # noqa: F401,E402

MODULE_PATH = Path(__file__).resolve().parent / "aqua-bale-standalone" / "app.py"
SPEC = spec_from_file_location("aqua_bale_standalone_app", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load standalone Aqua Bale application")
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

# Safe allowlist recovery for the standalone runtime only:
# if AquaGold has never explicitly stored allowed_chat_ids but all historical
# Bale jobs came from exactly one chat, use that one historical group. If there
# are zero or multiple chats, remain fail-closed.
_ORIGINAL_SETTINGS = MODULE._settings


def _settings_with_single_history_fallback():
    settings = _ORIGINAL_SETTINGS()
    if settings.get("allowed_chat_ids"):
        return settings
    try:
        with MODULE.get_db() as db, db.cursor() as cur:
            cur.execute(
                "select distinct chat_id::text as chat_id from bale_jobs "
                "where chat_id is not null order by chat_id limit 2"
            )
            rows = cur.fetchall()
        candidates = [str(row.get("chat_id")) for row in rows if row.get("chat_id") is not None]
        if len(candidates) == 1:
            settings["allowed_chat_ids"] = candidates
            settings["allowed_chat_ids_source"] = "single_historical_group"
    except Exception:
        pass
    return settings


MODULE._settings = _settings_with_single_history_fallback
app = MODULE.app

# The user explicitly chose not to move the live Bale webhook away from the
# original AquaGold app. Keep the old standalone activation endpoint blocked so
# it cannot be triggered accidentally.
@app.before_request
def _block_standalone_webhook_activation():
    if request.path == "/api/mini/bale/activate":
        return jsonify({"error": "انتقال وب‌هوک ربات غیرفعال است؛ ربات روی AquaGold اصلی باقی می‌ماند."}), 410
    return None


DEFAULT_MINIAPP_URL = (
    os.getenv("AQUA_BALE_PUBLIC_URL")
    or "https://aquagold-bale-git-standalone-aqua-bale-20260906-i-sector.vercel.app"
)


def _validated_miniapp_url(value: str) -> str:
    url = str(value or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise MODULE.ValidationError("آدرس مینی‌اپ باید یک لینک امن HTTPS باشد")
    return url


@app.post("/api/mini/bale/menu-button")
@MODULE.auth_required
def install_bale_menu_button():
    """Set only Bale's default chat menu button; never touch the webhook."""
    settings = MODULE._settings()
    token = settings.get("bot_token") or ""
    if not token:
        return jsonify({"error": "توکن ربات بله در تنظیمات AquaGold پیدا نشد"}), 400

    data = request.get_json(silent=True) or {}
    miniapp_url = _validated_miniapp_url(data.get("url") or DEFAULT_MINIAPP_URL)
    menu_button = {
        "type": "web_app",
        "text": "💧 AquaGold",
        "web_app": {"url": miniapp_url},
    }
    set_result = MODULE._bale_call(token, "setChatMenuButton", {"menu_button": menu_button})
    get_result = MODULE._bale_call(token, "getChatMenuButton", {})
    return jsonify(
        {
            "ok": bool(set_result.get("ok", True)),
            "webhook_changed": False,
            "miniapp_url": miniapp_url,
            "menu_button": get_result.get("result") if isinstance(get_result, dict) else get_result,
        }
    )


# Temporary one-shot installer. It is intentionally scoped to the separate
# aquagold-bale Vercel project and this standalone branch, and it only calls
# setChatMenuButton/getChatMenuButton. It never calls setWebhook.
_MENU_INSTALL_RESULT = {"attempted": False, "ok": False}
if (
    os.getenv("VERCEL_PROJECT_PRODUCTION_URL") == "aquagold-bale.vercel.app"
    and os.getenv("VERCEL_GIT_COMMIT_REF") == "standalone/aqua-bale-20260906"
):
    _MENU_INSTALL_RESULT["attempted"] = True
    try:
        _settings = MODULE._settings()
        _token = _settings.get("bot_token") or ""
        if not _token:
            raise RuntimeError("Bale bot token is not configured")
        _menu_button = {
            "type": "web_app",
            "text": "💧 AquaGold",
            "web_app": {"url": DEFAULT_MINIAPP_URL},
        }
        _set = MODULE._bale_call(_token, "setChatMenuButton", {"menu_button": _menu_button})
        _get = MODULE._bale_call(_token, "getChatMenuButton", {})
        _MENU_INSTALL_RESULT = {
            "attempted": True,
            "ok": bool(_set.get("ok", True)),
            "menu_button": _get.get("result") if isinstance(_get, dict) else _get,
            "webhook_changed": False,
        }
    except Exception as exc:
        _MENU_INSTALL_RESULT = {"attempted": True, "ok": False, "error": str(exc), "webhook_changed": False}


@app.get("/health/menu-button")
def menu_button_health():
    return jsonify(_MENU_INSTALL_RESULT)
