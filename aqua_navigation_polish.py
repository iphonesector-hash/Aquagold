"""Preview-only final polish for Aqua Map/Navigation.

This module stays scoped to the current feature branch. It fixes Neshan search
service mismatch with Geocoding Plus fallback, keeps the navigation marker
snapped to the routed road when GPS jitter is small, centers drive view on the
user instead of looking too far ahead, adds minimize/restore + day/night, and
uses a synchronized Neshan Web background (POI + traffic) under the existing
Leaflet overlays so customer markers/routes remain regression-safe.
"""
from __future__ import annotations

import re

from flask import jsonify, request

import app_v3
import aqua_neshan_preview as neshan
from aquagold_validation import text as valid_text


def _coord(value, fallback=None):
    try:
        return float(value)
    except Exception:
        return fallback


def _search_items(payload: dict, query: str):
    out = []
    for item in payload.get("items") or []:
        loc = item.get("location") or {}
        lat = loc.get("latitude", loc.get("y"))
        lng = loc.get("longitude", loc.get("x"))
        if lat is None or lng is None:
            continue
        out.append({
            "title": item.get("title") or item.get("name") or query,
            "address": item.get("address") or item.get("neighbourhood") or "",
            "type": item.get("type") or "search",
            "region": item.get("region") or item.get("city") or "",
            "latitude": float(lat),
            "longitude": float(lng),
        })
    return out


def _geocode_items(payload: dict, query: str):
    out = []
    for item in payload.get("items") or []:
        loc = item.get("location") or {}
        lat = loc.get("latitude", loc.get("y"))
        lng = loc.get("longitude", loc.get("x"))
        if lat is None or lng is None:
            continue
        province = str(item.get("province") or "").strip()
        city = str(item.get("city") or "").strip()
        neighbourhood = str(item.get("neighbourhood") or "").strip()
        label = "، ".join(x for x in (province, city, neighbourhood) if x)
        out.append({
            "title": neighbourhood or city or query,
            "address": label or query,
            "type": "geocode-plus",
            "region": city or province,
            "latitude": float(lat),
            "longitude": float(lng),
        })
    return out


@app_v3.token_required
@app_v3.limiter.limit("60 per hour")
def _polished_place_search():
    query = valid_text(request.args.get("q"), "جست‌وجوی مکان", required=True, max_length=180)
    lat = _coord(request.args.get("lat"), 35.6892)
    lng = _coord(request.args.get("lng"), 51.3890)
    search_error = ""
    try:
        # Canonical Neshan location search endpoint. Some service keys do not
        # include Search; when that happens we transparently fall back below.
        payload = neshan._neshan_get("/v1/search", {"term": query, "lat": lat, "lng": lng}, timeout=10)
        items = _search_items(payload, query)
        if items:
            return jsonify({"provider": "neshan-search", "items": items[:10]})
    except Exception as exc:
        search_error = str(exc)[:160]

    try:
        # The configured Aqua key includes Geocoding Plus, so address/plaque/
        # landmark-style text still works even when Search is not licensed.
        payload = neshan.geocode_address(query, plus=True, timeout=10)
        return jsonify({"provider": "neshan-geocoding-plus", "fallback": True, "items": _geocode_items(payload, query)[:10]})
    except Exception as exc:
        app_v3.logger.warning("aqua_map_search_failed search=%s geocode=%s", search_error, str(exc)[:140])
        return jsonify({"error": "این عبارت در سرویس‌های فعال نشان پیدا نشد؛ روی نقشه نگه دار تا همان نقطه مقصد شود."}), 502


# Override only the branch Smart Tour search surface.
if "smart_tour_place_search" in app_v3.app.view_functions:
    app_v3.app.view_functions["smart_tour_place_search"] = _polished_place_search


