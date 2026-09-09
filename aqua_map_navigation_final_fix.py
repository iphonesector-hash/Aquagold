"""Final Map/Navigation regression guard for PR #29.

This module is intentionally Map/Navigation-only. It runs as the outermost
response normalizer for the Smart Tour assets and preserves the restored map UI
while applying the remaining iPhone navigation fixes:
- compact customer/address search and one-row map action buttons;
- route-segment + GPS-accuracy off-route detection;
- single maneuver card (no duplicate next strip);
- Neshan GL, then official Neshan Leaflet, then OSM fallback;
- smooth marker/camera motion with raised purple route/marker styling;
- Screen Wake Lock reacquisition while navigation is active;
- touch-native long-press destination picking on iPhone/Safari.

No Finance, Aria, Bale, Push, database, main, or Production state is changed.
"""
from __future__ import annotations

import re

from flask import request

import app_v3


_HELPERS = r'''
function aqFinalClamp(v,a,b){return Math.max(a,Math.min(b,v))}
function aqFinalProject(pos,route){
 const pts=route?.points||[];if(pts.length<2){const n=nearestPointInfo(pos,pts);return{d:n.d,i:n.i,lat:pts[n.i]?.[0]??pos.lat,lng:pts[n.i]?.[1]??pos.lng}}
 const cos=Math.cos(pos.lat*Math.PI/180),mx=Math.max(1,111320*cos),my=110540;let best={d:Infinity,i:0,t:0,lat:pos.lat,lng:pos.lng};
 for(let i=0;i<pts.length-1;i++){
  const a=pts[i],b=pts[i+1],ax=(a[1]-pos.lng)*mx,ay=(a[0]-pos.lat)*my,bx=(b[1]-pos.lng)*mx,by=(b[0]-pos.lat)*my,dx=bx-ax,dy=by-ay,den=dx*dx+dy*dy||1,t=Math.max(0,Math.min(1,-(ax*dx+ay*dy)/den)),x=ax+t*dx,y=ay+t*dy,d=Math.hypot(x,y);
  if(d<best.d)best={d,i,t,lat:pos.lat+y/my,lng:pos.lng+x/mx};
 }
 return best
}
function aqFinalSmoothHeading(next){next=((Number(next)||0)%360+360)%360;let prev=Number(ST.nav.finalHeading);if(!Number.isFinite(prev)){ST.nav.finalHeading=next;return next}const delta=((next-prev+540)%360)-180;ST.nav.finalHeading=(prev+delta*.28+360)%360;return ST.nav.finalHeading}
function aqFinalSetMarker(p){if(!ST.nav.marker||!p)return;try{if(ST.nav.mapKind==='gl')ST.nav.marker.setLngLat([p.lng,p.lat]);else ST.nav.marker.setLatLng([p.lat,p.lng])}catch{}}
function aqFinalAnimateMarker(target,immediate=false){
 if(!target)return;const from=ST.nav.markerVisual||target;const token=(ST.nav.markerAnimToken||0)+1;ST.nav.markerAnimToken=token;
 if(immediate||!window.requestAnimationFrame){ST.nav.markerVisual=target;aqFinalSetMarker(target);return}
 const started=performance.now(),distance=Math.hypot((target.lat-from.lat)*110540,(target.lng-from.lng)*Math.max(1,111320*Math.cos(target.lat*Math.PI/180))),duration=aqFinalClamp(560+distance*5,620,980);
 function frame(now){if(token!==ST.nav.markerAnimToken)return;const x=aqFinalClamp((now-started)/duration,0,1),e=1-Math.pow(1-x,3),p={lat:from.lat+(target.lat-from.lat)*e,lng:from.lng+(target.lng-from.lng)*e};ST.nav.markerVisual=p;aqFinalSetMarker(p);if(x<1)requestAnimationFrame(frame)}requestAnimationFrame(frame)
}
function aqFinalResetHeading(){const el=$('#aqst-nav-map');if(!el)return;el.classList.remove('aqst-final-heading-up');el.style.removeProperty('--aqst-final-rotation')}
function aqFinalApplyHeading(h){const el=$('#aqst-nav-map');if(!el)return;h=((Number(h)||0)%360+360)%360;el.classList.add('aqst-final-heading-up');el.style.setProperty('--aqst-final-rotation',`${-h}deg`)}
async function aqFinalAcquireWakeLock(){
 if(!ST.nav.active||document.visibilityState!=='visible'||!navigator.wakeLock?.request)return false;
 try{if(ST.nav.wake&&!ST.nav.wake.released)return true;const lock=await navigator.wakeLock.request('screen');ST.nav.wake=lock;lock.addEventListener?.('release',()=>{if(ST.nav.wake===lock)ST.nav.wake=null;if(!ST.nav.wakeReleaseRequested&&ST.nav.active&&document.visibilityState==='visible')setTimeout(aqFinalAcquireWakeLock,350)});return true}catch(e){console.warn('Aqua wake lock unavailable',e);return false}
}
function aqFinalInstallWakeGuards(){if(ST.nav.finalWakeGuards)return;ST.nav.finalWakeGuards=true;document.addEventListener('visibilitychange',()=>{if(ST.nav.active&&document.visibilityState==='visible')setTimeout(aqFinalAcquireWakeLock,180)});setInterval(()=>{if(ST.nav.active&&document.visibilityState==='visible'&&(!ST.nav.wake||ST.nav.wake.released))aqFinalAcquireWakeLock()},15000)}
async function aqFinalReleaseWakeLock(){const lock=ST.nav.wake;ST.nav.wake=null;ST.nav.wakeReleaseRequested=true;try{await lock?.release?.()}catch{}finally{ST.nav.wakeReleaseRequested=false}}
function aqFinalLoadNavAsset(kind,url,id){return new Promise((resolve,reject)=>{let el=document.getElementById(id);if(el){if(kind==='css'||el.dataset.loaded==='1')return resolve(el);el.addEventListener('load',()=>resolve(el),{once:true});el.addEventListener('error',()=>reject(Error('بارگذاری نقشه نشان انجام نشد')),{once:true});return}el=document.createElement(kind==='css'?'link':'script');el.id=id;if(kind==='css'){el.rel='stylesheet';el.href=url;document.head.appendChild(el);return resolve(el)}el.src=url;el.async=true;el.onload=()=>{el.dataset.loaded='1';resolve(el)};el.onerror=()=>reject(Error('SDK سازگار نشان بارگذاری نشد'));document.head.appendChild(el)})}
async function aqFinalNeshanLeafletSdk(){if(ST.nav.finalNeshanLeaflet)return ST.nav.finalNeshanLeaflet;const cfg=await api('/api/map/neshan/web-config');if(!cfg?.configured||!cfg.web_key)throw Error('کلید وب نشان تنظیم نشده');const baseL=window.L;await aqFinalLoadNavAsset('css','https://static.neshan.org/sdk/leaflet/1.4.0/leaflet.css','aqst-final-neshan-leaflet-css');try{await aqFinalLoadNavAsset('js','https://static.neshan.org/sdk/leaflet/1.4.0/leaflet.js','aqst-final-neshan-leaflet-js');const NL=window.L;if(!NL?.Map)throw Error('SDK سازگار نشان آماده نشد');ST.nav.finalNeshanLeaflet={L:NL,key:cfg.web_key};return ST.nav.finalNeshanLeaflet}finally{if(baseL)window.L=baseL}}
async function aqFinalInitNeshanLeaflet(route,pos,target){const sdk=await aqFinalNeshanLeafletSdk(),NL=sdk.L;const map=new NL.Map('aqst-nav-map',{key:sdk.key,maptype:'neshan',poi:true,traffic:true,center:[pos.lat,pos.lng],zoom:17,zoomControl:false,attributionControl:false});ST.nav.map=map;ST.nav.mapKind='neshan-leaflet';ST.nav.navL=NL;ST.nav.casing=NL.polyline(route.points,{color:'#2b123f',weight:13,opacity:.9,lineCap:'round',lineJoin:'round',className:'aqst-route-shadow'}).addTo(map);ST.nav.line=NL.polyline(route.points,{color:'#8b2cff',weight:8,opacity:1,lineCap:'round',lineJoin:'round',className:'aqst-route-main'}).addTo(map);const icon=NL.divIcon({className:'aqst-nav-user',html:'<span id="aqst-nav-arrow">▲</span>',iconSize:[54,54],iconAnchor:[27,27]});ST.nav.marker=NL.marker([pos.lat,pos.lng],{icon,zIndexOffset:1500}).addTo(map);ST.nav.destMarker=NL.circleMarker([target.lat,target.lng],{radius:10,color:'#fff',weight:3,fillColor:'#8b2cff',fillOpacity:1}).addTo(map);ST.nav.markerVisual={lat:pos.lat,lng:pos.lng};setTimeout(()=>map.invalidateSize?.(),100)}
function aqFinalCompactMapUi(){
 const map=document.getElementById('mainMap');if(!map)return;const root=map.closest('[x-show]')||map.closest('section')||document;const all=[...root.querySelectorAll('button')];const label=b=>String(b.textContent||b.getAttribute('aria-label')||'').replace(/\u200c/g,' ').replace(/\s+/g,' ').trim();
 const near=all.find(b=>label(b).includes('اطراف من')),opt=all.find(b=>label(b).includes('بهینه سازی مسیر'));let mine=all.find(b=>label(b).includes('موقعیت من'));const locate=document.getElementById('aqst-locate');if(!mine&&locate){mine=locate;if(!mine.querySelector('span'))mine.innerHTML='⌖ <span>موقعیت من</span>'}else if(mine&&locate&&mine!==locate)locate.hidden=true;
 if(mine&&near&&opt){let row=root.querySelector('.aq-map-compact-actions');if(!row){row=document.createElement('div');row.className='aq-map-compact-actions';const frame=map.closest('.aq-map-frame')||map;frame.parentNode?.insertBefore(row,frame)}[mine,near,opt].forEach(b=>{if(b.parentElement!==row)row.appendChild(b)});[...root.querySelectorAll('.aqst-route-pair')].forEach(x=>{if(!x.children.length)x.remove()})}
 document.getElementById('aq-smart-tour')?.classList.add('aq-map-ui-compact')
}
function aqFinalBindCompactUi(){aqFinalCompactMapUi();setTimeout(aqFinalCompactMapUi,250);setTimeout(aqFinalCompactMapUi,900);if(!window.__aquaFinalMapUiObserver){window.__aquaFinalMapUiObserver=new MutationObserver(aqFinalCompactMapUi);window.__aquaFinalMapUiObserver.observe(document.documentElement,{subtree:true,childList:true})}}
'''.strip()


