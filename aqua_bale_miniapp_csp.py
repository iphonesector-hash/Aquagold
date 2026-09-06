"""Route-scoped security headers for the Bale Mini App only."""
from flask import request

import app_v3


@app_v3.app.after_request
def aqua_bale_miniapp_security_headers(response):
    if request.path == "/bale-mini":
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
            "img-src 'self' data: blob: https:; font-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline' https://tapi.bale.ai; "
            "connect-src 'self' https://tapi.bale.ai; worker-src 'self' blob:; manifest-src 'self'"
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response
