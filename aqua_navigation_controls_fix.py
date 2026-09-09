"""Ensure polish controls mount when dynamic Map/navigation UI is created."""
from flask import request

import app_v3


@app_v3.app.after_request
def aqua_navigation_controls_fix_asset(response):
    try:
        if request.path != "/aqua-smart-tour.js" or response.status_code != 200:
            return response
        response.direct_passthrough = False
        source = response.get_data(as_text=True)

        # Keep the existing navigation-polish mount behavior.
        old = "refreshVoiceCapability();\n}"
        new = "refreshVoiceCapability();if(typeof aqSetupPolish==='function')aqSetupPolish();\n}"
        if "function aqSetupPolish()" in source and old in source:
            source = source.replace(old, new, 1)

        # Phase 2 iPhone fix: bind the touch handlers as soon as #mainMap exists,
        # even when Alpine/Leaflet has not created mainMap() yet. Resolve the map
        # only when the hold actually fires. This avoids the startup-time race that
        # left long-press permanently unbound on a real iPhone.
        bind_guard = "const el=$('#mainMap'),m=mainMap();if(!el||!m||el.dataset.aqLongPress==='2')return;el.dataset.aqLongPress='2';"
        bind_guard_fixed = "const el=$('#mainMap');if(!el||el.dataset.aqLongPress==='2')return;el.dataset.aqLongPress='2';"
        hold_fire = "try{const ll=m.containerPointToLatLng([px,py]);selectFreeDestination({lat:ll.lat,lng:ll.lng,name:'مقصد انتخابی روی نقشه',address:'',source:'hold'});navigator.vibrate?.(25)}catch{}"
        hold_fire_fixed = "try{const m=mainMap();if(!m)return;const ll=m.containerPointToLatLng([px,py]);selectFreeDestination({lat:ll.lat,lng:ll.lng,name:'مقصد انتخابی روی نقشه',address:'',source:'hold'});navigator.vibrate?.(25)}catch{}"
        if bind_guard in source and hold_fire in source:
            source = source.replace(bind_guard, bind_guard_fixed, 1)
            source = source.replace(hold_fire, hold_fire_fixed, 1)

        response.set_data(source)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_controls_fix_failed: %s", str(exc)[:160])
    return response
