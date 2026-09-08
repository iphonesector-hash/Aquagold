"""Map-only iPhone navigation fallback polish.

When the Neshan GL map cannot stay active on iOS/Preview, Aqua falls back to
Leaflet. Leaflet is north-up by default, which makes the vehicle arrow appear
sideways while driving west/east. Keep that fallback useful by rotating the
visual map with the current route/device heading while follow mode is active.
Also keep both recenter/resume controls above map layers.

No Finance, Aria, Bale, Push, database or Production state is changed.
"""
from flask import request

import app_v3


_FALLBACK_JS = r'''
;(()=>{
 if(window.__aquaFallbackHeadingFix20260908)return;window.__aquaFallbackHeadingFix20260908=true;
 const $q=(s)=>document.querySelector(s);
 function fallbackHeading(pos,coords,near){
  try{
   const route=ST?.nav?.route;
   let h=Number(coords?.heading),speed=Number(coords?.speed);
   const i=Number(near?.i||0);
   const rb=typeof routeBearing==='function'?routeBearing(route,i):0;
   if(!Number.isFinite(h)||h<0||!Number.isFinite(speed)||speed<1.2)h=rb;
   if(typeof aqSmoothHeading==='function')h=aqSmoothHeading(h);
   return ((Number(h)||0)%360+360)%360;
  }catch{return 0}
 }
 function resetFallbackView(){
  const el=$q('#aqst-nav-map');if(!el)return;
  el.classList.remove('aqst-leaflet-heading-up');
  el.style.removeProperty('--aqst-fallback-rotation');
  el.style.removeProperty('transform');
 }
 function applyFallbackView(pos,coords,near){
  if(!ST?.nav?.active||!ST?.nav?.follow||ST?.nav?.mapKind!=='leaflet')return resetFallbackView();
  const el=$q('#aqst-nav-map');if(!el)return;
  const h=fallbackHeading(pos,coords,near);
  el.classList.add('aqst-leaflet-heading-up');
  el.style.setProperty('--aqst-fallback-rotation',`${-h}deg`);
 }
 const oldCamera=window.updateDriveCamera||updateDriveCamera;
 window.updateDriveCamera=updateDriveCamera=function(pos,coords,near,immediate=false){
  const out=oldCamera(pos,coords,near,immediate);
  try{requestAnimationFrame(()=>applyFallbackView(pos,coords,near))}catch{}
  return out;
 };
 const oldFollow=window.setFollowMode||setFollowMode;
 window.setFollowMode=setFollowMode=function(on){
  if(!on)resetFallbackView();
  const out=oldFollow(on);
  if(on&&ST?.nav?.lastPos)requestAnimationFrame(()=>applyFallbackView(ST.nav.lastPos,ST.nav.lastCoords||{},ST.nav.lastNear||{}));
  return out;
 };
 const oldStop=window.stopNavigation||stopNavigation;
 window.stopNavigation=stopNavigation=function(){resetFallbackView();return oldStop()};
 function liftControls(){
  const rec=$q('#aqst-recenter');if(rec){rec.style.zIndex='2147481800';rec.style.pointerEvents='auto'}
  const resume=$q('#aqst-nav-resume');if(resume){resume.style.zIndex='2147481800';resume.style.pointerEvents='auto'}
 }
 const mo=new MutationObserver(()=>liftControls());
 mo.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['hidden']});
 liftControls();setTimeout(liftControls,300);setTimeout(liftControls,1200);
})();
'''.strip()


_FALLBACK_CSS = r'''
/* Aqua iPhone fallback heading + navigation control layering — 20260908 */
#aqst-nav .aqst-navmap{overflow:hidden!important;isolation:isolate!important}
#aqst-nav #aqst-nav-map{z-index:1!important;transform-origin:50% 50%!important}
#aqst-nav #aqst-nav-map.aqst-leaflet-heading-up{transform:rotate(var(--aqst-fallback-rotation,0deg)) scale(1.43)!important;transition:transform .42s ease-out!important;will-change:transform!important}
#aqst-nav .aqst-drive-mode{z-index:2147481700!important;pointer-events:none!important}
#aqst-nav #aqst-recenter{position:absolute!important;z-index:2147481800!important;left:12px!important;bottom:14px!important;pointer-events:auto!important;display:block}
#aqst-nav #aqst-recenter[hidden]{display:none!important}
#aqst-nav-resume{position:fixed!important;z-index:2147481800!important;left:14px!important;bottom:calc(96px + env(safe-area-inset-bottom,0px))!important;pointer-events:auto!important}
#aqst-nav-resume[hidden]{display:none!important}
@media(max-width:700px){
 #aqst-nav #aqst-recenter{left:10px!important;bottom:12px!important;min-height:44px!important}
 #aqst-nav-resume{left:12px!important;bottom:calc(92px + env(safe-area-inset-bottom,0px))!important;min-height:44px!important}
}
'''.strip()


@app_v3.app.after_request
def aqua_navigation_fallback_heading_assets(response):
    try:
        if response.status_code != 200:
            return response
        if request.path == "/aqua-smart-tour.js":
            response.direct_passthrough = False
            source = response.get_data(as_text=True)
            if "__aquaFallbackHeadingFix20260908" not in source:
                source += "\n" + _FALLBACK_JS + "\n"
                response.set_data(source)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            if "Aqua iPhone fallback heading + navigation control layering — 20260908" not in css:
                css += "\n" + _FALLBACK_CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_fallback_heading_asset_failed: %s", str(exc)[:180])
    return response