_INIT_NAV = r'''async function initNavMap(route,pos,target){try{ST.nav.map?.remove?.()}catch{}ST.nav.map=null;ST.nav.mapKind=null;ST.nav.marker=null;ST.nav.destMarker=null;ST.nav.navL=null;ST.nav.markerVisual=null;const container=$('#aqst-nav-map');if(container){container.classList.remove('aqst-final-heading-up');container.style.removeProperty('--aqst-final-rotation');container.innerHTML=''}try{const sdk=await neshanSdk();await initNeshanGlMap(sdk,route,pos,target);ST.nav.markerVisual={lat:pos.lat,lng:pos.lng};$('#aqst-drive-mode').textContent='نقشه نشان • جهت حرکت • ترافیک'}catch(glError){console.warn('Aqua Neshan GL fallback',glError);try{await aqFinalInitNeshanLeaflet(route,pos,target);$('#aqst-drive-mode').textContent='نقشه نشان • حالت سازگار آیفون'}catch(leafError){console.warn('Aqua Neshan Leaflet fallback',leafError);initLeafletNavMap(route,pos,target);ST.nav.markerVisual={lat:pos.lat,lng:pos.lng};$('#aqst-drive-mode').textContent='حالت پشتیبان'}}}'''

_INIT_OSM = r'''function initLeafletNavMap(route,pos,target){ST.nav.map=L.map('aqst-nav-map',{zoomControl:false,attributionControl:false,preferCanvas:true}).setView([pos.lat,pos.lng],17);ST.nav.mapKind='leaflet';ST.nav.navL=L;L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(ST.nav.map);ST.nav.casing=L.polyline(route.points,{color:'#2b123f',weight:13,opacity:.9,lineCap:'round',lineJoin:'round',className:'aqst-route-shadow'}).addTo(ST.nav.map);ST.nav.line=L.polyline(route.points,{color:'#8b2cff',weight:8,opacity:1,lineCap:'round',lineJoin:'round',className:'aqst-route-main'}).addTo(ST.nav.map);const icon=L.divIcon({className:'aqst-nav-user',html:'<span id="aqst-nav-arrow">▲</span>',iconSize:[54,54],iconAnchor:[27,27]});ST.nav.marker=L.marker([pos.lat,pos.lng],{icon,zIndexOffset:1500}).addTo(ST.nav.map);ST.nav.destMarker=L.circleMarker([target.lat,target.lng],{radius:10,color:'#fff',weight:3,fillColor:'#8b2cff',fillOpacity:1}).addTo(ST.nav.map);ST.nav.markerVisual={lat:pos.lat,lng:pos.lng};setTimeout(()=>ST.nav.map.invalidateSize(),80)}'''

