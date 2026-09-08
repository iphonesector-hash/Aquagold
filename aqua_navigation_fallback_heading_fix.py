"""Map-only iPhone navigation reliability and Neshan-style fallback.

Scopes all changes to the served Smart Tour navigation assets:
- use route-segment projection + GPS accuracy hysteresis before rerouting;
- prefer Neshan's official Leaflet web map as the iPhone fallback before OSM;
- keep heading-up follow mode where the renderer supports it;
- collapse the duplicate next-maneuver strip into one top instruction card;
- make the navigation screen closer to the native Neshan proportions.

No Finance, Aria chat/voice, Bale, Push, database or Production state is changed.
"""
from __future__ import annotations

import re

from flask import request

import app_v3


_HELPERS = r'''
function aqResetLeafletHeading(){const el=$('#aqst-nav-map');if(!el)return;el.classList.remove('aqst-leaflet-heading-up');el.style.removeProperty('--aqst-fallback-rotation')}
function aqApplyLeafletHeading(h){const el=$('#aqst-nav-map');if(!el)return;h=((Number(h)||0)%360+360)%360;el.classList.add('aqst-leaflet-heading-up');el.style.setProperty('--aqst-fallback-rotation',`${-h}deg`)}
'''.strip()

_NESHAN_LEAFLET = r'''
function aqLoadNavAsset(kind,url,id){return new Promise((resolve,reject)=>{let el=document.getElementById(id);if(el){if(kind==='css'||el.dataset.loaded==='1')return resolve(el);el.addEventListener('load',()=>resolve(el),{once:true});el.addEventListener('error',()=>reject(Error('بارگذاری نقشه نشان انجام نشد')),{once:true});return}el=document.createElement(kind==='css'?'link':'script');el.id=id;if(kind==='css'){el.rel='stylesheet';el.href=url;document.head.appendChild(el);return resolve(el)}el.src=url;el.async=true;el.onload=()=>{el.dataset.loaded='1';resolve(el)};el.onerror=()=>reject(Error('SDK سازگار نشان بارگذاری نشد'));document.head.appendChild(el)})}
async function aqNeshanLeafletSdk(){if(ST.nav.neshanLeafletSdk)return ST.nav.neshanLeafletSdk;const cfg=await api('/api/map/neshan/web-config');if(!cfg?.configured||!cfg.web_key)throw Error('کلید وب نشان تنظیم نشده');const baseL=window.L;await aqLoadNavAsset('css','https://static.neshan.org/sdk/leaflet/1.4.0/leaflet.css','aqst-neshan-leaflet-css');try{await aqLoadNavAsset('js','https://static.neshan.org/sdk/leaflet/1.4.0/leaflet.js','aqst-neshan-leaflet-js');const NL=window.L;if(!NL?.Map)throw Error('SDK سازگار نشان آماده نشد');ST.nav.neshanLeafletSdk={L:NL,key:cfg.web_key};return ST.nav.neshanLeafletSdk}finally{if(baseL)window.L=baseL}}
async function initNeshanLeafletNavMap(route,pos,target){const sdk=await aqNeshanLeafletSdk(),NL=sdk.L;const map=new NL.Map('aqst-nav-map',{key:sdk.key,maptype:'neshan',poi:true,traffic:true,center:[pos.lat,pos.lng],zoom:17,zoomControl:false,attributionControl:false});ST.nav.map=map;ST.nav.mapKind='neshan-leaflet';ST.nav.navL=NL;ST.nav.casing=NL.polyline(route.points,{color:'#2a1738',weight:12,opacity:.92,lineCap:'round',lineJoin:'round'}).addTo(map);ST.nav.line=NL.polyline(route.points,{color:'#7b24d6',weight:8,opacity:1,lineCap:'round',lineJoin:'round'}).addTo(map);const icon=NL.divIcon({className:'aqst-nav-user',html:'<span id="aqst-nav-arrow">▲</span>',iconSize:[54,54],iconAnchor:[27,27]});ST.nav.marker=NL.marker([pos.lat,pos.lng],{icon,zIndexOffset:1500}).addTo(map);ST.nav.destMarker=NL.circleMarker([target.lat,target.lng],{radius:10,color:'#fff',weight:3,fillColor:'#7b24d6',fillOpacity:1}).addTo(map);setTimeout(()=>map.invalidateSize?.(),100)}
'''.strip()

