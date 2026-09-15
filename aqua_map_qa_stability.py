'''Branch-only Map/Navigation stabilization for iPhone QA.

Keeps Finance, Bale, Aria, production config and database schema untouched.
'''

from __future__ import annotations

import math
import re

from flask import request

import app_v3
import aqua_neshan_preview as neshan


def _append_points(target, points):
    for raw in points or []:
        try:
            lat, lng = float(raw[0]), float(raw[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        point = [lat, lng]
        if not target or target[-1] != point:
            target.append(point)


def _decode_geometry(value):
    if not value:
        return []
    if isinstance(value, str):
        return neshan.decode_polyline(value)
    if isinstance(value, dict):
        for key in ("points", "polyline", "encodedPolyline", "encoded_polyline"):
            if value.get(key):
                return _decode_geometry(value.get(key))
        coords = value.get("coordinates")
        if isinstance(coords, list):
            out = []
            for raw in coords:
                try:
                    lng, lat = float(raw[0]), float(raw[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180:
                    out.append([lat, lng])
            return out
    return []


def _detailed_direction(payload: dict):
    routes = payload.get("routes") or []
    if not routes:
        return {"points": [], "steps": [], "legs": [], "distance_m": 0, "duration_s": 0, "summary": ""}

    route = routes[0]
    overview = _decode_geometry(route.get("overview_polyline"))
    route_detail = []
    legs_out = []
    all_steps = []
    total_distance = 0
    total_duration = 0
    summaries = []

    for leg in route.get("legs") or []:
        distance_obj = leg.get("distance") or {}
        duration_obj = leg.get("duration") or {}
        distance = int(distance_obj.get("value") or 0)
        duration = int(duration_obj.get("value") or 0)
        total_distance += distance
        total_duration += duration
        summary = str(leg.get("summary") or "").strip()
        if summary:
            summaries.append(summary)

        leg_points = []
        steps_out = []
        for step in leg.get("steps") or []:
            raw_start = step.get("start_location") or []
            start = [raw_start[1], raw_start[0]] if isinstance(raw_start, (list, tuple)) and len(raw_start) >= 2 else None
            step_points = _decode_geometry(step.get("polyline") or step.get("geometry"))
            _append_points(leg_points, step_points)
            _append_points(route_detail, step_points)

            step_distance = step.get("distance") or {}
            step_duration = step.get("duration") or {}
            item = {
                "instruction": step.get("instruction") or step.get("name") or "ادامه مسیر",
                "name": step.get("name") or "",
                "type": step.get("type") or "continue",
                "modifier": step.get("modifier") or "straight",
                "bearing_after": step.get("bearing_after"),
                "exit": step.get("exit"),
                "rotary_name": step.get("rotary_name"),
                "distance_m": int(step_distance.get("value") or 0),
                "distance_text": step_distance.get("text") or "",
                "duration_s": int(step_duration.get("value") or 0),
                "duration_text": step_duration.get("text") or "",
                "start": start,
                "points": step_points,
            }
            steps_out.append(item)
            all_steps.append(item)

        if len(leg_points) < 2:
            leg_fallback = _decode_geometry(leg.get("polyline") or leg.get("geometry"))
            _append_points(leg_points, leg_fallback)
            _append_points(route_detail, leg_fallback)

        legs_out.append({
            "summary": summary,
            "distance_m": distance,
            "distance_text": distance_obj.get("text") or "",
            "duration_s": duration,
            "duration_text": duration_obj.get("text") or "",
            "points": leg_points,
            "steps": steps_out,
        })

    if len(route_detail) >= 2 and len(route_detail) >= len(overview):
        points = route_detail
        geometry_source = "steps"
    else:
        points = overview or route_detail
        geometry_source = "overview"

    return {
        "points": points,
        "steps": all_steps,
        "legs": legs_out,
        "distance_m": total_distance,
        "duration_s": total_duration,
        "summary": " - ".join(dict.fromkeys(summaries)),
        "geometry_source": geometry_source,
    }


@app_v3.app.before_request
def aqua_map_qa_use_detailed_direction():
    # aqua_navigation_pro assigns its normalizer later at startup. Re-assert this
    # one at request time so routing always uses the densest official geometry.
    if neshan.normalize_direction is not _detailed_direction:
        neshan.normalize_direction = _detailed_direction


_DISABLED_NORMAL_NESHAN = r'''async function aqSetupMainNeshan(){
 const bg=$('#aqst-main-neshan-bg');
 try{ST.nav.mainNeshan?.remove?.()}catch{}
 ST.nav.mainNeshan=null;
 if(bg)bg.remove();
 $('.aq-map-frame')?.classList.remove('aqst-main-neshan-ready');
 return false;
}'''

_REMAINING_ROUTE = r'''function aqRemainingRoutePoints(route,projection){
 const pts=route?.points||[];if(!pts.length)return[];
 const i=Math.max(0,Math.min(Math.floor(Number(projection?.i||0)),pts.length-1));
 const first=projection&&Number.isFinite(Number(projection.lat))&&Number.isFinite(Number(projection.lng))?[Number(projection.lat),Number(projection.lng)]:pts[i];
 const rest=pts.slice(i+1);
 return rest.length?[first,...rest]:[first,first]
}'''

_QA_CSS = r'''
/* Aqua Map iPhone QA stability — single normal-map engine + collision fixes. */
#aqst-map-tools-drawer{z-index:20!important;margin-top:4px!important}
#aqst-map-tools-panel,#aqst-map-tools-content{min-width:0!important;max-width:100%!important}
#aqst-map-tools-content .aqst-legend{display:grid!important;grid-template-columns:minmax(0,1fr)!important;gap:5px!important;align-items:start!important;width:100%!important;padding-top:7px!important}
#aqst-map-tools-content .aqst-legend>span{display:flex!important;width:100%!important;min-width:0!important;align-items:center!important}
#aqst-map-tools-content .aqst-free-hint{display:block!important;width:100%!important;line-height:1.8!important}
.aqst-map-sheet{overflow-x:hidden!important;box-sizing:border-box!important}
.aqst-special-editor,.aqst-special-editor form,.aqst-special-emojis{min-width:0!important;max-width:100%!important;overflow-x:hidden!important}
#aqst-special-emoji-options{display:grid!important;grid-template-columns:repeat(6,minmax(0,1fr))!important;gap:6px!important;width:100%!important;max-width:100%!important;overflow:visible!important;padding:2px 0 4px!important}
#aqst-special-emoji-options .aqst-special-emoji-option{width:100%!important;min-width:0!important;max-width:100%!important;height:38px!important;flex:none!important;padding:0!important}
.aq-map-frame:before,.aq-map-frame:after{animation:none!important;filter:none!important}
#aqst-main-neshan-bg{display:none!important}
.aq-map-frame #mainMap{background:var(--surface-2)!important}
.aq-map-frame #mainMap .leaflet-tile-pane{opacity:1!important}
.aq-map-frame #mainMap .leaflet-control-attribution{display:grid!important;grid-auto-flow:row!important;gap:1px!important;max-width:145px!important;white-space:normal!important;line-height:1.25!important;text-align:start!important}
.aq-map-frame #mainMap .leaflet-control-attribution>a{display:block!important}
.aq-map-frame #mainMap .leaflet-bottom{bottom:74px!important}
#aqst-nav .mapboxgl-ctrl-attrib-inner{display:grid!important;grid-auto-flow:row!important;gap:1px!important;max-width:145px!important;white-space:normal!important;line-height:1.25!important}
#aqst-nav .mapboxgl-ctrl-attrib-inner>a,#aqst-nav .mapboxgl-ctrl-attrib-inner>span{display:block!important}
html.aqst-nav-fullscreen #aqst-nav .mapboxgl-ctrl-bottom-left,html.aqst-nav-fullscreen #aqst-nav .mapboxgl-ctrl-bottom-right{bottom:calc(var(--aqst-foot-clear,150px) + 6px)!important}
html.aqst-nav-fullscreen #aqst-nav .aqst-drive-mode{bottom:calc(var(--aqst-foot-clear,150px) + 8px)!important}
@media(max-width:700px){#aqst-map-tools-drawer{z-index:20!important}.aqst-map-sheet{right:7px!important;left:7px!important;width:auto!important;max-width:calc(100% - 14px)!important}#aqst-special-emoji-options{grid-template-columns:repeat(6,minmax(0,1fr))!important}.aq-map-frame #mainMap .leaflet-bottom{bottom:78px!important}}
'''.strip()


def _patch_js(source: str) -> str:
    source, count = re.subn(
        r"async function aqSetupMainNeshan\(\)\{.*?\n\}\nfunction aqSetupPolish",
        _DISABLED_NORMAL_NESHAN + "\nfunction aqSetupPolish",
        source,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("normal-map Neshan helper was not found exactly once")

    polish_observer = (
        "const aqPolishObserver=new MutationObserver(()=>{aqTidyMapToolbar();if($('#mainMap'))aqSetupMainNeshan()});\n"
        "aqPolishObserver.observe(document.documentElement,{subtree:true,childList:true});"
    )
    if polish_observer not in source:
        raise RuntimeError("polish observer was not found")
    source = source.replace(polish_observer, "const aqPolishObserver={disconnect(){}};", 1)

    root_observer = "const obs=new MutationObserver(()=>enhance());obs.observe(document.documentElement,{childList:true,subtree:true});"
    if root_observer not in source:
        raise RuntimeError("root observer was not found")
    source = source.replace(root_observer, "const obs={disconnect(){}};", 1)

    source = source.replace("p.d<=120?", "p.d<=45?")
    source = source.replace("proj.d<=120?", "proj.d<=45?")

    source, count = re.subn(
        r"function aqRemainingRoutePoints\(route,projection\)\{.*?\}\nfunction aqSyncRemainingRoute",
        _REMAINING_ROUTE + "\nfunction aqSyncRemainingRoute",
        source,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("remaining-route helper was not found exactly once")

    old_focus = "setTimeout(()=>{editor.scrollIntoView?.({block:'center',behavior:'smooth'});$('#aqst-special-name')?.focus()},120)"
    new_focus = "setTimeout(()=>{editor.scrollTop=0;try{$('#aqst-special-name')?.focus({preventScroll:true})}catch{$('#aqst-special-name')?.focus()}},120)"
    if old_focus not in source:
        raise RuntimeError("special-editor focus hook was not found")
    source = source.replace(old_focus, new_focus, 1)
    return source


@app_v3.app.after_request
def aqua_map_qa_stability_assets(response):
    try:
        if response.status_code != 200:
            return response
        if request.path == "/aqua-smart-tour.js":
            response.direct_passthrough = False
            source = _patch_js(response.get_data(as_text=True))
            response.set_data(source)
            response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            marker = "/* Aqua Map iPhone QA stability — single normal-map engine + collision fixes. */"
            if marker not in css:
                css += "\n" + _QA_CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_map_qa_stability_failed: %s", str(exc)[:180])
    return response
