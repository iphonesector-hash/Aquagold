"""Final Map/Navigation-only regression guard for PR #29.

Runs after the older generated-asset layers (via Flask reverse after_request
ordering) and keeps the final iPhone runtime stable: accuracy-aware rerouting,
smooth marker/camera movement, Neshan-compatible fallback, screen Wake Lock,
single maneuver card, raised route styling and native touch long-press.
"""
from __future__ import annotations

import re

from flask import request

import app_v3


_HELPERS = r'''
function aqClamp(v,a,b){return Math.max(a,Math.min(b,v))}
function aqResetLeafletHeading(){const el=$('#aqst-nav-map');if(!el)return;el.classList.remove('aqst-leaflet-heading-up');el.style.removeProperty('--aqst-fallback-rotation')}
function aqApplyLeafletHeading(h){const el=$('#aqst-nav-map');if(!el)return;h=((Number(h)||0)%360+360)%360;el.classList.add('aqst-leaflet-heading-up');el.style.setProperty('--aqst-fallback-rotation',`${-h}deg`)}
function aqSetNavMarker(p){if(!ST.nav.marker||!p)return;try{if(ST.nav.mapKind==='gl')ST.nav.marker.setLngLat([p.lng,p.lat]);else ST.nav.marker.setLatLng([p.lat,p.lng])}catch{}}
function aqAnimateNavMarker(target,immediate=false){if(!target)return;const from=ST.nav.renderedPos||target;ST.nav.renderedPos=target;if(immediate||!window.requestAnimationFrame){aqSetNavMarker(target);return}const token=(ST.nav.markerAnimToken||0)+1;ST.nav.markerAnimToken=token;const started=performance.now(),duration=820;function frame(now){if(token!==ST.nav.markerAnimToken)return;const x=aqClamp((now-started)/duration,0,1),e=1-Math.pow(1-x,3),p={lat:from.lat+(target.lat-from.lat)*e,lng:from.lng+(target.lng-from.lng)*e};aqSetNavMarker(p);if(x<1)requestAnimationFrame(frame)}requestAnimationFrame(frame)}
async function aqAcquireWakeLock(){if(!ST.nav.active||document.visibilityState!=='visible'||!navigator.wakeLock?.request)return false;try{if(ST.nav.wake&&!ST.nav.wake.released)return true;const lock=await navigator.wakeLock.request('screen');ST.nav.wake=lock;lock.addEventListener?.('release',()=>{if(ST.nav.wake===lock)ST.nav.wake=null;if(ST.nav.active&&document.visibilityState==='visible')setTimeout(aqAcquireWakeLock,350)});return true}catch(e){console.warn('Aqua wake lock unavailable',e);return false}}
function aqInstallWakeGuards(){if(ST.nav.wakeGuardsInstalled)return;ST.nav.wakeGuardsInstalled=true;document.addEventListener('visibilitychange',()=>{if(ST.nav.active&&document.visibilityState==='visible')setTimeout(aqAcquireWakeLock,180)});ST.nav.wakeTimer=setInterval(()=>{if(ST.nav.active&&document.visibilityState==='visible'&&(!ST.nav.wake||ST.nav.wake.released))aqAcquireWakeLock()},15000)}
async function aqReleaseWakeLock(){try{await ST.nav.wake?.release?.()}catch{}ST.nav.wake=null}
function aqLoadNavAsset(kind,url,id){return new Promise((resolve,reject)=>{let el=document.getElementById(id);if(el){if(kind==='css'||el.dataset.loaded==='1')return resolve(el);el.addEventListener('load',()=>resolve(el),{once:true});el.addEventListener('error',()=>reject(Error('بارگذاری نقشه نشان انجام نشد')),{once:true});return}el=document.createElement(kind==='css'?'link':'script');el.id=id;if(kind==='css'){el.rel='stylesheet';el.href=url;document.head.appendChild(el);return resolve(el)}el.src=url;el.async=true;el.onload=()=>{el.dataset.loaded='1';resolve(el)};el.onerror=()=>reject(Error('SDK سازگار نشان بارگذاری نشد'));document.head.appendChild(el)})}
async function aqNeshanLeafletSdk(){if(ST.nav.neshanLeafletSdk)return ST.nav.neshanLeafletSdk;const cfg=await api('/api/map/neshan/web-config');if(!cfg?.configured||!cfg.web_key)throw Error('کلید وب نشان تنظیم نشده');const baseL=window.L;await aqLoadNavAsset('css','https://static.neshan.org/sdk/leaflet/1.4.0/leaflet.css','aqst-neshan-leaflet-css');try{await aqLoadNavAsset('js','https://static.neshan.org/sdk/leaflet/1.4.0/leaflet.js','aqst-neshan-leaflet-js');const NL=window.L;if(!NL?.Map)throw Error('SDK سازگار نشان آماده نشد');ST.nav.neshanLeafletSdk={L:NL,key:cfg.web_key};return ST.nav.neshanLeafletSdk}finally{if(baseL)window.L=baseL}}
async function initNeshanLeafletNavMap(route,pos,target){const sdk=await aqNeshanLeafletSdk(),NL=sdk.L;const map=new NL.Map('aqst-nav-map',{key:sdk.key,maptype:'neshan',poi:true,traffic:true,center:[pos.lat,pos.lng],zoom:17,zoomControl:false,attributionControl:false});ST.nav.map=map;ST.nav.mapKind='neshan-leaflet';ST.nav.navL=NL;ST.nav.casing=NL.polyline(route.points,{color:'#3b1068',weight:13,opacity:.92,lineCap:'round',lineJoin:'round',className:'aqst-route-shadow'}).addTo(map);ST.nav.line=NL.polyline(route.points,{color:'#8b2cff',weight:8,opacity:1,lineCap:'round',lineJoin:'round',className:'aqst-route-main'}).addTo(map);const icon=NL.divIcon({className:'aqst-nav-user',html:'<span id="aqst-nav-arrow">▲</span>',iconSize:[54,54],iconAnchor:[27,27]});ST.nav.marker=NL.marker([pos.lat,pos.lng],{icon,zIndexOffset:1500}).addTo(map);ST.nav.destMarker=NL.circleMarker([target.lat,target.lng],{radius:10,color:'#fff',weight:3,fillColor:'#8b2cff',fillOpacity:1}).addTo(map);setTimeout(()=>map.invalidateSize?.(),100)}
'''.strip()

