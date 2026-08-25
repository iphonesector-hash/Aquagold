from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import app_v3


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


# Route functions resolve this helper from app_v3 at request time.
app_v3.row_json = _row_json
app = app_v3.app

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
