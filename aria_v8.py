"""Inject the deterministic Aria v8 controller and final UI detail layer after normal AquaGold runtime."""
from flask import request

import app_v3

app = app_v3.app


@app.after_request
def inject_aria_v8(response):
    """Load v8 controllers last without changing the stable index/auth contract."""
    try:
        if request.path == "/" and response.status_code == 200 and "text/html" in (response.content_type or ""):
            html = response.get_data(as_text=True)
            tags = [
                '<script src="/aria-v8.js?v=20260828-v8"></script>',
                '<script src="/ui-detail-v8.js?v=20260828-v8"></script>',
            ]
            insert = "".join(tag for tag in tags if tag not in html)
            if insert and "</body>" in html:
                response.set_data(html.replace("</body>", insert + "</body>"))
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aria_v8_injection_failed: %s", exc)
    return response
