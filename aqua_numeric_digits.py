"""Persian/Arabic digit normalization without replacing the finance/map base UI."""
from flask import request

import app_v3


@app_v3.app.get("/aqua-numeric-digits.js")
def aqua_numeric_digits_js():
    return app_v3.send_from_directory(".", "aqua-numeric-digits.js", mimetype="application/javascript", max_age=0)


@app_v3.app.after_request
def inject_aqua_numeric_digits(response):
    if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        if "/aqua-numeric-digits.js" not in body:
            body = body.replace("</body>", '<script src="/aqua-numeric-digits.js?v=20260914-1"></script></body>', 1)
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
    return response
