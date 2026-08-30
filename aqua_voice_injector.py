"""Ensure the Aqua voice hotfix is actually present in the delivered HTML."""
from flask import request

import app_v3


@app_v3.app.after_request
def inject_aqua_voice_hotfix(response):
    try:
        if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
            # send_file/send_from_directory responses are direct-passthrough by default;
            # disable it before reading/mutating the HTML body.
            response.direct_passthrough = False
            body = response.get_data(as_text=True)
            tag = '<script src="/aqua-voice-runtime-hotfix.js?v=20260831-voice3"></script>'
            if "aqua-voice-runtime-hotfix.js" not in body:
                pos = body.lower().find("</head>")
                if pos >= 0:
                    body = body[:pos] + tag + body[pos:]
                    response.set_data(body)
                    response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_voice_injector_failed detail=%s", str(exc)[:200])
    return response
