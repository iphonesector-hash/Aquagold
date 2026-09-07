"""Final runtime handler for the /aqua Bale Mini App launcher command.

This wrapper intentionally sits outside the existing Bale webhook wrappers so it
can recognize command updates before normal work-intake parsing. It does not
change the webhook URL, intake logic, Smart flow, Aria, or database schema.
"""
from __future__ import annotations

import hmac
import re

from flask import jsonify, request

import app_v3
import bale_bridge

BALE_MINIAPP_DIRECT_URL = "https://ble.ir/aqua_goldbot?startapp"
AQUA_LAUNCHER_TEXT = "لطفاً برای ورود به مینی‌اپ آکوا، دکمه زیر را بزنید 👇"
BIDI_MARKS = "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff"


def _clean_text(value):
    text = str(value or "")
    for mark in BIDI_MARKS:
        text = text.replace(mark, "")
    text = text.replace("\u200c", " ")
    return re.sub(r"\s+", " ", text).strip()


def _is_aqua_command(text):
    value = _clean_text(text)
    if not value:
        return False
    return bool(re.match(r"^/aqua(?:@[A-Za-z0-9_]+)?(?:\s|$)", value, flags=re.IGNORECASE))


def _message_payload(update):
    message = update.get("message") or update.get("edited_message") or update.get("channel_post") or {}
    text = message.get("text") or message.get("caption") or ""
    chat = message.get("chat") or {}
    return message, text, chat


def _send_launcher(settings, chat_id):
    token = settings.get("bot_token") or ""
    if not token:
        return False
    result = bale_bridge._bale_call(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": AQUA_LAUNCHER_TEXT,
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "💧 باز کردن AquaGold", "url": BALE_MINIAPP_DIRECT_URL}
                ]]
            },
        },
        timeout=8,
    )
    return bool(result.get("ok", True)) if isinstance(result, dict) else True


_old_webhook = app_v3.app.view_functions.get("bale_webhook")


def _webhook_with_aqua_command(secret):
    settings = bale_bridge._load_settings()
    expected = str(settings.get("webhook_secret") or "")
    if not expected or not hmac.compare_digest(str(secret), expected):
        return _old_webhook(secret)

    update = request.get_json(silent=True) or {}
    message, text, chat = _message_payload(update)
    if not message or not _is_aqua_command(text):
        return _old_webhook(secret)

    chat_id = chat.get("id")
    if chat_id is None:
        return jsonify({"ok": True, "ignored": "aqua_no_chat"})

    allowed = {str(x) for x in (settings.get("allowed_chat_ids") or []) if str(x)}
    if allowed and str(chat_id) not in allowed:
        return jsonify({"ok": True, "ignored": "chat_not_allowed"})

    try:
        sent = _send_launcher(settings, chat_id)
    except Exception as exc:
        app_v3.logger.warning("bale_aqua_command_send_failed: %s", exc)
        sent = False

    app_v3.logger.info("bale_aqua_command handled sent=%s", sent)
    return jsonify({"ok": True, "aqua_launcher": True, "sent": sent})


if _old_webhook is not None:
    app_v3.app.view_functions["bale_webhook"] = _webhook_with_aqua_command
