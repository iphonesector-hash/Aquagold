"""Keep targeted edit modals outside hidden login containers.

Imported after aqua_targeted_fix so this after-request hook runs first and places
its existing modal HTML directly under <body>. No CSS/layout/theme changes.
"""
from flask import request

import app_v3
import aqua_targeted_fix


@app_v3.app.after_request
def mount_targeted_edit_modals_at_body(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        if 'x-show="serviceEditOpen"' not in body:
            body = body.replace("</body>", aqua_targeted_fix.TARGETED_MODAL_HTML + "</body>", 1)
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_targeted_modal_mount_failed detail=%s", str(exc)[:300])
    return response
