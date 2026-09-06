"""Final field-runtime repair for AquaGold test preview.

This module is imported early so its after_request hook runs after later UI
injectors (Flask executes after_request handlers in reverse registration order).
It only:
- injects the final iPhone mic + daily-edit runtime script last in the HTML;
- normalizes the older loader rewrite to the exact v2 Aqua Sector artwork.
"""
from __future__ import annotations

import re

from flask import request

import app_v3


FINAL_JS = "/aqua-round8-field-fixes.js"
FINAL_LOADER = "/assets/aquagold-loading-v20260906b.jpg?aqua-loader-exact-2"

_OLD_FORCED_LOADER = "/assets/aquagold-loading-v20260906.jpg?aqua-loader-exact-2"
_BOOT_IMAGE_RE = re.compile(
    r'(<div id="aqua-boot-20260906"[\s\S]*?<img\s+src=")[^"]+(")',
    re.I,
)


@app_v3.app.get(FINAL_JS)
def aqua_round8_field_fixes_js():
    return app_v3.send_from_directory(
        ".",
        "aqua-round8-field-fixes.js",
        mimetype="application/javascript",
        max_age=0,
    )


@app_v3.app.after_request
def finalize_aqua_round8_field_runtime(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response

        response.direct_passthrough = False
        body = response.get_data(as_text=True)

        # One older inline observer still rewrites the new boot image back to
        # the legacy 20260906 asset. Rewrite that literal in the final HTML so
        # both the initial image and that observer stay on the v2 artwork.
        body = body.replace(_OLD_FORCED_LOADER, FINAL_LOADER)
        body = _BOOT_IMAGE_RE.sub(r"\1" + FINAL_LOADER + r"\2", body, count=1)

        # This handler runs last, so the script is parser-loaded after all older
        # body-end wrappers but still before deferred Alpine initializes app().
        if FINAL_JS + "?" not in body:
            body = body.replace(
                "</body>",
                f'<script src="{FINAL_JS}?v=20260906-1"></script></body>',
                1,
            )

        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_round8_field_runtime_failed detail=%s", str(exc)[:320])
    return response
