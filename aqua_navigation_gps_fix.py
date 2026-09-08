"""Tiny branch-only asset patch: keep the live nav marker on the routed road.

Runs after the professional nav fragment is emitted and before final polish.
"""
from flask import request

import app_v3


@app_v3.app.after_request
def aqua_navigation_gps_fix_asset(response):
    try:
        if request.path != "/aqua-smart-tour.js" or response.status_code != 200:
            return response
        response.direct_passthrough = False
        source = response.get_data(as_text=True)
        old = "if(ST.nav.mapKind==='gl')ST.nav.marker?.setLngLat?.([pos.lng,pos.lat]);else ST.nav.marker?.setLatLng?.([pos.lat,pos.lng]);"
        new = "const aqVisiblePos=(typeof aqMatchedPosition==='function'?aqMatchedPosition(pos,route):pos);ST.nav.lastMatched=aqVisiblePos;if(ST.nav.mapKind==='gl')ST.nav.marker?.setLngLat?.([aqVisiblePos.lng,aqVisiblePos.lat]);else ST.nav.marker?.setLatLng?.([aqVisiblePos.lat,aqVisiblePos.lng]);if(typeof aqSyncMainNavMini==='function')aqSyncMainNavMini(aqVisiblePos);"
        if old in source:
            source = source.replace(old, new, 1)
            response.set_data(source)
            response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_gps_fix_failed: %s", str(exc)[:160])
    return response
