from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path

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

BALE_MINIAPP_DIRECT_URL = os.getenv("AQUA_BALE_DIRECT_LINK") or "https://ble.ir/aqua_goldbot?startapp"


def _group_miniapp_markup():
    return {"inline_keyboard": [[{"text": "💧 باز کردن AquaGold", "url": BALE_MINIAPP_DIRECT_URL}]]}


@app.post("/api/mini/bale/send-button")
@MODULE.auth_required
def send_bale_miniapp_button():
    settings = MODULE._settings()
    if not settings.get("bot_token"):
        return jsonify({"error": "توکن ربات بله پیدا نشد"}), 400
    chats = settings.get("allowed_chat_ids") or []
    if not chats:
        return jsonify({"error": "گروه مجاز پیدا نشد"}), 400
    sent = 0
    for chat_id in chats:
        result = MODULE._send_chat(
            settings,
            chat_id,
            "💧 AquaGold را داخل خود بله باز کن 👇",
            reply_markup=_group_miniapp_markup(),
        )
        if isinstance(result, dict) and result.get("ok", True):
            sent += 1
    return jsonify({"ok": sent > 0, "button_sent": sent, "webhook_changed": False})


@app.get("/__aqua_pin_launcher_5a8c2f")
def _pin_launcher_once():
    settings = MODULE._settings()
    chats = settings.get("allowed_chat_ids") or []
    if not settings.get("bot_token") or not chats:
        return jsonify({"ok": False, "error": "bot_or_group_missing", "webhook_changed": False}), 400
    pinned = 0
    failures = []
    for chat_id in chats:
        try:
            sent = MODULE._send_chat(
                settings,
                chat_id,
                "💧 دسترسی سریع AquaGold — همیشه از پیام سنجاق‌شده بازش کن 👇",
                reply_markup=_group_miniapp_markup(),
            )
            result = sent.get("result") if isinstance(sent, dict) else None
            message_id = (result or {}).get("message_id") if isinstance(result, dict) else None
            if message_id is None and isinstance(sent, dict):
                message_id = sent.get("message_id")
            if message_id is None:
                failures.append("message_id_missing")
                continue
            pin_result = MODULE._bale_call(
                settings["bot_token"],
                "pinChatMessage",
                {"chat_id": chat_id, "message_id": message_id, "disable_notification": True},
                8,
            )
            if isinstance(pin_result, dict) and pin_result.get("ok", True):
                pinned += 1
            else:
                failures.append("pin_rejected")
        except Exception as exc:
            failures.append(str(exc)[:180])
    return jsonify({"ok": pinned > 0, "pinned": pinned, "failures": failures, "webhook_changed": False})