_INIT_NAV = r'''async function initNavMap(route,pos,target){try{ST.nav.map?.remove?.()}catch{}ST.nav.map=null;ST.nav.mapKind=null;ST.nav.marker=null;ST.nav.destMarker=null;ST.nav.navL=null;ST.nav.renderedPos=null;const container=$('#aqst-nav-map');if(container){container.classList.remove('aqst-leaflet-heading-up');container.style.removeProperty('--aqst-fallback-rotation');container.innerHTML=''}try{const sdk=await neshanSdk();await initNeshanGlMap(sdk,route,pos,target);$('#aqst-drive-mode').textContent='نقشه نشان • جهت حرکت • ترافیک'}catch(glError){console.warn('Aqua Neshan GL fallback',glError);try{await initNeshanLeafletNavMap(route,pos,target);$('#aqst-drive-mode').textContent='نقشه نشان • حالت سازگار آیفون'}catch(leafError){console.warn('Aqua Neshan Leaflet fallback',leafError);initLeafletNavMap(route,pos,target);$('#aqst-drive-mode').textContent='حالت پشتیبان'}}}'''

_CAMERA = r'''function updateDriveCamera(pos,coords,near,immediate=false){if(!ST.nav.follow||!ST.nav.map)return;const route=ST.nav.route,proj=typeof aqRouteProjection==='function'?aqRouteProjection(pos,route):null,matched=proj&&proj.d<=130?{lat:proj.lat,lng:proj.lng}:pos,idx=proj?proj.i:Number(near?.i||0),rem=remainingDistance(route,{...(near||{}),i:idx}),rb=routeBearing(route,idx);let h=Number(coords?.heading),speed=Number(coords?.speed);if(!Number.isFinite(h)||h<0||!Number.isFinite(speed)||speed<1.2)h=rb;if(typeof aqSmoothHeading==='function')h=aqSmoothHeading(h);if(ST.nav.mapKind==='gl'){aqResetLeafletHeading();try{ST.nav.map.easeTo({center:[matched.lng,matched.lat],bearing:h,pitch:rem<180?50:57,zoom:rem<220?18.85:18.4,duration:immediate?0:820,essential:true})}catch{}}else try{const zoom=rem<300?18:17;if(typeof ST.nav.map.setBearing==='function'){aqResetLeafletHeading();ST.nav.map.setBearing(h)}else aqApplyLeafletHeading(h);if(immediate)ST.nav.map.setView([matched.lat,matched.lng],zoom,{animate:false});else if(ST.nav.map.panTo){if(ST.nav.map.getZoom?.()!==zoom)ST.nav.map.setZoom?.(zoom,{animate:true});ST.nav.map.panTo([matched.lat,matched.lng],{animate:true,duration:.78,easeLinearity:.22,noMoveStart:true})}else ST.nav.map.setView([matched.lat,matched.lng],zoom,{animate:true});$('#aqst-nav-arrow')?.style.setProperty('transform',typeof ST.nav.map.setBearing==='function'?'rotate(0deg)':`rotate(${h}deg)`)}catch{}}'''