_SET_FOLLOW = r'''function setFollowMode(on){ST.nav.follow=!!on;const b=$('#aqst-recenter');if(b)b.hidden=!!on;if(!on)aqFinalResetHeading();if(on&&ST.nav.active&&ST.nav.lastPos)updateDriveCamera(ST.nav.lastPos,ST.nav.lastCoords||{},ST.nav.lastNear||nearestPointInfo(ST.nav.lastPos,ST.nav.route?.points||[]),true)}'''

_CAMERA = r'''function updateDriveCamera(pos,coords,near,immediate=false){if(!ST.nav.follow||!ST.nav.map)return;const route=ST.nav.route,proj=aqFinalProject(pos,route),matched=proj.d<=135?{lat:proj.lat,lng:proj.lng}:pos,idx=proj.i,rem=remainingDistance(route,{...(near||{}),i:idx}),rb=routeBearing(route,idx);let h=Number(coords?.heading),speed=Number(coords?.speed);if(!Number.isFinite(h)||h<0||!Number.isFinite(speed)||speed<1.2)h=rb;h=aqFinalSmoothHeading(h);if(ST.nav.mapKind==='gl'){aqFinalResetHeading();try{ST.nav.map.easeTo({center:[matched.lng,matched.lat],bearing:h,pitch:rem<180?49:56,zoom:rem<220?18.8:18.35,duration:immediate?0:840,essential:true})}catch{}}else try{const zoom=rem<300?18:17;if(typeof ST.nav.map.setBearing==='function'){aqFinalResetHeading();ST.nav.map.setBearing(h)}else aqFinalApplyHeading(h);if(immediate)ST.nav.map.setView([matched.lat,matched.lng],zoom,{animate:false});else if(ST.nav.map.panTo){if(ST.nav.map.getZoom?.()!==zoom)ST.nav.map.setZoom?.(zoom,{animate:true});ST.nav.map.panTo([matched.lat,matched.lng],{animate:true,duration:.82,easeLinearity:.2,noMoveStart:true})}else ST.nav.map.setView([matched.lat,matched.lng],zoom,{animate:true});$('#aqst-nav-arrow')?.style.setProperty('transform',typeof ST.nav.map.setBearing==='function'?'rotate(0deg)':`rotate(${h}deg)`)}catch{}}'''