_INIT_NAV = r'''async function initNavMap(route,pos,target){try{ST.nav.map?.remove?.()}catch{}ST.nav.map=null;ST.nav.mapKind=null;ST.nav.marker=null;ST.nav.destMarker=null;ST.nav.navL=null;const container=$('#aqst-nav-map');if(container){container.classList.remove('aqst-leaflet-heading-up');container.style.removeProperty('--aqst-fallback-rotation');container.innerHTML=''}try{const sdk=await neshanSdk();await initNeshanGlMap(sdk,route,pos,target);$('#aqst-drive-mode').textContent='نقشه نشان • جهت حرکت • ترافیک'}catch(glError){console.warn('Aqua Neshan GL fallback',glError);try{await initNeshanLeafletNavMap(route,pos,target);$('#aqst-drive-mode').textContent='نقشه نشان • حالت سازگار آیفون'}catch(leafError){console.warn('Aqua Neshan Leaflet fallback',leafError);initLeafletNavMap(route,pos,target);$('#aqst-drive-mode').textContent='حالت پشتیبان'}}}'''

_INIT_OSM = r'''function initLeafletNavMap(route,pos,target){ST.nav.map=L.map('aqst-nav-map',{zoomControl:false,attributionControl:false,preferCanvas:true}).setView([pos.lat,pos.lng],17);ST.nav.mapKind='leaflet';ST.nav.navL=L;L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(ST.nav.map);ST.nav.casing=L.polyline(route.points,{color:'#2a1738',weight:12,opacity:.9,lineCap:'round',lineJoin:'round'}).addTo(ST.nav.map);ST.nav.line=L.polyline(route.points,{color:'#7b24d6',weight:8,opacity:1,lineCap:'round',lineJoin:'round'}).addTo(ST.nav.map);const icon=L.divIcon({className:'aqst-nav-user',html:'<span id="aqst-nav-arrow">▲</span>',iconSize:[54,54],iconAnchor:[27,27]});ST.nav.marker=L.marker([pos.lat,pos.lng],{icon,zIndexOffset:1500}).addTo(ST.nav.map);ST.nav.destMarker=L.circleMarker([target.lat,target.lng],{radius:10,color:'#fff',weight:3,fillColor:'#7b24d6',fillOpacity:1}).addTo(ST.nav.map);setTimeout(()=>ST.nav.map.invalidateSize(),80)}'''

_SET_FOLLOW = r'''function setFollowMode(on){ST.nav.follow=!!on;const b=$('#aqst-recenter');if(b)b.hidden=!!on;if(!on)aqResetLeafletHeading();if(on&&ST.nav.active&&ST.nav.lastPos)updateDriveCamera(ST.nav.lastPos,ST.nav.lastCoords||{},ST.nav.lastNear||nearestPointInfo(ST.nav.lastPos,ST.nav.route?.points||[]),true)}'''

_CAMERA = r'''function updateDriveCamera(pos,coords,near,immediate=false){if(!ST.nav.follow||!ST.nav.map)return;const route=ST.nav.route,proj=typeof aqRouteProjection==='function'?aqRouteProjection(pos,route):null,matched=proj&&proj.d<=120?{lat:proj.lat,lng:proj.lng}:pos,idx=proj?proj.i:Number(near?.i||0),rem=remainingDistance(route,{...(near||{}),i:idx}),rb=routeBearing(route,idx);let h=Number(coords?.heading),speed=Number(coords?.speed);if(!Number.isFinite(h)||h<0||!Number.isFinite(speed)||speed<1.2)h=rb;if(typeof aqSmoothHeading==='function')h=aqSmoothHeading(h);if(ST.nav.mapKind==='gl'){aqResetLeafletHeading();try{ST.nav.map.easeTo({center:[matched.lng,matched.lat],bearing:h,pitch:rem<180?48:56,zoom:rem<220?18.8:18.35,duration:immediate?0:620,essential:true})}catch{}}else try{ST.nav.map.setView([matched.lat,matched.lng],rem<300?18:17,{animate:!immediate});if(typeof ST.nav.map.setBearing==='function'){aqResetLeafletHeading();ST.nav.map.setBearing(h)}else{aqApplyLeafletHeading(h)}$('#aqst-nav-arrow')?.style.setProperty('transform',typeof ST.nav.map.setBearing==='function'?'rotate(0deg)':`rotate(${h}deg)`)}catch{}}'''

