"""Final map-only navigation motion/reliability patch for the iPhone Preview.

This layer intentionally runs after the older navigation injectors and only
rewrites /aqua-smart-tour.js and /aqua-smart-tour.css. It fixes the generated
runtime syntax edge case, smooths GPS/camera motion, keeps a single 3D-styled
route/vehicle marker, makes false off-route reroutes accuracy-aware, and keeps
the screen awake while navigation is active.
"""
from __future__ import annotations

import re

from flask import request

import app_v3


_HELPERS = r'''
function aqClamp(v,a,b){return Math.max(a,Math.min(b,v))}
function aqSmoothPoint(from,to,t){return{lat:from.lat+(to.lat-from.lat)*t,lng:from.lng+(to.lng-from.lng)*t}}
function aqSetNavMarker(p){if(!ST.nav.marker||!p)return;try{if(ST.nav.mapKind==='gl')ST.nav.marker.setLngLat([p.lng,p.lat]);else ST.nav.marker.setLatLng([p.lat,p.lng])}catch{}}
function aqAnimateNavMarker(target,immediate=false){if(!target)return;const from=ST.nav.renderedPos||target;ST.nav.renderedPos=target;if(immediate||!window.requestAnimationFrame){aqSetNavMarker(target);return}const token=(ST.nav.markerAnimToken||0)+1;ST.nav.markerAnimToken=token;const started=performance.now(),duration=820;function frame(now){if(token!==ST.nav.markerAnimToken)return;const x=aqClamp((now-started)/duration,0,1),e=1-Math.pow(1-x,3),p=aqSmoothPoint(from,target,e);aqSetNavMarker(p);if(x<1)requestAnimationFrame(frame)}requestAnimationFrame(frame)}
async function aqAcquireWakeLock(){if(!ST.nav.active||document.visibilityState!=='visible'||!navigator.wakeLock?.request)return false;try{if(ST.nav.wake&&!ST.nav.wake.released)return true;const lock=await navigator.wakeLock.request('screen');ST.nav.wake=lock;lock.addEventListener?.('release',()=>{if(ST.nav.wake===lock)ST.nav.wake=null;if(ST.nav.active&&document.visibilityState==='visible')setTimeout(aqAcquireWakeLock,350)});return true}catch(e){console.warn('Aqua wake lock unavailable',e);return false}}
function aqInstallWakeGuards(){if(ST.nav.wakeGuardsInstalled)return;ST.nav.wakeGuardsInstalled=true;document.addEventListener('visibilitychange',()=>{if(ST.nav.active&&document.visibilityState==='visible')setTimeout(aqAcquireWakeLock,180)});ST.nav.wakeTimer=setInterval(()=>{if(ST.nav.active&&document.visibilityState==='visible'&&(!ST.nav.wake||ST.nav.wake.released))aqAcquireWakeLock()},15000)}
async function aqReleaseWakeLock(){try{await ST.nav.wake?.release?.()}catch{}ST.nav.wake=null}
'''.strip()

_UPDATE_POS = r'''function updateNavPosition(pos,coords={},initial=false){if(!ST.nav.active)return;const route=ST.nav.route,pts=route?.points||[];if(!pts.length)return;const proj=typeof aqRouteProjection==='function'?aqRouteProjection(pos,route):null,near=proj?{d:proj.d,i:proj.i}:nearestPointInfo(pos,pts),rem=remainingDistance(route,near),total=Math.max(1,Number(route.distance_m||route._total||rem)),seconds=Math.max(0,Math.round(Number(route.duration_s||0)*Math.min(1,rem/total)));ST.nav.lastPos=pos;ST.nav.lastCoords=coords||{};ST.nav.lastNear=near;const info=findNextStep(route,near);ST.nav.stepIndex=info.index;updateTopInstruction(info,rem,seconds);if(!initial)maybeAnnounceManeuver(info);const visible=proj&&proj.d<=130?{lat:proj.lat,lng:proj.lng,_route_i:proj.i,_snap_d:proj.d}:(typeof aqMatchedPosition==='function'?aqMatchedPosition(pos,route):pos);ST.nav.lastMatched=visible;aqAnimateNavMarker(visible,initial);if(typeof aqSyncMainNavMini==='function')aqSyncMainNavMini(visible);ST.nav.prevPos=pos;updateDriveCamera(pos,coords,near,initial);const td=hav([pos.lat,pos.lng],[ST.nav.target.lat,ST.nav.target.lng]);if(td<32){$('#aqst-maneuver-icon').textContent='●';$('#aqst-maneuver-distance').textContent='رسیدی';$('#aqst-turn').textContent='به مقصد رسیدی';$('#aqst-turnsub').textContent=ST.nav.target.name||'';$('#aqst-remain').textContent='۰ متر';$('#aqst-nav-eta').textContent='۰ دقیقه';$('#aqst-arrival').textContent=arrivalClock(0);if(!ST.nav.arrived){ST.nav.arrived=true;ariaSpeak(`به مقصد ${ST.nav.target.name||''} رسیدی`,{replace:true})}return}const rawAcc=Number(coords?.accuracy),acc=Number.isFinite(rawAcc)&&rawAcc>0?Math.min(70,rawAcc):18,offThreshold=Math.max(75,Math.min(170,acc*2.25+35));ST.nav.lastOffDistance=near.d;ST.nav.offThreshold=offThreshold;if(near.d>offThreshold)ST.nav.offCount=(ST.nav.offCount||0)+1;else if(near.d<offThreshold*.62)ST.nav.offCount=0;else ST.nav.offCount=Math.max(0,(ST.nav.offCount||0)-1);if(ST.nav.offCount>=4&&Date.now()-ST.nav.lastReroute>40000){ST.nav.offCount=0;ST.nav.lastReroute=Date.now();reroute(pos)}}'''

