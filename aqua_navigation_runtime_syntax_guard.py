"""Final syntax guard for the generated map navigation asset only.

The navigation UI is assembled by multiple branch-scoped after_request layers.
This final guard normalizes the generated async function boundary and Wake Lock
statement before the JavaScript reaches Safari. It also imports the iOS-native
long-press destination picker so that picker is registered in the same map-only
response chain. No other app surface is touched.
"""
from flask import request

import app_v3
import aqua_map_longpress_ios_fix  # noqa: F401


@app_v3.app.after_request
def aqua_navigation_runtime_syntax_guard(response):
    try:
        if request.path != "/aqua-smart-tour.js" or response.status_code != 200:
            return response
        response.direct_passthrough = False
        source = response.get_data(as_text=True)
        source = source.replace("async async function initNavMap", "async function initNavMap")
        source = source.replace("async function aqClamp(v,a,b)", "function aqClamp(v,a,b)")
        source = source.replace("\nfunction startNavigation(target)", "\nasync function startNavigation(target)")
        source = source.replace("\nasync async function startNavigation(target)", "\nasync function startNavigation(target)")
        source = source.replace("await aqAcquireWakeLock()const ", "await aqAcquireWakeLock();const ")
        source = source.replace("await aqAcquireWakeLock()const", "await aqAcquireWakeLock();const")
        response.set_data(source)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_runtime_syntax_guard_failed: %s", str(exc)[:180])
    return response
