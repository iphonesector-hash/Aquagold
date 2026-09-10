"""Map-only CTA bridge for legacy optimized routes.

Keeps the existing optimizer untouched but exposes a visible Start Navigation
button that hands the first stop into the newer in-app Smart Tour navigator.
"""
from __future__ import annotations

from flask import request

import app_v3


@app_v3.app.get("/aqua-smart-tour-start-fix.js")
def aqua_smart_tour_start_fix_js():
    return app_v3.send_from_directory(
        ".",
        "aqua-smart-tour-start-fix.js",
        mimetype="application/javascript",
        max_age=0,
    )


@app_v3.app.after_request
def inject_aqua_smart_tour_start_fix(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        marker = "/aqua-smart-tour-start-fix.js?v=20260908-1"
        if marker not in body:
            body = body.replace(
                "</body>",
                f'<script defer src="{marker}"></script></body>',
                1,
            )
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("smart_tour_start_fix_injection_failed: %s", exc)
    return response
