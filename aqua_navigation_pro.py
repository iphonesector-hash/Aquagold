"""Branch-scoped professional navigation layer for Aqua Smart Tour.

Keeps the existing map/tour architecture intact while upgrading the served
navigation runtime with real Neshan maneuvers and Aria TTS. No production-only
state and no schema changes.
"""
from pathlib import Path
import re

from flask import request

import app_v3
import aqua_neshan_preview as neshan


def _normalize_direction_pro(payload: dict):
    routes = payload.get("routes") or []
    if not routes:
        return {"points": [], "steps": [], "legs": [], "distance_m": 0, "duration_s": 0, "summary": ""}
    route = routes[0]
    overview = route.get("overview_polyline") or {}
    points = neshan.decode_polyline(overview.get("points") if isinstance(overview, dict) else overview)
    legs_out, all_steps = [], []
    total_distance = total_duration = 0
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
        leg_points, steps_out = [], []
        for step in leg.get("steps") or []:
            raw_start = step.get("start_location") or []
            start = [raw_start[1], raw_start[0]] if len(raw_start) >= 2 else None
            step_points = neshan.decode_polyline(step.get("polyline"))
            if step_points:
                leg_points.extend(step_points[1:] if leg_points and leg_points[-1] == step_points[0] else step_points)
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
        legs_out.append({
            "summary": summary,
            "distance_m": distance,
            "distance_text": distance_obj.get("text") or "",
            "duration_s": duration,
            "duration_text": duration_obj.get("text") or "",
            "points": leg_points,
            "steps": steps_out,
        })
    return {
        "points": points,
        "steps": all_steps,
        "legs": legs_out,
        "distance_m": total_distance,
        "duration_s": total_duration,
        "summary": " - ".join(dict.fromkeys(summaries)),
    }


# directions() resolves this module global at call time, so replacing it here
# preserves the existing endpoints while retaining maneuver metadata.
neshan.normalize_direction = _normalize_direction_pro

_NAV_FRAGMENT = Path(__file__).with_name("aqua-navigation-pro-fragment.js")
_NAV_CSS = Path(__file__).with_name("aqua-navigation-pro.css")


_PHASE2_LONG_PRESS = r'''function bindMainMapLongPress(){
 const el=$('#mainMap'),m=mainMap();if(!el||!m||el.dataset.aqLongPress==='2')return;el.dataset.aqLongPress='2';
 let timer=null,start=null,lastPoint=null,lastFire=0;
 const clear=()=>{if(timer){clearTimeout(timer);timer=null}};
 const reset=()=>{clear();start=null;lastPoint=null};
 const begin=(x,y)=>{reset();start={x,y};lastPoint={x,y};timer=setTimeout(()=>{
  timer=null;if(!lastPoint||Date.now()-lastFire<900)return;lastFire=Date.now();
  const rect=el.getBoundingClientRect(),px=lastPoint.x-rect.left,py=lastPoint.y-rect.top;
  try{const ll=m.containerPointToLatLng([px,py]);selectFreeDestination({lat:ll.lat,lng:ll.lng,name:'مقصد انتخابی روی نقشه',address:'',source:'hold'});navigator.vibrate?.(25)}catch{}
 },720)};
 const move=(x,y)=>{if(!start)return;lastPoint={x,y};if(Math.hypot(x-start.x,y-start.y)>12)reset()};
 const end=()=>reset();
 // Mouse/pen keep the Pointer Events path. Touch deliberately uses the explicit
 // Safari path below so Leaflet pointercancel cannot kill the iPhone hold timer.
 el.addEventListener('pointerdown',e=>{if(e.pointerType==='touch'||(e.button!=null&&e.button!==0))return;begin(e.clientX,e.clientY)},{passive:true,capture:true});
 el.addEventListener('pointermove',e=>{if(e.pointerType==='touch')return;move(e.clientX,e.clientY)},{passive:true,capture:true});
 ['pointerup','pointercancel','pointerleave'].forEach(n=>el.addEventListener(n,e=>{if(e.pointerType==='touch')return;end()},{passive:true,capture:true}));
 el.addEventListener('touchstart',e=>{if(e.touches.length!==1)return;const t=e.touches[0];begin(t.clientX,t.clientY)},{passive:true,capture:true});
 el.addEventListener('touchmove',e=>{if(e.touches.length!==1){reset();return}const t=e.touches[0];move(t.clientX,t.clientY)},{passive:true,capture:true});
 ['touchend','touchcancel'].forEach(n=>el.addEventListener(n,end,{passive:true,capture:true}));
 el.addEventListener('contextmenu',e=>{if(Date.now()-lastFire<1200)e.preventDefault()},{capture:true});
}'''

