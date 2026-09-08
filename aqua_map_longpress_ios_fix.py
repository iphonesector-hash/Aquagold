"""iOS/Safari long-press destination picker for the Aqua map Preview.

Adds a touch-native long press fallback to the main map container so a user can
hold on the map, drop a destination pin, and immediately start navigation.
Map/Navigation only; no Finance, Aria, Bale, Push or database changes.
"""
from __future__ import annotations

from flask import request

import app_v3


_JS = r'''
;(()=>{
 if(window.__aquaIosLongPress20260908)return;window.__aquaIosLongPress20260908=true;
 function bind(){
  const el=document.getElementById('mainMap');if(!el||el.dataset.aqIosLong==='1')return;
  el.dataset.aqIosLong='1';let timer=null,start=null,last=null,moved=false;
  const clear=()=>{if(timer){clearTimeout(timer);timer=null}};
  const pointToLatLng=(x,y)=>{const m=mainMap?.();if(!m)return null;const r=el.getBoundingClientRect();try{return m.containerPointToLatLng([x-r.left,y-r.top])}catch{return null}};
  const fire=(x,y)=>{const ll=pointToLatLng(x,y);if(!ll)return;try{navigator.vibrate?.(30)}catch{};try{selectFreeDestination({lat:Number(ll.lat),lng:Number(ll.lng),name:'مقصد انتخابی روی نقشه',address:'',source:'hold'});setTimeout(()=>document.getElementById('aqst-free-card')?.classList.add('aqst-picked-visible'),30)}catch(e){console.warn('Aqua long press destination failed',e)}};
  el.addEventListener('touchstart',e=>{if(e.touches.length!==1)return;const t=e.touches[0];start={x:t.clientX,y:t.clientY};last=start;moved=false;clear();timer=setTimeout(()=>{timer=null;if(!moved&&last)fire(last.x,last.y)},680)},{passive:true});
  el.addEventListener('touchmove',e=>{if(!start||!e.touches.length)return;const t=e.touches[0];last={x:t.clientX,y:t.clientY};if(Math.hypot(last.x-start.x,last.y-start.y)>14){moved=true;clear()}},{passive:true});
  ['touchend','touchcancel'].forEach(n=>el.addEventListener(n,()=>{clear();start=null;last=null;moved=false},{passive:true}));
  // Pointer fallback for iPad pointer/mouse and browsers that support it reliably.
  let pstart=null,ptimer=null;
  const pclear=()=>{if(ptimer){clearTimeout(ptimer);ptimer=null}};
  el.addEventListener('pointerdown',e=>{if(e.pointerType==='touch'||(e.button!=null&&e.button!==0))return;pstart={x:e.clientX,y:e.clientY};pclear();ptimer=setTimeout(()=>{ptimer=null;if(pstart)fire(pstart.x,pstart.y)},680)},{passive:true});
  el.addEventListener('pointermove',e=>{if(!pstart)return;if(Math.hypot(e.clientX-pstart.x,e.clientY-pstart.y)>14){pclear();pstart=null}},{passive:true});
  ['pointerup','pointercancel','pointerleave'].forEach(n=>el.addEventListener(n,()=>{pclear();pstart=null},{passive:true}));
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind,{once:true});else bind();
 new MutationObserver(bind).observe(document.documentElement,{subtree:true,childList:true});
 setTimeout(bind,300);setTimeout(bind,1200);
})();
'''.strip()

_CSS = r'''
/* iOS destination long-press feedback */
#mainMap{touch-action:pan-x pan-y pinch-zoom}
#aqst-free-card:not([hidden]){animation:aqstPickPop .18s ease-out}
@keyframes aqstPickPop{from{transform:translateY(8px) scale(.985);opacity:.35}to{transform:none;opacity:1}}
@media(max-width:700px){
 #aqst-free-card:not([hidden]){position:fixed!important;left:12px!important;right:12px!important;bottom:calc(94px + env(safe-area-inset-bottom,0px))!important;z-index:2147481600!important;margin:0!important;padding:12px!important;border-radius:18px!important;background:rgba(6,22,38,.97)!important;border:1px solid rgba(92,214,255,.38)!important;box-shadow:0 14px 34px rgba(0,0,0,.42)!important;backdrop-filter:blur(14px)!important}
 #aqst-free-card .aqst-free-card-copy{min-width:0!important}
 #aqst-free-card .aqst-free-card-copy b{display:block!important;font-size:.95rem!important;color:#fff!important}
 #aqst-free-card .aqst-free-card-copy small{display:block!important;margin-top:3px!important;color:#9fb6c7!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
 #aqst-free-card .aqst-free-card-actions{display:flex!important;gap:8px!important;margin-top:10px!important}
 #aqst-free-card .aqst-free-card-actions button{flex:1!important;min-height:44px!important;border-radius:13px!important;font-weight:900!important}
 #aqst-free-card .aqst-free-start{background:linear-gradient(135deg,#16c9d5,#18b985)!important;color:#fff!important}
 #aqst-free-card .aqst-free-clear{background:#16324a!important;color:#e8f5ff!important}
}
'''.strip()


@app_v3.app.after_request
def aqua_map_longpress_ios_assets(response):
    try:
        if response.status_code != 200:
            return response
        if request.path == "/aqua-smart-tour.js":
            response.direct_passthrough = False
            src = response.get_data(as_text=True)
            marker = "window.__aquaIosLongPress20260908"
            if marker not in src:
                src += "\n" + _JS + "\n"
                response.set_data(src)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            marker = "iOS destination long-press feedback"
            if marker not in css:
                css += "\n" + _CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_map_longpress_ios_failed: %s", str(exc)[:180])
    return response