_UPDATE_POS = r'''function updateNavPosition(pos,coords={},initial=false){if(!ST.nav.active)return;const route=ST.nav.route,pts=route?.points||[];if(!pts.length)return;const proj=typeof aqRouteProjection==='function'?aqRouteProjection(pos,route):null,near=proj?{d:proj.d,i:proj.i}:nearestPointInfo(pos,pts),rem=remainingDistance(route,near),total=Math.max(1,Number(route.distance_m||route._total||rem)),seconds=Math.max(0,Math.round(Number(route.duration_s||0)*Math.min(1,rem/total)));ST.nav.lastPos=pos;ST.nav.lastCoords=coords||{};ST.nav.lastNear=near;const info=findNextStep(route,near);ST.nav.stepIndex=info.index;updateTopInstruction(info,rem,seconds);if(!initial)maybeAnnounceManeuver(info);const visible=proj&&proj.d<=130?{lat:proj.lat,lng:proj.lng,_route_i:proj.i,_snap_d:proj.d}:(typeof aqMatchedPosition==='function'?aqMatchedPosition(pos,route):pos);ST.nav.lastMatched=visible;aqAnimateNavMarker(visible,initial);if(typeof aqSyncMainNavMini==='function')aqSyncMainNavMini(visible);ST.nav.prevPos=pos;updateDriveCamera(pos,coords,near,initial);const td=hav([pos.lat,pos.lng],[ST.nav.target.lat,ST.nav.target.lng]);if(td<32){$('#aqst-maneuver-icon').textContent='●';$('#aqst-maneuver-distance').textContent='رسیدی';$('#aqst-turn').textContent='به مقصد رسیدی';$('#aqst-turnsub').textContent=ST.nav.target.name||'';$('#aqst-remain').textContent='۰ متر';$('#aqst-nav-eta').textContent='۰ دقیقه';$('#aqst-arrival').textContent=arrivalClock(0);if(!ST.nav.arrived){ST.nav.arrived=true;ariaSpeak(`به مقصد ${ST.nav.target.name||''} رسیدی`,{replace:true})}return}const rawAcc=Number(coords?.accuracy),acc=Number.isFinite(rawAcc)&&rawAcc>0?Math.min(70,rawAcc):18,offThreshold=Math.max(75,Math.min(170,acc*2.25+35));ST.nav.lastOffDistance=near.d;ST.nav.offThreshold=offThreshold;if(near.d>offThreshold)ST.nav.offCount=(ST.nav.offCount||0)+1;else if(near.d<offThreshold*.62)ST.nav.offCount=0;else ST.nav.offCount=Math.max(0,(ST.nav.offCount||0)-1);if(ST.nav.offCount>=4&&Date.now()-ST.nav.lastReroute>40000){ST.nav.offCount=0;ST.nav.lastReroute=Date.now();reroute(pos)}}'''