_HELPERS = r'''
function aqRouteProjection(pos,route){
 const pts=route?.points||[];if(pts.length<2){const n=nearestPointInfo(pos,pts);return{...n,lat:pts[n.i]?.[0]??pos.lat,lng:pts[n.i]?.[1]??pos.lng}}
 const cos=Math.cos(pos.lat*Math.PI/180),mx=Math.max(1,111320*cos),my=110540;let best={d:Infinity,i:0,t:0,lat:pos.lat,lng:pos.lng};
 for(let i=0;i<pts.length-1;i++){
  const a=pts[i],b=pts[i+1],ax=(a[1]-pos.lng)*mx,ay=(a[0]-pos.lat)*my,bx=(b[1]-pos.lng)*mx,by=(b[0]-pos.lat)*my,dx=bx-ax,dy=by-ay,den=dx*dx+dy*dy||1,t=Math.max(0,Math.min(1,-(ax*dx+ay*dy)/den)),x=ax+t*dx,y=ay+t*dy,d=Math.hypot(x,y);
  if(d<best.d)best={d,i,t,lat:pos.lat+y/my,lng:pos.lng+x/mx};
 }
 return best
}
function aqMatchedPosition(pos,route){const p=aqRouteProjection(pos,route);return p.d<=95?{lat:p.lat,lng:p.lng,_route_i:p.i,_snap_d:p.d}:{...pos,_route_i:p.i,_snap_d:p.d}}
function aqSmoothHeading(next){next=((Number(next)||0)%360+360)%360;let prev=Number(ST.nav.cameraHeading);if(!Number.isFinite(prev)){ST.nav.cameraHeading=next;return next}let delta=((next-prev+540)%360)-180;ST.nav.cameraHeading=(prev+delta*.32+360)%360;return ST.nav.cameraHeading}
function aqNavMapType(gl){if(ST.nav.theme==='night')return gl.Map.mapTypes.neshanVectorNight||gl.Map.mapTypes.neshanVector;return gl.Map.mapTypes.neshanVector}
function aqRemoveMainNavMini(){try{const m=mainMap();if(ST.nav.mainMiniMarker)m?.removeLayer(ST.nav.mainMiniMarker)}catch{}ST.nav.mainMiniMarker=null}
function aqSyncMainNavMini(point){if(!ST.nav.minimized||!point||!window.L)return;const m=mainMap();if(!m)return;try{if(!ST.nav.mainMiniMarker){const ic=L.divIcon({className:'aqst-mini-user',html:'▲',iconSize:[34,34],iconAnchor:[17,17]});ST.nav.mainMiniMarker=L.marker([point.lat,point.lng],{icon:ic,zIndexOffset:1400}).addTo(m)}else ST.nav.mainMiniMarker.setLatLng([point.lat,point.lng]);m.setView([point.lat,point.lng],17)}catch{}}
function aqEnsureResume(){let b=$('#aqst-nav-resume');if(b)return b;const frame=$('.aq-map-frame');if(!frame)return null;b=document.createElement('button');b.id='aqst-nav-resume';b.type='button';b.textContent='↗ بازگشت به مسیریابی';b.hidden=true;b.addEventListener('click',aqResumeNavigation);frame.appendChild(b);return b}
function aqMinimizeNavigation(){if(!ST.nav.active)return;ST.nav.minimized=true;document.documentElement.classList.remove('aqst-nav-fullscreen');$('#aqst-nav').hidden=true;const b=aqEnsureResume();if(b)b.hidden=false;aqSyncMainNavMini(ST.nav.lastMatched||ST.nav.lastPos);setTimeout(()=>mainMap()?.invalidateSize?.(),80)}
function aqResumeNavigation(){if(!ST.nav.active)return;ST.nav.minimized=false;aqRemoveMainNavMini();const b=$('#aqst-nav-resume');if(b)b.hidden=true;document.documentElement.classList.add('aqst-nav-fullscreen');$('#aqst-nav').hidden=false;setTimeout(()=>{try{ST.nav.mapKind==='gl'?ST.nav.map?.resize?.():ST.nav.map?.invalidateSize?.()}catch{}setFollowMode(true)},90)}
async function aqRestoreWakeLock(){if(!ST.nav.active||document.visibilityState!=='visible'||!navigator.wakeLock?.request)return;if(ST.nav.wake&&!ST.nav.wake.released)return;try{ST.nav.wake=await navigator.wakeLock.request('screen')}catch{ST.nav.wake=null}}
function aqRefreshNavViewport(){if(!ST.nav.active)return;setTimeout(()=>{try{ST.nav.mapKind==='gl'?ST.nav.map?.resize?.():ST.nav.map?.invalidateSize?.()}catch{}if(ST.nav.lastPos)updateDriveCamera(ST.nav.lastPos,ST.nav.lastCoords||{},ST.nav.lastNear||nearestPointInfo(ST.nav.lastPos,ST.nav.route?.points||[]),true)},120)}
async function aqToggleNavTheme(){ST.nav.theme=ST.nav.theme==='night'?'day':'night';const b=$('#aqst-theme');if(b)b.textContent=ST.nav.theme==='night'?'☀':'☾';if(!ST.nav.active||!ST.nav.lastPos)return;const p=ST.nav.lastPos;await initNavMap(ST.nav.route,p,ST.nav.target);updateNavPosition(p,ST.nav.lastCoords||{},true)}
function aqTidyMapToolbar(){const el=$('#mainMap');if(!el)return;let root=el.closest('section')||el.parentElement?.parentElement||document;const buttons=[...root.querySelectorAll('button')],near=buttons.find(b=>b.textContent.includes('اطراف من')),opt=buttons.find(b=>b.textContent.includes('بهینه‌سازی مسیر'));if(near&&opt&&near.parentElement===opt.parentElement&&!near.closest('.aqst-route-pair')){const pair=document.createElement('div');pair.className='aqst-route-pair';near.parentElement.insertBefore(pair,near);pair.append(near,opt)}}
async function aqSetupMainNeshan(){
 const leaf=mainMap(),host=$('.aq-map-frame');if(!leaf||!host||$('#aqst-main-neshan-bg'))return;
 try{
  const {gl,key}=await neshanSdk(),bg=document.createElement('div');bg.id='aqst-main-neshan-bg';host.prepend(bg);
  const c=leaf.getCenter(),map=new gl.Map({mapType:document.documentElement.dataset.theme==='dark'?(gl.Map.mapTypes.neshanVectorNight||gl.Map.mapTypes.neshanVector):gl.Map.mapTypes.neshanVector,container:bg,zoom:leaf.getZoom(),pitch:0,bearing:0,center:[c.lng,c.lat],minZoom:2,maxZoom:21,trackResize:true,mapKey:key,poi:true,traffic:true,isTouchPlatform:true,dragPan:false,dragRotate:false,scrollZoom:false,touchZoomRotate:false,doubleClickZoom:false,keyboard:false});
  ST.nav.mainNeshan=map;map.on('load',()=>{host.classList.add('aqst-main-neshan-ready');const sync=()=>{try{const cc=leaf.getCenter();map.jumpTo({center:[cc.lng,cc.lat],zoom:leaf.getZoom(),bearing:0,pitch:0})}catch{}};leaf.on('move zoom resize',sync);sync();setTimeout(()=>map.resize(),100)});
 }catch(e){console.warn('Aqua main Neshan background fallback',e)}
}
function aqSetupPolish(){
 aqTidyMapToolbar();aqEnsureResume();const mapbox=$('#aqst-nav .aqst-navmap');if(mapbox&&!$('#aqst-map-actions')){const tools=document.createElement('div');tools.id='aqst-map-actions';tools.className='aqst-map-actions';tools.innerHTML='<button type="button" id="aqst-theme" aria-label="حالت شب و روز">☾</button><button type="button" id="aqst-minimize" aria-label="کوچک کردن نقشه">↙</button>';mapbox.appendChild(tools);$('#aqst-theme').addEventListener('click',aqToggleNavTheme);$('#aqst-minimize').addEventListener('click',aqMinimizeNavigation)}
 setTimeout(aqTidyMapToolbar,300);setTimeout(aqTidyMapToolbar,1100);setTimeout(aqSetupMainNeshan,700);setTimeout(aqSetupMainNeshan,1800)
}
'''.strip()

