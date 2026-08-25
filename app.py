from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from flask import jsonify, request

import app_v3
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

# Registers v3 extras and PostgreSQL 18 compatibility fixes.
import app_extras  # noqa: E402,F401
import app_fixes  # noqa: E402,F401


@app_v3.token_required
def _smart_parse_ai():
    text = (request.get_json() or {}).get("text", "")
    if not text.strip():
        return jsonify({"error": "متن لازم است"}), 400
    return jsonify(parse_with_ai(text))


app.view_functions["smart_parse"] = _smart_parse_ai

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