_ON_POS = r'''async function onNavPosition(p){if(!ST.nav.active)return;updateNavPosition({lat:p.coords.latitude,lng:p.coords.longitude},{heading:p.coords.heading,speed:p.coords.speed,accuracy:p.coords.accuracy},false)}'''

_CAMERA = r'''function updateDriveCamera(pos,coords,near,immediate=false){if(!ST.nav.follow||!ST.nav.map)return;const route=ST.nav.route,proj=typeof aqRouteProjection==='function'?aqRouteProjection(pos,route):null,matched=proj&&proj.d<=130?{lat:proj.lat,lng:proj.lng}:pos,idx=proj?proj.i:Number(near?.i||0),rem=remainingDistance(route,{...(near||{}),i:idx}),rb=routeBearing(route,idx);let h=Number(coords?.heading),speed=Number(coords?.speed);if(!Number.isFinite(h)||h<0||!Number.isFinite(speed)||speed<1.2)h=rb;if(typeof aqSmoothHeading==='function')h=aqSmoothHeading(h);if(ST.nav.mapKind==='gl'){aqResetLeafletHeading?.();try{ST.nav.map.easeTo({center:[matched.lng,matched.lat],bearing:h,pitch:rem<180?50:57,zoom:rem<220?18.85:18.4,duration:immediate?0:820,essential:true})}catch{}}else try{const zoom=rem<300?18:17;if(typeof ST.nav.map.setBearing==='function'){aqResetLeafletHeading?.();ST.nav.map.setBearing(h)}else aqApplyLeafletHeading?.(h);if(immediate)ST.nav.map.setView([matched.lat,matched.lng],zoom,{animate:false});else if(ST.nav.map.panTo){if(ST.nav.map.getZoom?.()!==zoom)ST.nav.map.setZoom?.(zoom,{animate:true});ST.nav.map.panTo([matched.lat,matched.lng],{animate:true,duration:.78,easeLinearity:.22,noMoveStart:true})}else ST.nav.map.setView([matched.lat,matched.lng],zoom,{animate:true});$('#aqst-nav-arrow')?.style.setProperty('transform',typeof ST.nav.map.setBearing==='function'?'rotate(0deg)':`rotate(${h}deg)`)}catch{}}'''

_START_WAKE_OLD = "try{ST.nav.wake=await navigator.wakeLock?.request?.('screen')}catch{}"
_START_WAKE_NEW = "aqInstallWakeGuards();await aqAcquireWakeLock()"
_STOP_WAKE_OLD = "try{await ST.nav.wake?.release?.()}catch{}ST.nav.wake=null;"
_STOP_WAKE_NEW = "await aqReleaseWakeLock();"