_INIT_GL = r'''function initNeshanGlMap({gl,key},route,pos,target){return new Promise((resolve,reject)=>{try{const proj=aqRouteProjection(pos,route),matched=proj.d<=95?{lat:proj.lat,lng:proj.lng}:pos,heading=routeBearing(route,proj.i);const map=new gl.Map({mapType:aqNavMapType(gl),container:'aqst-nav-map',zoom:18.35,pitch:54,bearing:heading,center:[matched.lng,matched.lat],minZoom:2,maxZoom:21,trackResize:true,mapKey:key,poi:true,traffic:true,isTouchPlatform:true,dragRotate:true,touchZoomRotate:true,touchPitch:true});ST.nav.map=map;ST.nav.mapKind='gl';let settled=false;const fail=setTimeout(()=>{if(!settled){settled=true;try{map.remove()}catch{}reject(Error('نقشه سه‌بعدی نشان دیر پاسخ داد'))}},12000);map.on('load',()=>{if(settled)return;settled=true;clearTimeout(fail);try{map.touchZoomRotate?.enable?.();map.touchZoomRotate?.enableRotation?.();map.touchPitch?.enable?.();map.dragRotate?.enable?.()}catch{}map.addSource('aqua-route',{type:'geojson',data:routeGeo(route)});map.addLayer({id:'aqua-route-casing',type:'line',source:'aqua-route',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#f4fbff','line-width':12,'line-opacity':.92}});map.addLayer({id:'aqua-route-line',type:'line',source:'aqua-route',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#16c7f4','line-width':7,'line-opacity':1}});const u=document.createElement('div');u.className='aqst-gl-user';u.innerHTML='<span>▲</span>';ST.nav.userEl=u;ST.nav.marker=new gl.Marker({element:u,anchor:'center'}).setLngLat([matched.lng,matched.lat]).addTo(map);const d=document.createElement('div');d.className='aqst-gl-destination';d.innerHTML='<span></span>';ST.nav.destMarker=new gl.Marker({element:d,anchor:'bottom'}).setLngLat([target.lng,target.lat]).addTo(map);['dragstart','rotatestart','pitchstart','zoomstart'].forEach(ev=>map.on(ev,e=>{if(e?.originalEvent)setFollowMode(false)}));setTimeout(()=>map.resize(),80);resolve()});map.on('error',e=>{if(!settled&&e?.error){clearTimeout(fail);settled=true;try{map.remove()}catch{}reject(e.error)}})}catch(e){reject(e)}})}'''

