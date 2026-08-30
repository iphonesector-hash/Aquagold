"""Ensure the Aqua voice hotfix and iOS Persian TTS patch are delivered in order."""
from flask import request

import app_v3


@app_v3.app.after_request
def inject_aqua_voice_hotfix(response):
    try:
        if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
            response.direct_passthrough = False
            body = response.get_data(as_text=True)
            tags = (
                '<script src="/aqua-voice-runtime-hotfix.js?v=20260831-dariush2"></script>'
                '<script src="/aqua-ios-tts-patch.js?v=20260831-ios1"></script>'
            )
            if "aqua-ios-tts-patch.js" not in body:
                # Remove any older injected voice runtime tag so the ordered pair is deterministic.
                import re
                body = re.sub(r'<script src="/aqua-voice-runtime-hotfix\.js\?v=[^"]+"></script>', '', body)
                pos = body.lower().find("</head>")
                if pos >= 0:
                    body = body[:pos] + tags + body[pos:]
                    response.set_data(body)
                    response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_voice_injector_failed detail=%s", str(exc)[:200])
    return response