_ON_POS = r'''async function onNavPosition(p){if(!ST.nav.active)return;updateNavPosition({lat:p.coords.latitude,lng:p.coords.longitude},{heading:p.coords.heading,speed:p.coords.speed,accuracy:p.coords.accuracy},false)}'''

_LONGPRESS = r'''
;(()=>{
 if(window.__aquaIosLongPress20260909)return;window.__aquaIosLongPress20260909=true;
 function bind(){const el=$('#mainMap'),m=mainMap?.();if(!el||!m||el.dataset.aqIosHold==='1')return;el.dataset.aqIosHold='1';let timer=null,start=null,last=null;const clear=()=>{if(timer){clearTimeout(timer);timer=null}};const pick=()=>{if(!last)return;const r=el.getBoundingClientRect(),x=last.clientX-r.left,y=last.clientY-r.top;try{const ll=m.containerPointToLatLng([x,y]);selectFreeDestination({lat:ll.lat,lng:ll.lng,name:'مقصد انتخابی روی نقشه',address:'',source:'hold'});navigator.vibrate?.(30)}catch{}};el.addEventListener('touchstart',e=>{const t=e.touches?.[0];if(!t)return;start={x:t.clientX,y:t.clientY};last={clientX:t.clientX,clientY:t.clientY};clear();timer=setTimeout(()=>{timer=null;pick()},680)},{passive:true});el.addEventListener('touchmove',e=>{const t=e.touches?.[0];if(!t)return;last={clientX:t.clientX,clientY:t.clientY};if(start&&Math.hypot(t.clientX-start.x,t.clientY-start.y)>14)clear()},{passive:true});['touchend','touchcancel'].forEach(n=>el.addEventListener(n,()=>{clear();start=null},{passive:true}))}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind,{once:true});else bind();new MutationObserver(()=>setTimeout(bind,20)).observe(document.documentElement,{subtree:true,childList:true});setTimeout(bind,400);setTimeout(bind,1200)
})();
'''.strip()

_CSS = r'''
/* Aqua final iPhone navigation guard — 20260909 */
#aqst-nav .aqst-next-strip{display:none!important}
#aqst-nav .aqst-navhead{margin:8px 8px 0!important;min-height:132px!important;padding:15px 14px!important;border-radius:22px!important;background:#08090b!important;box-shadow:0 10px 28px rgba(0,0,0,.30)!important}
#aqst-nav .aqst-turn{font-size:1.38rem!important;line-height:1.4!important;color:#7bdcff!important;font-weight:950!important}
#aqst-nav .aqst-navmap{min-height:0!important;background:#e9ece8!important;overflow:hidden!important}
#aqst-nav #aqst-nav-map.aqst-leaflet-heading-up{transform:rotate(var(--aqst-fallback-rotation,0deg)) scale(1.42)!important;transition:transform .45s linear!important;transform-origin:50% 50%!important;will-change:transform!important}
#aqst-nav .aqst-nav-user,#aqst-nav .aqst-gl-user{filter:drop-shadow(0 9px 7px rgba(41,0,80,.42)) drop-shadow(0 2px 2px rgba(255,255,255,.8))!important;will-change:transform!important;transform:translateZ(0)!important}
#aqst-nav .aqst-nav-user span,#aqst-nav .aqst-gl-user span{color:#8b2cff!important;font-size:2.55rem!important;text-shadow:-3px -3px 0 #fff,3px -3px 0 #fff,-3px 3px 0 #fff,3px 3px 0 #fff,0 5px 0 #4b0d91,0 9px 13px rgba(48,0,94,.58)!important;will-change:transform!important}
#aqst-nav .leaflet-overlay-pane svg path.aqst-route-shadow{filter:drop-shadow(0 5px 5px rgba(48,0,83,.42))!important}
#aqst-nav .leaflet-overlay-pane svg path.aqst-route-main{filter:drop-shadow(0 3px 3px rgba(89,20,157,.52))!important}
#aqst-nav .leaflet-marker-icon{will-change:transform!important;backface-visibility:hidden!important;-webkit-backface-visibility:hidden!important}
#aqst-free-card:not([hidden]){z-index:2147481200!important}
@media(max-width:700px){#aqst-free-card:not([hidden]){position:fixed!important;left:12px!important;right:12px!important;bottom:calc(94px + env(safe-area-inset-bottom))!important;margin:0!important;padding:11px!important;border-radius:17px!important;background:rgba(7,18,29,.94)!important;color:#fff!important;box-shadow:0 16px 44px rgba(0,0,0,.38)!important;backdrop-filter:blur(18px)!important;-webkit-backdrop-filter:blur(18px)!important}#aqst-free-card .aqst-free-card-actions{display:grid!important;grid-template-columns:1fr auto!important;gap:7px!important;margin-top:8px!important}#aqst-free-card .aqst-free-start{background:linear-gradient(135deg,#16c8a2,#00a977)!important;color:#021b14!important;font-weight:950!important}#aqst-free-card .aqst-free-clear{background:#15283c!important;color:#fff!important}}
'''.strip()


