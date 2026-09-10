"""Ensure polish controls mount when dynamic Map/navigation UI is created."""
import re

from flask import request

import app_v3


_PHASE3_REROUTE_BLOCK = r'''function routeCorridorDistance(pos,points,nearIndex=0){
 if(!points?.length)return Infinity;if(points.length===1)return hav([pos.lat,pos.lng],points[0]);
 const latScale=110540,lngScale=111320*Math.cos(Number(pos.lat)*Math.PI/180);let best=Infinity;
 const idx=Math.max(0,Math.min(Number(nearIndex||0),points.length-1)),lo=Math.max(0,idx-10),hi=Math.min(points.length-2,idx+10);
 for(let i=lo;i<=hi;i++){const a=points[i],b=points[i+1];if(!a||!b)continue;const ax=(Number(a[1])-pos.lng)*lngScale,ay=(Number(a[0])-pos.lat)*latScale,bx=(Number(b[1])-pos.lng)*lngScale,by=(Number(b[0])-pos.lat)*latScale,dx=bx-ax,dy=by-ay,len2=dx*dx+dy*dy;let t=len2>0?-(ax*dx+ay*dy)/len2:0;t=Math.max(0,Math.min(1,t));best=Math.min(best,Math.hypot(ax+t*dx,ay+t*dy))}
 return Number.isFinite(best)?best:hav([pos.lat,pos.lng],points[idx]);
}
function clearOffRouteCandidate(guard){if(!guard)return;guard.samples=0;guard.since=0;guard.anchor=null;guard.peak=0;ST.nav.offCount=0}
function resetOffRouteGuard(route=ST.nav.route,resetCooldown=false){ST.nav.offTrack={routeRef:route,samples:0,since:0,anchor:null,lastFix:null,peak:0};ST.nav.offCount=0;if(resetCooldown)ST.nav.lastReroute=0}
function rerouteThreshold(coords={}){const raw=coords?.accuracy,accuracy=Number(raw),hasAccuracy=raw!==null&&raw!==undefined&&Number.isFinite(accuracy)&&accuracy>0;return Math.max(70,Math.min(135,hasAccuracy?accuracy*1.5+35:85))}
function evaluateReroute(pos,coords,near,initial=false){
 if(initial||!ST.nav.offTrack||ST.nav.offTrack.routeRef!==ST.nav.route){resetOffRouteGuard(ST.nav.route,initial);return false}
 const guard=ST.nav.offTrack,now=Date.now(),points=ST.nav.route?.points||[],distance=routeCorridorDistance(pos,points,near?.i||0),threshold=rerouteThreshold(coords),accuracyRaw=coords?.accuracy,accuracy=Number(accuracyRaw),hasAccuracy=accuracyRaw!==null&&accuracyRaw!==undefined&&Number.isFinite(accuracy)&&accuracy>0;
 if(!Number.isFinite(distance)||(hasAccuracy&&accuracy>65)){clearOffRouteCandidate(guard);guard.lastFix={lat:pos.lat,lng:pos.lng,at:now};return false}
 if(distance<=threshold){clearOffRouteCandidate(guard);guard.lastFix={lat:pos.lat,lng:pos.lng,at:now};return false}
 const prev=guard.lastFix;guard.lastFix={lat:pos.lat,lng:pos.lng,at:now};const speedRaw=coords?.speed,speed=Number(speedRaw),hasSpeed=speedRaw!==null&&speedRaw!==undefined&&Number.isFinite(speed)&&speed>=0,dt=prev?Math.max(.25,(now-prev.at)/1000):0,moved=prev?hav([prev.lat,prev.lng],[pos.lat,pos.lng]):0,moving=(hasSpeed&&speed>=1.2)||(!!prev&&moved>=Math.max(6,Math.min(20,dt*1.2)));
 if(!moving){clearOffRouteCandidate(guard);return false}
 if(!guard.since){guard.since=now;guard.samples=1;guard.anchor={lat:pos.lat,lng:pos.lng};guard.peak=distance;ST.nav.offCount=1;return false}
 guard.samples+=1;guard.peak=Math.max(Number(guard.peak||0),distance);ST.nav.offCount=guard.samples;
 const sustained=guard.samples>=4&&now-guard.since>=6500,cooldown=now-Number(ST.nav.lastReroute||0)>=45000;
 if(!sustained||!cooldown||ST.nav.rerouting)return false;
 clearOffRouteCandidate(guard);ST.nav.lastReroute=now;reroute(pos);return true;
}
function updateNavPosition(pos,coords={},initial=false){if(!ST.nav.active)return;const route=ST.nav.route,pts=route?.points||[];if(!pts.length)return;const near=nearestPointInfo(pos,pts),projection=typeof aqRouteProjection==='function'?aqRouteProjection(pos,route):{d:near.d,i:near.i,lat:pts[near.i][0],lng:pts[near.i][1]},visible=typeof aqMatchedPosition==='function'?aqMatchedPosition(pos,route):pos,rem=remainingDistance(route,near),total=Math.max(1,Number(route.distance_m||route._total||rem)),seconds=Math.max(0,Math.round(Number(route.duration_s||0)*Math.min(1,rem/total)));ST.nav.lastPos=pos;ST.nav.lastMatched=visible;ST.nav.lastCoords=coords||{};ST.nav.lastNear=near;const info=findNextStep(route,near);ST.nav.stepIndex=info.index;updateTopInstruction(info,rem,seconds);if(!initial)maybeAnnounceManeuver(info);if(ST.nav.mapKind==='gl')ST.nav.marker?.setLngLat?.([visible.lng,visible.lat]);else ST.nav.marker?.setLatLng?.([visible.lat,visible.lng]);if(typeof aqSyncRemainingRoute==='function')aqSyncRemainingRoute(route,projection);if(typeof aqSyncMainNavMini==='function')aqSyncMainNavMini(visible);ST.nav.prevPos=pos;updateDriveCamera(pos,coords,near,initial);const td=hav([pos.lat,pos.lng],[ST.nav.target.lat,ST.nav.target.lng]);if(td<32){$('#aqst-maneuver-icon').textContent='●';$('#aqst-maneuver-distance').textContent='رسیدی';$('#aqst-turn').textContent='به مقصد رسیدی';$('#aqst-turnsub').textContent=ST.nav.target.name||'';$('#aqst-remain').textContent='۰ متر';$('#aqst-nav-eta').textContent='۰ دقیقه';$('#aqst-arrival').textContent=arrivalClock(0);clearOffRouteCandidate(ST.nav.offTrack);if(!ST.nav.arrived){ST.nav.arrived=true;ariaSpeak(`به مقصد ${ST.nav.target.name||''} رسیدی`,{replace:true})}return}evaluateReroute(pos,coords,near,initial)}
async function onNavPosition(p){if(!ST.nav.active)return;updateNavPosition({lat:p.coords.latitude,lng:p.coords.longitude},{heading:p.coords.heading,speed:p.coords.speed,accuracy:p.coords.accuracy,timestamp:p.timestamp},false)}
async function reroute(pos){if(!ST.nav.active||!ST.nav.target||ST.nav.rerouting)return;ST.nav.rerouting=true;const target=ST.nav.target;try{const route=await fetchRoute(pos,target);if(!ST.nav.active||ST.nav.target!==target||!route.points?.length)return;ST.nav.route=route;prepareRouteModel(route);resetOffRouteGuard(route,false);updateRouteLayer(route);ST.nav.lastPos=pos;updateNavPosition(pos,ST.nav.lastCoords||{},true);ariaSpeak('از مسیر خارج شدی. مسیر دوباره محاسبه شد.',{replace:true})}catch{}finally{ST.nav.rerouting=false}}
'''.strip()


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

        # Phase 3: reroute only after a sustained, good-quality off-route signal.
        # Use distance to the route segment/corridor, not only to sparse polyline
        # vertices; the old vertex distance could say 100m+ while driving exactly
        # between two route points and announce a false reroute.
        phase3_pattern = (
            r"function updateNavPosition\(pos,coords=\{\},initial=false\)\{.*?"
            r"\nasync function reroute\(pos\)\{.*?\}\n(?=async function stopNavigation)"
        )
        source, phase3_count = re.subn(
            phase3_pattern,
            _PHASE3_REROUTE_BLOCK + "\n",
            source,
            count=1,
            flags=re.S,
        )
        if phase3_count != 1:
            raise RuntimeError("Phase 3 reroute block was not found exactly once")

        response.set_data(source)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_controls_fix_failed: %s", str(exc)[:160])
    return response
