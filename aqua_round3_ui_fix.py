"""Serve and inject the final branch-only UI data layer after Round 2."""
from flask import request

import app_v3


@app_v3.app.get("/aqua-round3-ui.js")
def aqua_round3_ui_js():
    return app_v3.send_from_directory(".", "aqua-round3-ui.js", mimetype="application/javascript", max_age=0)


@app_v3.app.after_request
def inject_aqua_round3_ui(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        if '/aqua-round3-ui.js?' not in body:
            body = body.replace(
                "</body>",
                '<script src="/aqua-round3-ui.js?v=20260902-1"></script></body>',
                1,
            )
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_round3_ui_inject_failed detail=%s", str(exc)[:300])
    return response