_OVERVIEW = r'''function showRouteOverview(){const pts=ST.nav.route?.points||[];if(!pts.length||!ST.nav.map)return;setFollowMode(false);if(ST.nav.mapKind==='gl'){try{const gl=window.nmp_mapboxgl,b=new gl.LngLatBounds();pts.forEach(p=>b.extend([p[1],p[0]]));ST.nav.map.fitBounds(b,{padding:{top:70,bottom:120,left:38,right:38},pitch:12,bearing:0,duration:650})}catch{}}else try{ST.nav.map.fitBounds(pts,{padding:[42,42]})}catch{}}'''

_UPDATE_TOP = r'''function updateTopInstruction(info,rem,seconds){const step=info.step,target=ST.nav.target||{},distance=Number(info.distance||0);$('#aqst-maneuver-icon').textContent=navIcon(step);$('#aqst-maneuver-distance').textContent=step?.type==='arrive'?'مقصد':roundVoiceDistance(distance);$('#aqst-turn').textContent=step?.instruction||`در مسیر ${target.name||'مقصد'} ادامه بده`;$('#aqst-turnsub').textContent=step?.name||target.name||'';const next=$('#aqst-next-strip');if(next)next.hidden=true;$('#aqst-remain').textContent=fmtKm(rem);$('#aqst-nav-eta').textContent=fmtDur(seconds);$('#aqst-arrival').textContent=arrivalClock(seconds)}'''

_UPDATE_POS = r'''function updateNavPosition(pos,coords={},initial=false){if(!ST.nav.active)return;const route=ST.nav.route,pts=route?.points||[];if(!pts.length)return;const proj=typeof aqRouteProjection==='function'?aqRouteProjection(pos,route):null,near=proj?{d:proj.d,i:proj.i}:nearestPointInfo(pos,pts),rem=remainingDistance(route,near),total=Math.max(1,Number(route.distance_m||route._total||rem)),seconds=Math.max(0,Math.round(Number(route.duration_s||0)*Math.min(1,rem/total)));ST.nav.lastPos=pos;ST.nav.lastCoords=coords||{};ST.nav.lastNear=near;const info=findNextStep(route,near);ST.nav.stepIndex=info.index;updateTopInstruction(info,rem,seconds);if(!initial)maybeAnnounceManeuver(info);const aqVisiblePos=proj&&proj.d<=120?{lat:proj.lat,lng:proj.lng,_route_i:proj.i,_snap_d:proj.d}:(typeof aqMatchedPosition==='function'?aqMatchedPosition(pos,route):pos);ST.nav.lastMatched=aqVisiblePos;if(ST.nav.mapKind==='gl')ST.nav.marker?.setLngLat?.([aqVisiblePos.lng,aqVisiblePos.lat]);else ST.nav.marker?.setLatLng?.([aqVisiblePos.lat,aqVisiblePos.lng]);if(typeof aqSyncMainNavMini==='function')aqSyncMainNavMini(aqVisiblePos);ST.nav.prevPos=pos;updateDriveCamera(pos,coords,near,initial);const td=hav([pos.lat,pos.lng],[ST.nav.target.lat,ST.nav.target.lng]);if(td<32){$('#aqst-maneuver-icon').textContent='●';$('#aqst-maneuver-distance').textContent='رسیدی';$('#aqst-turn').textContent='به مقصد رسیدی';$('#aqst-turnsub').textContent=ST.nav.target.name||'';$('#aqst-remain').textContent='۰ متر';$('#aqst-nav-eta').textContent='۰ دقیقه';$('#aqst-arrival').textContent=arrivalClock(0);if(!ST.nav.arrived){ST.nav.arrived=true;ariaSpeak(`به مقصد ${ST.nav.target.name||''} رسیدی`,{replace:true})}return}const accuracy=Number(coords?.accuracy),acc=Number.isFinite(accuracy)&&accuracy>0?Math.min(60,accuracy):15,offThreshold=Math.max(70,Math.min(150,acc*2.2+35));ST.nav.lastOffDistance=near.d;ST.nav.offThreshold=offThreshold;if(near.d>offThreshold)ST.nav.offCount=(ST.nav.offCount||0)+1;else if(near.d<offThreshold*.65)ST.nav.offCount=0;else ST.nav.offCount=Math.max(0,(ST.nav.offCount||0)-1);if(ST.nav.offCount>=4&&Date.now()-ST.nav.lastReroute>35000){ST.nav.offCount=0;ST.nav.lastReroute=Date.now();reroute(pos)}}'''

