"""Independent Jalali day/month/year picker for expense editing."""
from flask import request

import app_v3


@app_v3.app.get("/aqua-expense-jalali.js")
def aqua_expense_jalali_js():
    return app_v3.send_from_directory(".", "aqua-expense-jalali.js", mimetype="application/javascript", max_age=0)


@app_v3.app.after_request
def inject_expense_jalali(response):
    if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        if "/aqua-expense-jalali.js" not in body:
            body = body.replace("</body>", '<script src="/aqua-expense-jalali.js?v=20260914-1"></script></body>', 1)
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
    return response