_PHASE2_CSS = r'''
/* Aqua Map Phase 2 — iPhone long-press + compact selected customer correction. */
@media(max-width:700px){
 html body section[x-show*="page==='map'"]>div:first-child>.no-print{
  width:calc(100% + 8px)!important;
  margin-inline:-4px!important;
  grid-template-columns:repeat(3,minmax(0,1fr))!important;
  gap:3px!important;
 }
 html body section[x-show*="page==='map'"]>div:first-child>.no-print>button:nth-child(-n+3),
 html body section[x-show*="page==='map'"]>div:first-child>.no-print>.aqst-route-pair>button{
  width:100%!important;
  min-width:0!important;
  height:40px!important;
  min-height:40px!important;
  padding:0 5px!important;
  font-size:clamp(.62rem,2.7vw,.72rem)!important;
  gap:3px!important;
  border-radius:12px!important;
 }
 html body section[x-show*="page==='map'"]>div:first-child>.no-print svg{
  width:15px!important;height:15px!important;flex:0 0 15px!important;
 }
 html body #aq-smart-tour .aqst-selected{
  display:grid!important;
  grid-template-columns:minmax(0,1fr) auto!important;
  flex-direction:row!important;
  flex-wrap:nowrap!important;
  align-items:center!important;
  justify-content:space-between!important;
  width:100%!important;
  height:auto!important;
  min-height:0!important;
  max-height:72px!important;
  margin-top:5px!important;
  padding:7px 8px!important;
  gap:6px!important;
  overflow:hidden!important;
 }
 html body #aq-smart-tour .aqst-selected-copy{
  flex:0 1 auto!important;
  min-width:0!important;
  min-height:0!important;
  max-width:100%!important;
 }
 html body #aq-smart-tour .aqst-selected-copy b,
 html body #aq-smart-tour .aqst-selected-copy small{
  white-space:nowrap!important;
  overflow:hidden!important;
  text-overflow:ellipsis!important;
 }
 html body #aq-smart-tour .aqst-selected>div:last-child{
  display:flex!important;
  flex:0 0 auto!important;
  gap:5px!important;
  align-items:center!important;
 }
 html body #aq-smart-tour .aqst-selected .aqst-btn{
  min-width:auto!important;
  min-height:34px!important;
  height:34px!important;
  padding:0 9px!important;
  font-size:.68rem!important;
 }
 html body section[x-show*="page==='map'"] #mainMap{
  -webkit-touch-callout:none!important;
  -webkit-user-select:none!important;
  user-select:none!important;
 }
}
'''.strip()


def _phase2_fragment(source: str) -> str:
    pattern = r"function bindMainMapLongPress\(\)\{.*?\n\}\n\n(?=function renderFreeCard)"
    patched, count = re.subn(
        pattern,
        _PHASE2_LONG_PRESS + "\n\n",
        source,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("Phase 2 long-press function was not found exactly once")
    return patched


@app_v3.app.after_request
def aqua_navigation_pro_assets(response):
    try:
        if request.path == "/aqua-smart-tour.js" and response.status_code == 200:
            response.direct_passthrough = False
            source = response.get_data(as_text=True)
            start = source.find("function createNav(){")
            end = source.find("\n\nfunction enhance()", start)
            if start >= 0 and end > start:
                replacement = _phase2_fragment(_NAV_FRAGMENT.read_text(encoding="utf-8").strip())
                source = source[:start] + replacement + source[end:]
                response.set_data(source)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css" and response.status_code == 200:
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            marker = "/* aqua-navigation-pro */"
            if marker not in css:
                css += "\n" + marker + "\n" + _NAV_CSS.read_text(encoding="utf-8") + "\n" + _PHASE2_CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_pro_asset_failed: %s", str(exc)[:180])
    return response
