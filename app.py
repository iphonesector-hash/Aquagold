import os
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from flask import jsonify, request

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

# Registers v3/v4/v6 extensions, Farangis bridge and PostgreSQL 18 compatibility fixes.
import app_extras  # noqa: E402,F401
import app_fixes  # noqa: E402,F401
import app_commerce  # noqa: E402,F401
import app_routing  # noqa: E402,F401
import farangis_bridge  # noqa: E402,F401


@app_v3.roles_required("technician")
def _smart_parse_ai():
    text = valid_text((request.get_json() or {}).get("text"), "متن", required=True, max_length=8000)
    return jsonify(parse_with_ai(text))


app.view_functions["smart_parse"] = _smart_parse_ai

# Safe runtime diagnostic: exposes only whether Groq is configured, never the key itself.
_original_health = app.view_functions["health"]


def _health_with_ai_status():
    response = app.make_response(_original_health())
    if response.is_json:
        payload = response.get_json() or {}
        payload["ai"] = "configured" if os.getenv("GROQ_API_KEY") else "not_configured"
        payload["farangis_bridge"] = "configured" if os.getenv("FARANGIS_INTEGRATION_TOKEN") else "not_configured"
        return jsonify(payload), response.status_code
    return response


app.view_functions["health"] = _health_with_ai_status

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
