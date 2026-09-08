"""Map-only iPhone navigation fallback polish.

When Neshan GL cannot stay active on iOS/Preview, Aqua falls back to Leaflet.
Leaflet is north-up by default, so the vehicle arrow can appear sideways while
travelling west/east. Patch only the final navigation asset to keep the fallback
heading-up while follow mode is active, and keep recenter/resume controls above
all map layers.

No Finance, Aria, Bale, Push, database or Production state is changed.
"""
from __future__ import annotations

import re

from flask import request

import app_v3


_HELPERS = r'''
function aqResetLeafletHeading(){const el=$('#aqst-nav-map');if(!el)return;el.classList.remove('aqst-leaflet-heading-up');el.style.removeProperty('--aqst-fallback-rotation')}
function aqApplyLeafletHeading(h){const el=$('#aqst-nav-map');if(!el)return;h=((Number(h)||0)%360+360)%360;el.classList.add('aqst-leaflet-heading-up');el.style.setProperty('--aqst-fallback-rotation',`${-h}deg`)}
'''.strip()

_SET_FOLLOW = r'''function setFollowMode(on){ST.nav.follow=!!on;const b=$('#aqst-recenter');if(b)b.hidden=!!on;if(!on)aqResetLeafletHeading();if(on&&ST.nav.active&&ST.nav.lastPos)updateDriveCamera(ST.nav.lastPos,ST.nav.lastCoords||{},ST.nav.lastNear||nearestPointInfo(ST.nav.lastPos,ST.nav.route?.points||[]),true)}'''

_CAMERA = r'''function updateDriveCamera(pos,coords,near,immediate=false){if(!ST.nav.follow||!ST.nav.map)return;const route=ST.nav.route,proj=typeof aqRouteProjection==='function'?aqRouteProjection(pos,route):null,matched=proj&&proj.d<=95?{lat:proj.lat,lng:proj.lng}:pos,idx=proj?proj.i:Number(near?.i||0),rem=remainingDistance(route,{...(near||{}),i:idx}),rb=routeBearing(route,idx);let h=Number(coords?.heading),speed=Number(coords?.speed);if(!Number.isFinite(h)||h<0||!Number.isFinite(speed)||speed<1.2)h=rb;if(typeof aqSmoothHeading==='function')h=aqSmoothHeading(h);if(ST.nav.mapKind==='gl'){aqResetLeafletHeading();try{ST.nav.map.easeTo({center:[matched.lng,matched.lat],bearing:h,pitch:rem<180?46:54,zoom:rem<220?18.7:18.25,duration:immediate?0:620,essential:true})}catch{}}else try{ST.nav.map.setView([matched.lat,matched.lng],rem<300?18:17,{animate:!immediate});$('#aqst-nav-arrow')?.style.setProperty('transform',`rotate(${h-90}deg)`);aqApplyLeafletHeading(h)}catch{}}'''


_FALLBACK_CSS = r'''
/* Aqua iPhone fallback heading + navigation control layering — 20260908 */
#aqst-nav .aqst-navmap{overflow:hidden!important;isolation:isolate!important}
#aqst-nav #aqst-nav-map{z-index:1!important;transform-origin:50% 50%!important}
#aqst-nav #aqst-nav-map.aqst-leaflet-heading-up{transform:rotate(var(--aqst-fallback-rotation,0deg)) scale(1.43)!important;transition:transform .42s ease-out!important;will-change:transform!important}
#aqst-nav .aqst-drive-mode{z-index:2147481700!important;pointer-events:none!important}
#aqst-nav #aqst-recenter{position:absolute!important;z-index:2147481800!important;left:12px!important;bottom:14px!important;pointer-events:auto!important}
#aqst-nav #aqst-recenter[hidden]{display:none!important}
#aqst-nav-resume{position:fixed!important;z-index:2147481800!important;left:14px!important;bottom:calc(96px + env(safe-area-inset-bottom,0px))!important;pointer-events:auto!important}
#aqst-nav-resume[hidden]{display:none!important}
@media(max-width:700px){
 #aqst-nav #aqst-recenter{left:10px!important;bottom:12px!important;min-height:44px!important}
 #aqst-nav-resume{left:12px!important;bottom:calc(92px + env(safe-area-inset-bottom,0px))!important;min-height:44px!important}
}
'''.strip()


def _replace_function(source: str, name: str, next_name: str, replacement: str) -> str:
    pattern = rf"function\s+{re.escape(name)}\(.*?(?=\nfunction\s+{re.escape(next_name)}\()"
    return re.sub(pattern, replacement + "\n", source, count=1, flags=re.S)


@app_v3.app.after_request
def aqua_navigation_fallback_heading_assets(response):
    try:
        if response.status_code != 200:
            return response
        if request.path == "/aqua-smart-tour.js":
            response.direct_passthrough = False
            source = response.get_data(as_text=True)
            marker = "function aqResetLeafletHeading()"
            if marker not in source and "function setFollowMode(" in source and "function updateDriveCamera(" in source:
                source = source.replace("function setFollowMode(", _HELPERS + "\nfunction setFollowMode(", 1)
                source = _replace_function(source, "setFollowMode", "updateDriveCamera", _SET_FOLLOW)
                source = _replace_function(source, "updateDriveCamera", "showRouteOverview", _CAMERA)
                response.set_data(source)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            marker = "Aqua iPhone fallback heading + navigation control layering — 20260908"
            if marker not in css:
                css += "\n" + _FALLBACK_CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_fallback_heading_asset_failed: %s", str(exc)[:180])
    return response
