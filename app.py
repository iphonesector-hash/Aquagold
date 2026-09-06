from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import jsonify, request

import aquagold_secret_bootstrap  # noqa: F401,E402

MODULE_PATH = Path(__file__).resolve().parent / "aqua-bale-standalone" / "app.py"
SPEC = spec_from_file_location("aqua_bale_standalone_app", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load standalone Aqua Bale application")
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

_ORIGINAL_SETTINGS = MODULE._settings


def _settings_with_single_history_fallback():
    settings = _ORIGINAL_SETTINGS()
    if settings.get("allowed_chat_ids"):
        return settings
    try:
        with MODULE.get_db() as db, db.cursor() as cur:
            cur.execute("select distinct chat_id::text as chat_id from bale_jobs where chat_id is not null order by chat_id limit 2")
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

@app.before_request
def _block_standalone_webhook_activation():
    if request.path == "/api/mini/bale/activate":
        return jsonify({"error": "انتقال وب‌هوک ربات غیرفعال است؛ ربات روی AquaGold اصلی باقی می‌ماند."}), 410
    return None

DEFAULT_MINIAPP_URL = os.getenv("AQUA_BALE_PUBLIC_URL") or "https://aquagold-bale-git-standalone-aqua-bale-20260906-i-sector.vercel.app"


def _validated_miniapp_url(value: str) -> str:
    url = str(value or "").strip(); parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise MODULE.ValidationError("آدرس مینی‌اپ باید یک لینک امن HTTPS باشد")
    return url


def _markup(url: str):
    return {"inline_keyboard": [[{"text": "💧 باز کردن AquaGold", "url": url}]]}


def _native_group_keyboard(url: str):
    return {
        "keyboard": [[{"text": "💧 AquaGold", "web_app": {"url": url}}]],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "is_persistent": True,
    }


@app.post("/api/mini/bale/send-button")
@MODULE.auth_required
def send_bale_miniapp_button():
    settings = MODULE._settings()
    if not settings.get("bot_token"):
        return jsonify({"error": "توکن ربات بله پیدا نشد"}), 400
    chats = settings.get("allowed_chat_ids") or []
    if not chats:
        return jsonify({"error": "گروه مجاز پیدا نشد"}), 400
    data = request.get_json(silent=True) or {}
    url = _validated_miniapp_url(data.get("url") or DEFAULT_MINIAPP_URL)
    sent = 0
    for chat_id in chats:
        result = MODULE._send_chat(settings, chat_id, "💧 AquaGold Bale آماده است. این دکمه مستقیم باز می‌شود 👇", reply_markup=_markup(url))
        if isinstance(result, dict) and result.get("ok", True):
            sent += 1
    return jsonify({"ok": sent > 0, "button_sent": sent, "webhook_changed": False})