def _replace_fn(source: str, name: str, next_name: str, replacement: str) -> str:
    pattern = rf"(?:async\s+)?function\s+{re.escape(name)}\(.*?(?=\n(?:async\s+)?function\s+{re.escape(next_name)}\()"
    return re.sub(pattern, replacement + "\n", source, count=1, flags=re.S)


@app_v3.app.after_request
def aqua_navigation_final_guard_assets(response):
    try:
        if response.status_code != 200:
            return response
        if request.path == "/aqua-smart-tour.js":
            response.direct_passthrough = False
            source = response.get_data(as_text=True)
            source = source.replace("async async function initNavMap", "async function initNavMap")
            if "function aqAnimateNavMarker(" not in source:
                anchor = "async function startNavigation("
                idx = source.find(anchor)
                if idx >= 0:
                    source = source[:idx] + _HELPERS + "\n" + source[idx:]
            source = _replace_fn(source, "initNavMap", "initNeshanGlMap", _INIT_NAV)
            source = _replace_fn(source, "updateDriveCamera", "showRouteOverview", _CAMERA)
            source = _replace_fn(source, "updateNavPosition", "onNavPosition", _UPDATE_POS)
            source = _replace_fn(source, "onNavPosition", "reroute", _ON_POS)
            source = source.replace("try{ST.nav.wake=await navigator.wakeLock?.request?.('screen')}catch{}", "aqInstallWakeGuards();await aqAcquireWakeLock()")
            source = source.replace("try{await ST.nav.wake?.release?.()}catch{}ST.nav.wake=null;", "await aqReleaseWakeLock();")
            source = source.replace("color:'#eefcff',weight:11", "color:'#3b1068',weight:13,className:'aqst-route-shadow'")
            source = source.replace("color:'#13bdf4',weight:7", "color:'#8b2cff',weight:8,className:'aqst-route-main'")
            source = source.replace("'line-color':'#f4fbff','line-width':12", "'line-color':'#3b1068','line-width':13,'line-blur':2")
            source = source.replace("'line-color':'#16c7f4','line-width':7", "'line-color':'#8b2cff','line-width':8,'line-blur':.15")
            if "__aquaIosLongPress20260909" not in source:
                source += "\n" + _LONGPRESS + "\n"
            response.set_data(source)
            response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            if "Aqua final iPhone navigation guard — 20260909" not in css:
                css += "\n" + _CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_final_guard_failed: %s", str(exc)[:180])
    return response