_OVERVIEW = r'''function showRouteOverview(){const pts=ST.nav.route?.points||[];if(!pts.length||!ST.nav.map)return;setFollowMode(false);aqFinalResetHeading();if(ST.nav.mapKind==='gl'){try{const gl=window.nmp_mapboxgl,b=new gl.LngLatBounds();pts.forEach(p=>b.extend([p[1],p[0]]));ST.nav.map.fitBounds(b,{padding:{top:70,bottom:120,left:38,right:38},pitch:12,bearing:0,duration:650})}catch{}}else try{ST.nav.map.fitBounds(pts,{padding:[42,42]})}catch{}}'''

_UPDATE_TOP = r'''function updateTopInstruction(info,rem,seconds){const step=info.step,target=ST.nav.target||{},distance=Number(info.distance||0);$('#aqst-maneuver-icon').textContent=navIcon(step);$('#aqst-maneuver-distance').textContent=step?.type==='arrive'?'مقصد':roundVoiceDistance(distance);$('#aqst-turn').textContent=step?.instruction||`در مسیر ${target.name||'مقصد'} ادامه بده`;$('#aqst-turnsub').textContent=step?.name||target.name||'';const next=$('#aqst-next-strip');if(next)next.hidden=true;$('#aqst-remain').textContent=fmtKm(rem);$('#aqst-nav-eta').textContent=fmtDur(seconds);$('#aqst-arrival').textContent=arrivalClock(seconds)}'''