_ON_POS = r'''async function onNavPosition(p){if(!ST.nav.active)return;updateNavPosition({lat:p.coords.latitude,lng:p.coords.longitude},{heading:p.coords.heading,speed:p.coords.speed,accuracy:p.coords.accuracy},false)}'''


_FALLBACK_CSS = r'''
/* Aqua Neshan-like iPhone navigation + reliable fallback — 20260908 */
#aqst-nav{background:#e9ece8!important;grid-template-rows:auto 1fr auto!important}
#aqst-nav .aqst-next-strip{display:none!important}
#aqst-nav .aqst-navhead{margin:10px 8px 0!important;min-height:148px!important;padding:18px 15px!important;border-radius:24px!important;background:#070809!important;border:0!important;box-shadow:0 10px 30px rgba(0,0,0,.28)!important;grid-template-columns:74px minmax(0,1fr)!important;gap:14px!important;direction:ltr!important}
#aqst-nav .aqst-maneuver-icon{width:70px!important;height:70px!important;border-radius:18px!important;background:transparent!important;color:#fff!important;font-size:3.25rem!important;box-shadow:none!important;align-self:start!important}
#aqst-nav .aqst-maneuver-copy{direction:rtl!important;text-align:right!important;padding-top:2px!important}
#aqst-nav .aqst-maneuver-distance{font-size:1.08rem!important;color:#fff!important;font-weight:950!important;margin-bottom:8px!important}
#aqst-nav .aqst-turn{font-size:1.45rem!important;line-height:1.45!important;color:#74d7ff!important;font-weight:950!important}
#aqst-nav .aqst-turnsub{font-size:.9rem!important;color:#a9b0b5!important;margin-top:5px!important}
#aqst-nav .aqst-navtools{position:absolute!important;right:12px!important;top:calc(100% + 28px)!important;z-index:2147481800!important;display:grid!important;gap:12px!important}
#aqst-nav .aqst-navtools button{width:54px!important;height:54px!important;border-radius:50%!important;background:rgba(255,255,255,.94)!important;color:#111!important;border:1px solid rgba(0,0,0,.07)!important;box-shadow:0 5px 15px rgba(0,0,0,.16)!important;font-size:1.25rem!important}
#aqst-nav .aqst-navmap{margin-top:0!important;overflow:hidden!important;isolation:isolate!important;background:#e7ebe7!important}
#aqst-nav #aqst-nav-map{z-index:1!important;transform-origin:50% 50%!important;background:#e7ebe7!important}
#aqst-nav #aqst-nav-map.aqst-leaflet-heading-up{transform:rotate(var(--aqst-fallback-rotation,0deg)) scale(1.45)!important;transition:transform .35s linear!important;will-change:transform!important}
#aqst-nav .leaflet-tile-pane{filter:none!important}
#aqst-nav .aqst-nav-user{background:transparent!important;border:0!important}
#aqst-nav .aqst-nav-user span{width:54px!important;height:54px!important;display:grid!important;place-items:center!important;color:#079bd6!important;font-size:2.5rem!important;text-shadow:-2px -2px 0 #fff,2px -2px 0 #fff,-2px 2px 0 #fff,2px 2px 0 #fff,0 5px 10px rgba(0,0,0,.45)!important;transform-origin:50% 50%!important}
#aqst-nav .aqst-drive-mode{display:none!important}
#aqst-nav #aqst-recenter{position:absolute!important;z-index:2147481850!important;left:12px!important;bottom:16px!important;pointer-events:auto!important;border:0!important;border-radius:999px!important;background:rgba(255,255,255,.95)!important;color:#151515!important;box-shadow:0 5px 18px rgba(0,0,0,.18)!important;min-height:46px!important;padding:0 16px!important}
#aqst-nav #aqst-recenter[hidden]{display:none!important}
#aqst-nav .aqst-navfoot{grid-template-columns:repeat(3,1fr)!important;gap:0!important;padding:13px 10px max(14px,env(safe-area-inset-bottom))!important;background:#fff!important;color:#111!important;border:0!important;border-radius:24px 24px 0 0!important;box-shadow:0 -8px 26px rgba(0,0,0,.12)!important;z-index:2147481900!important}
#aqst-nav .aqst-navmetric{padding:5px 4px!important;border-left:1px solid #e5e5e5!important;color:#111!important}
#aqst-nav .aqst-navmetric:nth-child(3){border-left:0!important}
#aqst-nav .aqst-navmetric b{font-size:1.05rem!important;color:#111!important;font-weight:950!important}
#aqst-nav .aqst-navmetric small{font-size:.68rem!important;color:#666!important}
#aqst-nav .aqst-stop{grid-column:1/-1!important;margin:8px 6px 0!important;border-radius:15px!important;padding:10px!important;background:#d82b3e!important;color:#fff!important;font-size:.9rem!important}
#aqst-nav-resume{position:fixed!important;z-index:2147481850!important;left:14px!important;bottom:calc(96px + env(safe-area-inset-bottom,0px))!important;pointer-events:auto!important}
#aqst-nav-resume[hidden]{display:none!important}
#aqst-nav .mapboxgl-canvas{background:#e7ebe7!important}
#aqst-nav .mapboxgl-ctrl-bottom-left,#aqst-nav .mapboxgl-ctrl-bottom-right{opacity:.48!important;font-size:8px!important}
@media(max-width:700px){
 #aqst-nav .aqst-navhead{margin:7px 7px 0!important;min-height:136px!important;padding:15px 12px!important;grid-template-columns:62px minmax(0,1fr)!important;gap:10px!important}
 #aqst-nav .aqst-maneuver-icon{width:60px!important;height:60px!important;font-size:2.8rem!important}
 #aqst-nav .aqst-turn{font-size:1.23rem!important}
 #aqst-nav .aqst-maneuver-distance{font-size:.94rem!important;margin-bottom:5px!important}
 #aqst-nav .aqst-navtools{right:10px!important;top:calc(100% + 18px)!important;gap:10px!important}
 #aqst-nav .aqst-navtools button{width:48px!important;height:48px!important}
 #aqst-nav #aqst-recenter{left:10px!important;bottom:12px!important;min-height:44px!important}
 #aqst-nav-resume{left:12px!important;bottom:calc(92px + env(safe-area-inset-bottom,0px))!important;min-height:44px!important}
 #aqst-nav .aqst-navfoot{padding-top:10px!important}
 #aqst-nav .aqst-stop{padding:9px!important}
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
            marker = "function aqNeshanLeafletSdk()"
            if marker not in source and "function initLeafletNavMap(" in source:
                source = source.replace("function initLeafletNavMap(", _NESHAN_LEAFLET + "\nfunction initLeafletNavMap(", 1)
                if "function aqResetLeafletHeading()" not in source:
                    source = source.replace("function setFollowMode(", _HELPERS + "\nfunction setFollowMode(", 1)
                source = _replace_function(source, "initNavMap", "aqRouteProjection", _INIT_NAV)
                source = _replace_function(source, "initLeafletNavMap", "aqResetLeafletHeading", _INIT_OSM)
                source = _replace_function(source, "setFollowMode", "updateDriveCamera", _SET_FOLLOW)
                source = _replace_function(source, "updateDriveCamera", "showRouteOverview", _CAMERA)
                source = _replace_function(source, "showRouteOverview", "updateRouteLayer", _OVERVIEW)
                source = _replace_function(source, "updateTopInstruction", "maneuverSpeech", _UPDATE_TOP)
                source = _replace_function(source, "updateNavPosition", "onNavPosition", _UPDATE_POS)
                source = _replace_function(source, "onNavPosition", "reroute", _ON_POS)
                source = source.replace("'line-color':'#16c7f4'", "'line-color':'#7b24d6'")
                source = source.replace("'line-color':'#f4fbff'", "'line-color':'#2a1738'")
                response.set_data(source)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            marker = "Aqua Neshan-like iPhone navigation + reliable fallback — 20260908"
            if marker not in css:
                css += "\n" + _FALLBACK_CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_fallback_heading_asset_failed: %s", str(exc)[:180])
    return response
