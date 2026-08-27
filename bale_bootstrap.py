"""One-time Bale token bootstrap. Staging value is erased after encryption."""

import base64
import hmac

from flask import jsonify

import app_v3
import bale_bridge


@app_v3.app.get("/api/bale/bootstrap/<secret>")
@app_v3.limiter.exempt
def bale_bootstrap(secret):
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select value from app_settings where key='bale_bot' for update")
        row = cur.fetchone()
        stored = dict((row or {}).get("value") or {})
        expected = str(stored.get("webhook_secret") or "")
        if not expected or not hmac.compare_digest(secret, expected):
            return jsonify({"ok": False}), 404
        encoded = str(stored.pop("bootstrap_token_b64", "") or "")
        if not encoded:
            return jsonify({"ok": True, "already_bootstrapped": bool(stored.get("bot_token_cipher"))})
        try:
            token = base64.urlsafe_b64decode(encoded.encode()).decode()
        except Exception:
            return jsonify({"ok": False, "error": "bootstrap payload invalid"}), 400
        stored["bot_token_cipher"] = bale_bridge._encrypt(token)
        stored["enabled"] = True
        cur.execute("update app_settings set value=%s,updated_at=now() where key='bale_bot'", (app_v3.Jsonb(stored),))
    result = bale_bridge._bale_call(token, "setWebhook", {"url": bale_bridge._canonical_webhook(secret)})
    return jsonify({"ok": True, "webhook": bool(result.get("ok", True)), "token_staged": False})