_CAMERA = r'''function updateDriveCamera(pos,coords,near,immediate=false){if(!ST.nav.follow||!ST.nav.map)return;const route=ST.nav.route,proj=aqRouteProjection(pos,route),matched=proj.d<=95?{lat:proj.lat,lng:proj.lng}:pos,rem=remainingDistance(route,{...near,i:proj.i}),rb=routeBearing(route,proj.i);let h=Number(coords?.heading),speed=Number(coords?.speed);if(!Number.isFinite(h)||h<0||!Number.isFinite(speed)||speed<1.2)h=rb;h=aqSmoothHeading(h);if(ST.nav.mapKind==='gl'){try{ST.nav.map.easeTo({center:[matched.lng,matched.lat],bearing:h,pitch:rem<180?46:54,zoom:rem<220?18.7:18.25,duration:immediate?0:620,essential:true})}catch{}}else try{ST.nav.map.setView([matched.lat,matched.lng],rem<300?18:17,{animate:!immediate});$('#aqst-nav-arrow')?.style.setProperty('transform',`rotate(${h-90}deg)`)}catch{}}'''

_UPDATE_POS = r'''function updateNavPosition(pos,coords={},initial=false){if(!ST.nav.active)return;const route=ST.nav.route,pts=route?.points||[];if(!pts.length)return;const rawNear=nearestPointInfo(pos,pts),proj=aqRouteProjection(pos,route),near={d:proj.d,i:proj.i},matched=proj.d<=95?{lat:proj.lat,lng:proj.lng}:pos,rem=remainingDistance(route,near),total=Math.max(1,Number(route.distance_m||route._total||rem)),seconds=Math.max(0,Math.round(Number(route.duration_s||0)*Math.min(1,rem/total)));ST.nav.lastPos=pos;ST.nav.lastMatched=matched;ST.nav.lastCoords=coords||{};ST.nav.lastNear=near;const info=findNextStep(route,near);ST.nav.stepIndex=info.index;updateTopInstruction(info,rem,seconds);if(!initial)maybeAnnounceManeuver(info);if(ST.nav.mapKind==='gl')ST.nav.marker?.setLngLat?.([matched.lng,matched.lat]);else ST.nav.marker?.setLatLng?.([matched.lat,matched.lng]);aqSyncMainNavMini(matched);ST.nav.prevPos=pos;updateDriveCamera(pos,coords,near,initial);const td=hav([pos.lat,pos.lng],[ST.nav.target.lat,ST.nav.target.lng]);if(td<32){$('#aqst-maneuver-icon').textContent='●';$('#aqst-maneuver-distance').textContent='رسیدی';$('#aqst-turn').textContent='به مقصد رسیدی';$('#aqst-turnsub').textContent=ST.nav.target.name||'';$('#aqst-remain').textContent='۰ متر';$('#aqst-nav-eta').textContent='۰ دقیقه';$('#aqst-arrival').textContent=arrivalClock(0);if(!ST.nav.arrived){ST.nav.arrived=true;ariaSpeak(`به مقصد ${ST.nav.target.name||''} رسیدی`,{replace:true})}return}if(proj.d>100)ST.nav.offCount++;else ST.nav.offCount=0;if(ST.nav.offCount>=2&&Date.now()-ST.nav.lastReroute>25000){ST.nav.offCount=0;ST.nav.lastReroute=Date.now();reroute(pos)}}'''

