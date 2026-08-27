import os
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from flask import jsonify, request

# Ensure production can start even when Vercel has no explicit session secret yet.
import aquagold_secret_bootstrap  # noqa: E402,F401
import app_v3
from aquagold_validation import text as valid_text
from ai_intake import parse_with_ai


def _row_json(row):
    out = {}
    for key, value in dict(row).items():
        if isinstance(value, Decimal):
            value = float(value)
        elif isinstance(value, UUID):
            value = str(value)
        elif isinstance(value, (date, datetime)):
            value = value.isoformat()
        out[key] = value
    return out


app_v3.row_json = _row_json
app = app_v3.app

# Registers v3/v4/v6 extensions, Aqua AI, Bale intake and PostgreSQL compatibility fixes.
import app_extras  # noqa: E402,F401
import app_fixes  # noqa: E402,F401
import app_commerce  # noqa: E402,F401
import app_routing  # noqa: E402,F401
import aqua_ai  # noqa: E402,F401
import bale_bridge  # noqa: E402,F401


@app_v3.roles_required("technician")
def _smart_parse_ai():
    text = valid_text((request.get_json() or {}).get("text"), "متن", required=True, max_length=8000)
    return jsonify(parse_with_ai(text))


app.view_functions["smart_parse"] = _smart_parse_ai

# Safe runtime diagnostic: exposes only whether providers are configured, never secrets.
_original_health = app.view_functions["health"]


def _health_with_ai_status():
    response = app.make_response(_original_health())
    if response.is_json:
        payload = response.get_json() or {}
        status = aqua_ai.configuration_status()
        payload["ai"] = "configured" if status["brain"] else "not_configured"
        payload["aqua_ai"] = status
        try:
            bale = bale_bridge._public_settings(bale_bridge._load_settings())
            payload["bale"] = {"enabled": bale["enabled"], "token": bale["bot_token_configured"], "webhook": bale["webhook_configured"]}
        except Exception:
            payload["bale"] = {"enabled": False, "token": False, "webhook": False}
        return jsonify(payload), response.status_code
    return response


app.view_functions["health"] = _health_with_ai_status

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