_UPDATE_POS = r'''function updateNavPosition(pos,coords={},initial=false){if(!ST.nav.active)return;const route=ST.nav.route,pts=route?.points||[];if(!pts.length)return;const proj=aqFinalProject(pos,route),near={d:proj.d,i:proj.i},rem=remainingDistance(route,near),total=Math.max(1,Number(route.distance_m||route._total||rem)),seconds=Math.max(0,Math.round(Number(route.duration_s||0)*Math.min(1,rem/total)));ST.nav.lastPos=pos;ST.nav.lastCoords=coords||{};ST.nav.lastNear=near;const info=findNextStep(route,near);ST.nav.stepIndex=info.index;updateTopInstruction(info,rem,seconds);if(!initial)maybeAnnounceManeuver(info);const rawAcc=Number(coords?.accuracy),acc=Number.isFinite(rawAcc)&&rawAcc>0?Math.min(70,rawAcc):18,snapThreshold=Math.max(95,Math.min(145,acc*1.7+45)),visible=proj.d<=snapThreshold?{lat:proj.lat,lng:proj.lng,_route_i:proj.i,_snap_d:proj.d}:pos;ST.nav.lastMatched=visible;aqFinalAnimateMarker(visible,initial);if(typeof aqSyncMainNavMini==='function')aqSyncMainNavMini(visible);ST.nav.prevPos=pos;updateDriveCamera(pos,coords,near,initial);const td=hav([pos.lat,pos.lng],[ST.nav.target.lat,ST.nav.target.lng]);if(td<32){$('#aqst-maneuver-icon').textContent='●';$('#aqst-maneuver-distance').textContent='رسیدی';$('#aqst-turn').textContent='به مقصد رسیدی';$('#aqst-turnsub').textContent=ST.nav.target.name||'';$('#aqst-remain').textContent='۰ متر';$('#aqst-nav-eta').textContent='۰ دقیقه';$('#aqst-arrival').textContent=arrivalClock(0);if(!ST.nav.arrived){ST.nav.arrived=true;ariaSpeak(`به مقصد ${ST.nav.target.name||''} رسیدی`,{replace:true})}return}const offThreshold=Math.max(75,Math.min(170,acc*2.25+35));ST.nav.lastOffDistance=near.d;ST.nav.offThreshold=offThreshold;if(near.d>offThreshold)ST.nav.offCount=(ST.nav.offCount||0)+1;else if(near.d<offThreshold*.62)ST.nav.offCount=0;else ST.nav.offCount=Math.max(0,(ST.nav.offCount||0)-1);if(ST.nav.offCount>=4&&Date.now()-ST.nav.lastReroute>40000){ST.nav.offCount=0;ST.nav.lastReroute=Date.now();reroute(pos)}}'''

_ON_POS = r'''async function onNavPosition(p){if(!ST.nav.active)return;updateNavPosition({lat:p.coords.latitude,lng:p.coords.longitude},{heading:p.coords.heading,speed:p.coords.speed,accuracy:p.coords.accuracy},false)}'''

_LONG_PRESS = r'''function bindMainMapLongPress(){const el=$('#mainMap'),m=mainMap();if(!el||!m||el.dataset.aqFinalLongPress==='1')return;el.dataset.aqFinalLongPress='1';let timer=null,start=null,last=null,moved=false;const clear=()=>{if(timer){clearTimeout(timer);timer=null}};const fire=(x,y)=>{const rect=el.getBoundingClientRect();try{const ll=m.containerPointToLatLng([x-rect.left,y-rect.top]);navigator.vibrate?.(30);selectFreeDestination({lat:Number(ll.lat),lng:Number(ll.lng),name:'مقصد انتخابی روی نقشه',address:'',source:'hold'});setTimeout(()=>$('#aqst-free-card')?.classList.add('aqst-picked-visible'),30)}catch(e){console.warn('Aqua long press destination failed',e)}};el.addEventListener('touchstart',e=>{if(e.touches.length!==1)return;const t=e.touches[0];start={x:t.clientX,y:t.clientY};last=start;moved=false;clear();timer=setTimeout(()=>{timer=null;if(!moved&&last)fire(last.x,last.y)},680)},{passive:true});el.addEventListener('touchmove',e=>{if(!start||!e.touches.length)return;const t=e.touches[0];last={x:t.clientX,y:t.clientY};if(Math.hypot(last.x-start.x,last.y-start.y)>14){moved=true;clear()}},{passive:true});['touchend','touchcancel'].forEach(n=>el.addEventListener(n,()=>{clear();start=null;last=null;moved=false},{passive:true}));let pstart=null,ptimer=null;const pclear=()=>{if(ptimer){clearTimeout(ptimer);ptimer=null}};el.addEventListener('pointerdown',e=>{if(e.pointerType==='touch'||(e.button!=null&&e.button!==0))return;pstart={x:e.clientX,y:e.clientY};pclear();ptimer=setTimeout(()=>{ptimer=null;if(pstart)fire(pstart.x,pstart.y)},680)},{passive:true});el.addEventListener('pointermove',e=>{if(!pstart)return;if(Math.hypot(e.clientX-pstart.x,e.clientY-pstart.y)>14){pclear();pstart=null}},{passive:true});['pointerup','pointercancel','pointerleave'].forEach(n=>el.addEventListener(n,()=>{pclear();pstart=null},{passive:true}))}'''