_POLISH_JS = r'''
aqSetupPolish();
if(!window.__aquaNavLifecycleBound){window.__aquaNavLifecycleBound=true;document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){aqRestoreWakeLock();aqRefreshNavViewport()}});window.addEventListener('orientationchange',aqRefreshNavViewport,{passive:true});window.visualViewport?.addEventListener?.('resize',aqRefreshNavViewport,{passive:true})}
const aqPolishObserver=new MutationObserver(()=>{aqTidyMapToolbar();if($('#mainMap'))aqSetupMainNeshan()});
aqPolishObserver.observe(document.documentElement,{subtree:true,childList:true});
'''.strip()

_POLISH_CSS = r'''
/* Aqua Neshan navigation polish */
html.aqst-nav-fullscreen,html.aqst-nav-fullscreen body{overflow:hidden!important}
#aqst-nav{position:fixed!important;inset:0!important;width:100vw!important;height:100dvh!important;z-index:9999!important;max-width:none!important;margin:0!important;border-radius:0!important}
#aqst-nav[hidden]{display:none!important}
#aqst-nav .aqst-navmap{min-height:0!important}
#aqst-nav #aqst-nav-map{width:100%!important;height:100%!important;min-height:0!important}
#aqst-map-actions{position:absolute;z-index:35;left:12px;top:18px;display:grid;gap:8px}
#aqst-map-actions button{width:44px;height:44px;border:1px solid rgba(255,255,255,.14);border-radius:15px;background:rgba(5,18,29,.88);color:#fff;font-size:1.2rem;font-weight:900;box-shadow:0 10px 24px rgba(0,0,0,.28);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
#aqst-nav-resume{position:absolute;z-index:50;left:12px;bottom:14px;border:0;border-radius:15px;padding:10px 13px;background:#16aee5;color:#02151d;font:inherit;font-size:.75rem;font-weight:950;box-shadow:0 10px 26px rgba(0,130,220,.32)}
#aqst-nav-resume[hidden]{display:none!important}
.aq-map-frame{position:relative!important;overflow:hidden!important}
.aq-map-frame #mainMap{height:300px!important;min-height:300px!important;background:transparent!important;position:relative;z-index:2}
#aqst-main-neshan-bg{position:absolute;inset:0;z-index:1;pointer-events:none;background:#dde2df}
.aq-map-frame.aqst-main-neshan-ready #mainMap .leaflet-tile-pane{opacity:0!important}
.aq-map-frame.aqst-main-neshan-ready #mainMap .leaflet-control-attribution{display:none!important}
.aq-map-frame.aqst-main-neshan-ready #mainMap .leaflet-container{background:transparent!important}
.aqst-route-pair{display:grid!important;grid-template-columns:1fr 1fr!important;gap:8px!important;flex:1 1 100%}
.aqst-route-pair>.btn,.aqst-route-pair>button{width:100%!important;min-width:0!important}
#aq-smart-tour .aqst-searchbar,#aqst-free-search .aqst-free-searchbar{grid-template-columns:minmax(0,1fr) auto!important;align-items:stretch}
#aq-smart-tour input,#aqst-free-search input{min-width:0!important;max-width:100%!important}
#aq-smart-tour .aqst-selected{display:flex!important;flex-wrap:wrap!important;align-items:center!important;gap:8px!important}
#aq-smart-tour .aqst-selected-copy{min-width:0!important;flex:1 1 180px!important}
#aq-smart-tour .aqst-selected-copy small{white-space:normal!important;overflow-wrap:anywhere!important}
.aqst-mini-user{background:transparent!important;border:0!important;color:#12aff4!important;font-size:1.55rem!important;text-shadow:-2px -2px 0 #fff,2px -2px 0 #fff,-2px 2px 0 #fff,2px 2px 0 #fff,0 4px 8px rgba(0,0,0,.55)}
#aqst-nav .aqst-gl-user span{font-size:2.25rem!important;color:#10b8ff!important;text-shadow:-3px -3px 0 #fff,3px -3px 0 #fff,-3px 3px 0 #fff,3px 3px 0 #fff,0 5px 10px rgba(0,0,0,.55)!important}
@media(max-width:520px){.aq-map-frame #mainMap{height:265px!important;min-height:265px!important}#aqst-map-actions{left:8px;top:12px}#aqst-map-actions button{width:41px;height:41px}.aqst-route-pair{grid-template-columns:1fr 1fr!important}.aqst-free-searchbar button{padding:0 11px!important}.aqst-free-searchbar input{font-size:16px!important}}
'''.strip()


