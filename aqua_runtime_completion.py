"""Final branch-scoped runtime completion for the requested AquaGold QA items."""
from __future__ import annotations

from flask import request

import app_v3


@app_v3.app.get("/aqua-runtime-completion.js")
def aqua_runtime_completion_js():
    return app_v3.send_from_directory(".", "aqua-runtime-completion.js", mimetype="application/javascript", max_age=0)


@app_v3.app.after_request
def inject_aqua_runtime_completion(response):
    if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        if "/aqua-runtime-completion.js" not in body:
            body = body.replace("</head>", '<style id="aqua-runtime-completion-style">#expenseJalaliPicker{width:100%;max-width:100%;min-width:0;box-sizing:border-box;overflow:hidden}#expenseJalaliPicker *{box-sizing:border-box;min-width:0}#expenseJalaliPicker .aq-jalali-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}#expenseJalaliPicker .aq-jalali-time{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:8px}#expenseJalaliPicker select{width:100%;max-width:100%;min-width:0}.aq-map-frame>#aqst-controls{display:none!important}#aqst-controls.aqst-controls-outside{display:block!important;position:relative!important;inset:auto!important;z-index:5!important;width:100%!important;margin:8px 0 0!important}.aqst-controls-outside .aqst-toolbar{margin:0!important}@media(max-width:600px){#expenseJalaliPicker{padding:10px!important}#expenseJalaliPicker .aq-jalali-grid{gap:5px}#expenseJalaliPicker select{font-size:13px;padding-left:4px!important;padding-right:4px!important}.aqst-controls-outside .aqst-toolbar{grid-template-columns:1fr!important}}</style></head>', 1)
            body = body.replace("</body>", '<script src="/aqua-runtime-completion.js?v=20260914-4"></script></body>', 1)
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
    return response