_FINAL_BOOT = r'''
aqFinalInstallWakeGuards();aqFinalBindCompactUi();
'''.strip()

_CSS = r'''
/* Aqua final Map/Navigation guard — PR29 20260909 */
#aq-smart-tour.aq-map-ui-compact{margin-bottom:6px!important}
#aq-smart-tour.aq-map-ui-compact .aqst-search{margin:0 0 6px!important}
#aq-smart-tour.aq-map-ui-compact .aqst-searchbar{grid-template-columns:minmax(0,1fr) auto!important;gap:6px!important}
#aq-smart-tour.aq-map-ui-compact .aqst-searchbar input{height:40px!important;min-height:40px!important;padding:7px 11px!important;border-radius:12px!important;font-size:.82rem!important;line-height:1.2!important}
#aq-smart-tour.aq-map-ui-compact .aqst-iconbtn{width:40px!important;height:40px!important;min-width:40px!important;border-radius:12px!important;font-size:.9rem!important}
#aq-smart-tour.aq-map-ui-compact .aqst-iconbtn span{font-size:.7rem!important;margin-inline-start:2px!important}
#aq-smart-tour.aq-map-ui-compact .aqst-results{top:46px!important;max-height:240px!important}
#aq-smart-tour.aq-map-ui-compact .aqst-selected{margin-top:6px!important;padding:8px 10px!important;border-radius:13px!important;min-height:0!important}
#aq-smart-tour.aq-map-ui-compact .aqst-selected b{font-size:.82rem!important}#aq-smart-tour.aq-map-ui-compact .aqst-selected small{font-size:.7rem!important}
.aq-map-compact-actions{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:6px!important;margin:6px 0 8px!important;width:100%!important;align-items:stretch!important}
.aq-map-compact-actions>button{width:100%!important;min-width:0!important;max-width:none!important;height:38px!important;min-height:38px!important;padding:0 5px!important;margin:0!important;border-radius:12px!important;font-size:.7rem!important;line-height:1!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;display:flex!important;align-items:center!important;justify-content:center!important;gap:3px!important}
#aqst-free-search{margin:6px 0!important}.aqst-free-searchbar{gap:6px!important}.aqst-free-searchbar input{height:40px!important;min-height:40px!important;padding:7px 10px!important;border-radius:12px!important;font-size:.82rem!important}.aqst-free-searchbar button{height:40px!important;min-height:40px!important;padding:0 11px!important;border-radius:12px!important;font-size:.75rem!important}.aqst-free-hint{padding:5px 2px!important;font-size:.68rem!important;line-height:1.45!important}
#mainMap{touch-action:pan-x pan-y pinch-zoom}
#aqst-free-card:not([hidden]){animation:aqstFinalPickPop .18s ease-out}@keyframes aqstFinalPickPop{from{transform:translateY(8px) scale(.985);opacity:.35}to{transform:none;opacity:1}}
#aqst-nav{background:#e9ece8!important;grid-template-rows:auto 1fr auto!important}
#aqst-nav .aqst-next-strip{display:none!important}
#aqst-nav .aqst-navhead{position:relative!important;margin:7px 7px 0!important;min-height:118px!important;padding:13px 12px!important;border-radius:22px!important;background:#070809!important;border:0!important;box-shadow:0 10px 28px rgba(0,0,0,.28)!important;grid-template-columns:58px minmax(0,1fr)!important;gap:10px!important;direction:ltr!important;z-index:2147481850!important}
#aqst-nav .aqst-maneuver-icon{width:56px!important;height:56px!important;border-radius:16px!important;background:transparent!important;color:#fff!important;font-size:2.65rem!important;box-shadow:none!important;align-self:start!important}
#aqst-nav .aqst-maneuver-copy{direction:rtl!important;text-align:right!important;padding-top:1px!important;min-width:0!important}
#aqst-nav .aqst-maneuver-distance{font-size:.92rem!important;color:#fff!important;font-weight:950!important;margin-bottom:4px!important}
#aqst-nav .aqst-turn{font-size:1.14rem!important;line-height:1.38!important;color:#75d8ff!important;font-weight:950!important}
#aqst-nav .aqst-turnsub{font-size:.78rem!important;color:#adb5ba!important;margin-top:4px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
#aqst-nav .aqst-navtools{position:absolute!important;right:10px!important;top:calc(100% + 16px)!important;z-index:2147481870!important;display:grid!important;gap:9px!important}
#aqst-nav .aqst-navtools button,#aqst-map-actions button{width:46px!important;height:46px!important;border-radius:50%!important;background:rgba(255,255,255,.95)!important;color:#111!important;border:1px solid rgba(0,0,0,.07)!important;box-shadow:0 5px 15px rgba(0,0,0,.16)!important;font-size:1.15rem!important}
#aqst-map-actions{left:10px!important;top:12px!important;gap:9px!important}
#aqst-nav .aqst-navmap{margin-top:0!important;overflow:hidden!important;isolation:isolate!important;background:#e7ebe7!important;min-height:0!important}
#aqst-nav #aqst-nav-map{z-index:1!important;transform-origin:50% 50%!important;background:#e7ebe7!important}
#aqst-nav #aqst-nav-map.aqst-final-heading-up{transform:rotate(var(--aqst-final-rotation,0deg)) scale(1.5)!important;transition:transform .45s linear!important;will-change:transform!important}
#aqst-nav .aqst-drive-mode{display:none!important}
#aqst-nav .aqst-nav-user,#aqst-nav .aqst-gl-user{background:transparent!important;border:0!important;filter:drop-shadow(0 9px 7px rgba(41,0,80,.42)) drop-shadow(0 2px 2px rgba(255,255,255,.72))!important}
#aqst-nav .aqst-nav-user span,#aqst-nav .aqst-gl-user span{width:54px!important;height:54px!important;display:grid!important;place-items:center!important;color:#8b2cff!important;font-size:2.5rem!important;text-shadow:-3px -3px 0 #fff,3px -3px 0 #fff,-3px 3px 0 #fff,3px 3px 0 #fff,0 5px 0 #4b0d91,0 9px 13px rgba(48,0,94,.58)!important;transform-origin:50% 50%!important;transition:transform .45s linear!important}
#aqst-nav .leaflet-overlay-pane svg path.aqst-route-shadow{filter:drop-shadow(0 5px 5px rgba(48,0,83,.42))!important}
#aqst-nav .leaflet-overlay-pane svg path.aqst-route-main{filter:drop-shadow(0 3px 3px rgba(89,20,157,.52))!important}
#aqst-nav .leaflet-marker-pane .leaflet-marker-icon{will-change:transform!important}
#aqst-nav #aqst-recenter{position:absolute!important;z-index:2147481880!important;left:10px!important;bottom:12px!important;pointer-events:auto!important;border:0!important;border-radius:999px!important;background:rgba(255,255,255,.96)!important;color:#151515!important;box-shadow:0 5px 18px rgba(0,0,0,.18)!important;min-height:44px!important;padding:0 14px!important}
#aqst-nav #aqst-recenter[hidden]{display:none!important}
#aqst-nav .aqst-navfoot{grid-template-columns:repeat(3,1fr)!important;gap:0!important;padding:10px 10px max(12px,env(safe-area-inset-bottom))!important;background:#fff!important;color:#111!important;border:0!important;border-radius:22px 22px 0 0!important;box-shadow:0 -8px 24px rgba(0,0,0,.12)!important;z-index:2147481900!important;min-height:72px!important}
#aqst-nav .aqst-navmetric{padding:4px!important;border-left:1px solid #e5e5e5!important;color:#111!important}.aqst-navmetric:nth-child(3){border-left:0!important}
#aqst-nav .aqst-navmetric b{font-size:.98rem!important;color:#111!important;font-weight:950!important}.aqst-navmetric small{font-size:.65rem!important;color:#666!important}
#aqst-nav .aqst-stop{position:fixed!important;z-index:2147481950!important;left:10px!important;top:calc(env(safe-area-inset-top) + 10px)!important;width:42px!important;height:42px!important;min-width:42px!important;padding:0!important;margin:0!important;border-radius:50%!important;font-size:0!important;background:#d92c43!important;box-shadow:0 7px 18px rgba(160,0,25,.35)!important}.aqst-stop::after{content:'×';font-size:1.65rem;line-height:1;color:#fff;font-weight:700}
@media(max-width:700px){
 .aq-map-compact-actions{gap:5px!important}.aq-map-compact-actions>button{height:36px!important;min-height:36px!important;font-size:.66rem!important;padding:0 3px!important;border-radius:11px!important}
 #aqst-free-card:not([hidden]){position:fixed!important;left:12px!important;right:12px!important;bottom:calc(94px + env(safe-area-inset-bottom,0px))!important;z-index:2147481600!important;margin:0!important;padding:11px!important;border-radius:17px!important;background:rgba(6,22,38,.97)!important;border:1px solid rgba(139,44,255,.42)!important;box-shadow:0 14px 34px rgba(0,0,0,.42)!important;backdrop-filter:blur(14px)!important}
 #aqst-free-card .aqst-free-card-copy b{display:block!important;font-size:.9rem!important;color:#fff!important}#aqst-free-card .aqst-free-card-copy small{display:block!important;margin-top:3px!important;color:#a9b5c7!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
 #aqst-free-card .aqst-free-card-actions{display:flex!important;gap:8px!important;margin-top:9px!important}#aqst-free-card .aqst-free-card-actions button{flex:1!important;min-height:42px!important;border-radius:12px!important;font-weight:900!important}.aqst-free-start{background:linear-gradient(135deg,#8b2cff,#5a16be)!important;color:#fff!important}.aqst-free-clear{background:#16324a!important;color:#e8f5ff!important}
}
@media(max-width:360px){.aq-map-compact-actions>button{font-size:.61rem!important;letter-spacing:-.01em!important}}
'''.strip()