_CSS = r'''
/* Aqua navigation smooth motion + raised route/marker — 20260908 */
#aqst-nav .aqst-next-strip{display:none!important}
#aqst-nav .aqst-navmap{min-height:0!important;background:#e9ece8!important}
#aqst-nav .aqst-nav-user,#aqst-nav .aqst-gl-user{filter:drop-shadow(0 9px 7px rgba(41,0,80,.42)) drop-shadow(0 2px 2px rgba(255,255,255,.75))!important;will-change:transform!important}
#aqst-nav .aqst-nav-user span,#aqst-nav .aqst-gl-user span{color:#8b2cff!important;font-size:2.55rem!important;text-shadow:-3px -3px 0 #fff,3px -3px 0 #fff,-3px 3px 0 #fff,3px 3px 0 #fff,0 5px 0 #4b0d91,0 9px 13px rgba(48,0,94,.58)!important;transition:transform .55s linear!important}
#aqst-nav .leaflet-overlay-pane svg path.aqst-route-shadow{filter:drop-shadow(0 5px 5px rgba(48,0,83,.42))!important}
#aqst-nav .leaflet-overlay-pane svg path.aqst-route-main{filter:drop-shadow(0 3px 3px rgba(89,20,157,.52))!important}
#aqst-nav .leaflet-marker-pane img,#aqst-nav .leaflet-marker-pane .leaflet-marker-icon{transition:transform .52s linear!important;will-change:transform!important}
#aqst-nav .mapboxgl-marker{transition:none!important;will-change:transform!important}
#aqst-nav .aqst-navfoot{min-height:78px!important;padding-bottom:max(12px,env(safe-area-inset-bottom))!important}
#aqst-nav .aqst-stop{position:fixed!important;z-index:2147481950!important;left:12px!important;top:calc(env(safe-area-inset-top) + 16px)!important;width:44px!important;height:44px!important;min-width:44px!important;padding:0!important;margin:0!important;border-radius:50%!important;font-size:0!important;background:#d92c43!important;box-shadow:0 7px 18px rgba(160,0,25,.35)!important}
#aqst-nav .aqst-stop::after{content:'×';font-size:1.7rem;line-height:1;color:#fff;font-weight:700}
@media(max-width:700px){#aqst-nav .aqst-navfoot{min-height:72px!important}#aqst-nav .aqst-stop{left:10px!important;top:calc(env(safe-area-inset-top) + 12px)!important;width:42px!important;height:42px!important;min-width:42px!important}}
'''.strip()


def _replace_fn(source: str, name: str, next_name: str, replacement: str) -> str:
    pattern = rf"(?:async\s+)?function\s+{re.escape(name)}\(.*?(?=\n(?:async\s+)?function\s+{re.escape(next_name)}\()"
    return re.sub(pattern, replacement + "\n", source, count=1, flags=re.S)


@app_v3.app.after_request
def aqua_navigation_motion_wakelock_assets(response):
    try:
        if response.status_code != 200:
            return response
        if request.path == "/aqua-smart-tour.js":
            response.direct_passthrough = False
            source = response.get_data(as_text=True)
            source = source.replace("async async function initNavMap", "async function initNavMap")
            if "function aqAcquireWakeLock()" not in source:
                anchor = "function startNavigation("
                idx = source.find(anchor)
                if idx >= 0:
                    source = source[:idx] + _HELPERS + "\n" + source[idx:]
            source = _replace_fn(source, "updateDriveCamera", "showRouteOverview", _CAMERA)
            source = _replace_fn(source, "updateNavPosition", "onNavPosition", _UPDATE_POS)
            source = _replace_fn(source, "onNavPosition", "reroute", _ON_POS)
            source = source.replace(_START_WAKE_OLD, _START_WAKE_NEW)
            source = source.replace(_STOP_WAKE_OLD, _STOP_WAKE_NEW)
            # Give Leaflet-based route layers explicit classes for raised/glow styling.
            source = source.replace("weight:12,opacity:.92,lineCap:'round',lineJoin:'round'", "weight:12,opacity:.92,lineCap:'round',lineJoin:'round',className:'aqst-route-shadow'")
            source = source.replace("weight:12,opacity:.9,lineCap:'round',lineJoin:'round'", "weight:12,opacity:.9,lineCap:'round',lineJoin:'round',className:'aqst-route-shadow'")
            source = source.replace("weight:8,opacity:1,lineCap:'round',lineJoin:'round'", "weight:8,opacity:1,lineCap:'round',lineJoin:'round',className:'aqst-route-main'")
            # Add a soft depth halo to GL route layers without creating a second visible route.
            source = source.replace("'line-width':12,'line-opacity':.92", "'line-width':13,'line-opacity':.92,'line-blur':2.2")
            source = source.replace("'line-width':7,'line-opacity':1", "'line-width':8,'line-opacity':1,'line-blur':.15")
            response.set_data(source)
            response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            marker = "Aqua navigation smooth motion + raised route/marker — 20260908"
            if marker not in css:
                css += "\n" + _CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_motion_wakelock_failed: %s", str(exc)[:180])
    return response
