"""Ensure polish controls mount when the dynamic navigation overlay is created."""
from flask import request

import app_v3


@app_v3.app.after_request
def aqua_navigation_controls_fix_asset(response):
    try:
        if request.path != "/aqua-smart-tour.js" or response.status_code != 200:
            return response
        response.direct_passthrough = False
        source = response.get_data(as_text=True)
        old = "refreshVoiceCapability();\n}"
        new = "refreshVoiceCapability();if(typeof aqSetupPolish==='function')aqSetupPolish();\n}"
        if "function aqSetupPolish()" in source and old in source:
            source = source.replace(old, new, 1)
            response.set_data(source)
            response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_controls_fix_failed: %s", str(exc)[:160])
    return response