def _replace_function(source: str, name: str, replacement: str) -> str:
    pattern = rf"(?:async\s+)?function\s+{re.escape(name)}\([^)]*\)\{{.*?(?=\n(?:async\s+)?function\s+[A-Za-z_$][\w$]*\()"
    return re.sub(pattern, replacement + "\n", source, count=1, flags=re.S)


@app_v3.app.after_request
def aqua_map_navigation_final_assets(response):
    try:
        if response.status_code != 200:
            return response
        if request.path == "/aqua-smart-tour.js":
            response.direct_passthrough = False
            source = response.get_data(as_text=True)
            marker = "function aqFinalProject(pos,route)"
            if marker not in source:
                anchor = "async function startNavigation(target)"
                idx = source.find(anchor)
                if idx < 0:
                    anchor = "function startNavigation(target)"
                    idx = source.find(anchor)
                if idx >= 0:
                    source = source[:idx] + _HELPERS + "\n" + source[idx:]
                source = _replace_function(source, "bindMainMapLongPress", _LONG_PRESS)
                source = _replace_function(source, "initNavMap", _INIT_NAV)
                source = _replace_function(source, "initLeafletNavMap", _INIT_OSM)
                source = _replace_function(source, "setFollowMode", _SET_FOLLOW)
                source = _replace_function(source, "updateDriveCamera", _CAMERA)
                source = _replace_function(source, "showRouteOverview", _OVERVIEW)
                source = _replace_function(source, "updateTopInstruction", _UPDATE_TOP)
                source = _replace_function(source, "updateNavPosition", _UPDATE_POS)
                source = _replace_function(source, "onNavPosition", _ON_POS)
                source = source.replace("try{ST.nav.wake=await navigator.wakeLock?.request?.('screen')}catch{}", "aqFinalInstallWakeGuards();await aqFinalAcquireWakeLock();")
                source = source.replace("try{await ST.nav.wake?.release?.()}catch{}ST.nav.wake=null;", "await aqFinalReleaseWakeLock();")
                source = source.replace("'line-color':'#16c7f4','line-width':7,'line-opacity':1", "'line-color':'#8b2cff','line-width':8,'line-opacity':1,'line-blur':.15")
                source = source.replace("'line-color':'#f4fbff','line-width':12,'line-opacity':.92", "'line-color':'#2b123f','line-width':14,'line-opacity':.84,'line-blur':2.6")
                source = source.replace("'line-color':'#7b24d6'", "'line-color':'#8b2cff'")
                source = source.replace("'line-color':'#2a1738'", "'line-color':'#2b123f'")
                boot_anchor = "\nfunction enhance(){"
                if boot_anchor in source:
                    source = source.replace(boot_anchor, "\n" + _FINAL_BOOT + boot_anchor, 1)
                else:
                    source += "\n" + _FINAL_BOOT + "\n"
                source = source.replace("async async function", "async function")
                source = source.replace("await aqFinalAcquireWakeLock()const", "await aqFinalAcquireWakeLock();const")
                response.set_data(source)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            marker = "Aqua final Map/Navigation guard — PR29 20260909"
            if marker not in css:
                css += "\n" + _CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_map_navigation_final_failed: %s", str(exc)[:180])
    return response
