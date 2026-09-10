# Final scoped iPhone stability/layout patch for the AquaGold Map preview.
from __future__ import annotations

import re

from flask import request

import app_v3


_MAIN_MAP_SINGLE_ENGINE = r'''async function aqSetupMainNeshan(){
 const host=$('.aq-map-frame'),bg=$('#aqst-main-neshan-bg');
 try{ST.nav.mainNeshan?.remove?.()}catch{}
 ST.nav.mainNeshan=null;
 if(bg)bg.remove();
 host?.classList.remove('aqst-main-neshan-ready');
}'''

_INVALIDATE = r'''let aqNormalMapInvalidateFrame=0;
function aqInvalidateNormalMap(){
 if(!isMapPageVisible())return;
 if(aqNormalMapInvalidateFrame)cancelAnimationFrame(aqNormalMapInvalidateFrame);
 aqNormalMapInvalidateFrame=requestAnimationFrame(()=>{
  aqNormalMapInvalidateFrame=0;
  try{mainMap()?.invalidateSize?.({pan:false})}catch{}
 });
}'''

_LIGHT_OBSERVER = r'''const aqMapSection=$('#mainMap')?.closest('section');
const obs=aqMapSection?new MutationObserver(()=>{if(isMapPageVisible())enhance()}):null;
if(obs)obs.observe(aqMapSection,{attributes:true,attributeFilter:['style','class','hidden']});'''

_CSS = r'''
/* Aqua Map final iPhone stability/layout patch */
html body .topbar{z-index:90!important}
html body section[x-show*="page==='map'"] #aqst-map-tools-drawer{
  position:relative!important;
  z-index:20!important;
  margin-top:0!important;
  isolation:isolate;
}
html body section[x-show*="page==='map'"] .aq-map-frame{
  transform:none!important;
  contain:layout paint;
  overflow:hidden!important;
}
html body section[x-show*="page==='map'"] .aq-map-frame:before,
html body section[x-show*="page==='map'"] .aq-map-frame:after{
  animation:none!important;
}
html body section[x-show*="page==='map'"] #aqst-main-neshan-bg{display:none!important}
html body section[x-show*="page==='map'"] .aq-map-frame.aqst-main-neshan-ready #mainMap .leaflet-tile-pane{
  opacity:1!important;
}
html body section[x-show*="page==='map'"] .aq-map-frame #mainMap{
  background:#e5e7eb!important;
  transform:none!important;
}
html body section[x-show*="page==='map'"] .leaflet-map-pane,
html body section[x-show*="page==='map'"] .leaflet-marker-pane,
html body section[x-show*="page==='map'"] .leaflet-overlay-pane{
  will-change:transform;
}
html body section[x-show*="page==='map'"] #aqst-map-workspace{z-index:30!important}
html body section[x-show*="page==='map'"] .aqst-map-float-stack{z-index:44!important}
html body section[x-show*="page==='map'"] #aqst-controls{z-index:42!important}
html body section[x-show*="page==='map'"] .aqst-map-sheet{
  z-index:50!important;
  max-width:calc(100% - 14px)!important;
  width:auto!important;
  box-sizing:border-box!important;
  overflow-x:hidden!important;
  overscroll-behavior:contain;
}
html body section[x-show*="page==='map'"] .aqst-special-editor form,
html body section[x-show*="page==='map'"] .aqst-special-emojis{
  min-width:0!important;
  max-width:100%!important;
  overflow:hidden!important;
}
html body section[x-show*="page==='map'"] #aqst-special-emoji-options{
  display:grid!important;
  grid-template-columns:repeat(6,minmax(0,1fr))!important;
  gap:6px!important;
  width:100%!important;
  max-width:100%!important;
  overflow:visible!important;
  padding:2px 0 5px!important;
}
html body section[x-show*="page==='map'"] .aqst-special-emoji-option{
  width:100%!important;
  min-width:0!important;
  max-width:none!important;
  height:40px!important;
  flex:none!important;
}
html body section[x-show*="page==='map'"] .aqst-legend{
  display:grid!important;
  grid-template-columns:1fr!important;
  align-items:start!important;
  gap:5px!important;
  padding:8px 2px 4px!important;
}
html body section[x-show*="page==='map'"] .aqst-legend>span{
  width:100%!important;
  display:flex!important;
  justify-content:flex-start!important;
  white-space:normal!important;
  line-height:1.65!important;
}
html body section[x-show*="page==='map'"] .aqst-free-hint{
  display:block!important;
  width:100%!important;
  line-height:1.8!important;
}
html body section[x-show*="page==='map'"] .leaflet-control-attribution{
  max-width:min(84vw,320px)!important;
  white-space:normal!important;
  line-height:1.45!important;
  text-align:left!important;
}
html.aqst-nav-fullscreen #aqst-nav .mapboxgl-ctrl-top-left,
html.aqst-nav-fullscreen #aqst-nav .mapboxgl-ctrl-top-right{
  top:calc(var(--aqst-head-bottom,112px) + 8px)!important;
}
html.aqst-nav-fullscreen #aqst-nav .mapboxgl-ctrl-bottom-left,
html.aqst-nav-fullscreen #aqst-nav .mapboxgl-ctrl-bottom-right{
  bottom:calc(var(--aqst-foot-clear,150px) + 6px)!important;
}
html.aqst-nav-fullscreen #aqst-nav .mapboxgl-ctrl-attrib{
  max-width:min(78vw,340px)!important;
}
html.aqst-nav-fullscreen #aqst-nav .mapboxgl-ctrl-attrib-inner{
  display:grid!important;
  gap:2px!important;
  line-height:1.35!important;
}
html.aqst-nav-fullscreen #aqst-nav .mapboxgl-ctrl-attrib-inner>a{
  display:block!important;
}
html.aqst-nav-fullscreen #aqst-nav #aqst-map-actions{z-index:75!important}
html.aqst-nav-fullscreen #aqst-nav .aqst-drive-mode,
html.aqst-nav-fullscreen #aqst-nav .aqst-recenter{z-index:70!important}
@media(max-width:700px){
  html body section[x-show*="page==='map'"] #aqst-special-emoji-options{
    grid-template-columns:repeat(4,minmax(0,1fr))!important;
  }
  html body section[x-show*="page==='map'"] .aqst-map-sheet{
    right:7px!important;
    left:7px!important;
    max-width:none!important;
  }
  html body section[x-show*="page==='map'"] #aqst-map-tools-drawer{
    scroll-margin-top:calc(env(safe-area-inset-top) + 74px);
  }
}
'''.strip()