def _replace_function(source: str, name: str, next_name: str, replacement: str) -> str:
    pattern = rf"function\s+{re.escape(name)}\(.*?(?=\nfunction\s+{re.escape(next_name)}\()"
    return re.sub(pattern, replacement + "\n", source, count=1, flags=re.S)


@app_v3.app.after_request
def aqua_navigation_polish_assets(response):
    try:
        if response.status_code != 200:
            return response
        if request.path == "/aqua-smart-tour.js":
            response.direct_passthrough = False
            source = response.get_data(as_text=True)
            marker = "function aqRouteProjection(pos,route)"
            if marker not in source and "function initNeshanGlMap(" in source:
                source = source.replace("function initNeshanGlMap(", _HELPERS + "\nfunction initNeshanGlMap(", 1)
                source = _replace_function(source, "initNeshanGlMap", "initLeafletNavMap", _INIT_GL)
                source = _replace_function(source, "updateDriveCamera", "showRouteOverview", _CAMERA)
                source = _replace_function(source, "updateNavPosition", "onNavPosition", _UPDATE_POS)
                source = source.replace("$('#aqst-nav').hidden=false;await initNavMap", "ST.nav.minimized=false;document.documentElement.classList.add('aqst-nav-fullscreen');$('#aqst-nav').hidden=false;const aqResume=$('#aqst-nav-resume');if(aqResume)aqResume.hidden=true;await initNavMap", 1)
                source = source.replace("stopVoicePlayback();$('#aqst-nav').hidden=true;", "stopVoicePlayback();ST.nav.minimized=false;document.documentElement.classList.remove('aqst-nav-fullscreen');aqRemoveMainNavMini();const aqResume=$('#aqst-nav-resume');if(aqResume)aqResume.hidden=true;$('#aqst-nav').hidden=true;", 1)
                source = source.replace("\nfunction enhance(){", "\n" + _POLISH_JS + "\nfunction enhance(){", 1)
                response.set_data(source)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            if "/* Aqua Neshan navigation polish */" not in css:
                css += "\n" + _POLISH_CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_polish_asset_failed: %s", str(exc)[:180])
    return response
