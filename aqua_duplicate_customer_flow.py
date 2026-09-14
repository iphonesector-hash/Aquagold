"""UI-only guard for duplicate Smart Intake customers and stable final-submit retries."""
from flask import request

import app_v3


@app_v3.app.get("/aqua-duplicate-customer.js")
def aqua_duplicate_customer_js():
    return app_v3.send_from_directory(".", "aqua-duplicate-customer.js", mimetype="application/javascript", max_age=0)


@app_v3.app.after_request
def inject_duplicate_customer_flow(response):
    if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        if "/aqua-duplicate-customer.js" not in body:
            body = body.replace("</body>", '<script src="/aqua-duplicate-customer.js?v=20260914-1"></script></body>', 1)
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
    return response