def _patch_js(source: str) -> str:
    if "Aqua Map final iPhone stability patch" in source:
        return source

    source = re.sub(
        r"async function aqSetupMainNeshan\(\)\{.*?\n\}\n(?=function aqSetupPolish\(\))",
        _MAIN_MAP_SINGLE_ENGINE + "\n",
        source,
        count=1,
        flags=re.S,
    )

    source = source.replace(
        "setTimeout(aqTidyMapToolbar,300);setTimeout(aqTidyMapToolbar,1100);setTimeout(aqSetupMainNeshan,700);setTimeout(aqSetupMainNeshan,1800)",
        "setTimeout(aqTidyMapToolbar,300);setTimeout(aqTidyMapToolbar,1100)",
    )

    source = re.sub(
        r"const aqPolishObserver=new MutationObserver\(\(\)=>\{aqTidyMapToolbar\(\);if\(\$\('#mainMap'\)\)aqSetupMainNeshan\(\)\}\);\s*aqPolishObserver\.observe\(document\.documentElement,\{subtree:true,childList:true\}\);",
        "/* stability: global subtree observer removed; map-ready/section visibility own updates */",
        source,
        count=1,
    )

    source = re.sub(
        r"function aqInvalidateNormalMap\(\)\{.*?\}\n(?=function aqSetMapToolsDrawer\()",
        _INVALIDATE + "\n",
        source,
        count=1,
        flags=re.S,
    )

    source = source.replace(
        "const obs=new MutationObserver(()=>enhance());obs.observe(document.documentElement,{childList:true,subtree:true});",
        _LIGHT_OBSERVER,
    )

    marker = "\n/* Aqua Map final iPhone stability patch */\n"
    end = source.rfind("})();")
    if end >= 0:
        source = source[:end] + marker + source[end:]
    return source


@app_v3.app.after_request
def aqua_map_stability_assets(response):
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
            marker = "/* Aqua Map final iPhone stability/layout patch */"
            if marker not in css:
                css += "\n" + _CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_map_stability_asset_failed: %s", str(exc)[:180])
    return response
