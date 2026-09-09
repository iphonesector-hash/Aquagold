"""Branch-scoped Phase 4B fullscreen navigation sheets.

This presentation-only layer keeps routing, Neshan providers, Aria voice,
long-press, reroute logic, and Map search untouched. It turns the existing
navigation map into a true edge-to-edge canvas and makes the top instruction
and bottom metrics surfaces collapsible glass sheets for iPhone use.
"""
from flask import request

import app_v3


_PHASE4B_JS = r'''
function aqSyncPhase4BPanelInsets(){
 const nav=$('#aqst-nav');if(!nav||nav.hidden)return;
 const head=nav.querySelector('.aqst-navhead'),foot=nav.querySelector('.aqst-navfoot');
 if(head){const r=head.getBoundingClientRect();nav.style.setProperty('--aqst-head-bottom',`${Math.max(44,Math.ceil(r.bottom+6))}px`)}
 if(foot){const r=foot.getBoundingClientRect();nav.style.setProperty('--aqst-foot-clear',`${Math.max(44,Math.ceil(window.innerHeight-r.top+8))}px`)}
 try{ST.nav.mapKind==='gl'?ST.nav.map?.resize?.():ST.nav.map?.invalidateSize?.()}catch{}
}
function aqRefreshPhase4BHandle(handle,collapsed,label){if(!handle)return;handle.setAttribute('aria-expanded',collapsed?'false':'true');handle.setAttribute('aria-label',`${collapsed?'باز کردن':'جمع کردن'} ${label}`)}
function aqSetPhase4BSheet(kind,collapsed){
 const nav=$('#aqst-nav');if(!nav)return;const isHead=kind==='head',cls=isHead?'aqst-head-collapsed':'aqst-foot-collapsed',handle=$(isHead?'#aqst-head-handle':'#aqst-foot-handle');
 nav.classList.toggle(cls,!!collapsed);aqRefreshPhase4BHandle(handle,!!collapsed,isHead?'راهنمای مسیر':'اطلاعات مسیر');
 requestAnimationFrame(aqSyncPhase4BPanelInsets);setTimeout(aqSyncPhase4BPanelInsets,340);
}
function aqTogglePhase4BSheet(kind){const nav=$('#aqst-nav');if(!nav)return;const cls=kind==='head'?'aqst-head-collapsed':'aqst-foot-collapsed';aqSetPhase4BSheet(kind,!nav.classList.contains(cls))}
function aqBindPhase4BSwipe(handle,kind){
 if(!handle||handle.dataset.aqSwipe==='1')return;handle.dataset.aqSwipe='1';let startY=null;
 handle.addEventListener('touchstart',e=>{if(e.touches.length===1)startY=e.touches[0].clientY},{passive:true});
 handle.addEventListener('touchend',e=>{if(startY==null||!e.changedTouches.length){startY=null;return}const dy=e.changedTouches[0].clientY-startY;startY=null;if(Math.abs(dy)<24)return;if(kind==='head')aqSetPhase4BSheet('head',dy<0);else aqSetPhase4BSheet('foot',dy>0)},{passive:true});
}
function aqResetPhase4BPanels(){const nav=$('#aqst-nav');if(!nav)return;nav.classList.remove('aqst-head-collapsed','aqst-foot-collapsed');aqRefreshPhase4BHandle($('#aqst-head-handle'),false,'راهنمای مسیر');aqRefreshPhase4BHandle($('#aqst-foot-handle'),false,'اطلاعات مسیر');requestAnimationFrame(aqSyncPhase4BPanelInsets)}
function aqSetupPhase4BPanels(){
 const nav=$('#aqst-nav'),head=nav?.querySelector('.aqst-navhead'),foot=nav?.querySelector('.aqst-navfoot');if(!nav||!head||!foot||nav.dataset.aqPhase4b==='1')return;nav.dataset.aqPhase4b='1';
 head.id=head.id||'aqst-nav-head-sheet';foot.id=foot.id||'aqst-nav-foot-sheet';
 const makeHandle=(id,kind,parent,label)=>{const b=document.createElement('button');b.type='button';b.id=id;b.className='aqst-sheet-handle';b.setAttribute('aria-controls',parent.id);aqRefreshPhase4BHandle(b,false,label);b.addEventListener('click',()=>aqTogglePhase4BSheet(kind));aqBindPhase4BSwipe(b,kind);parent.appendChild(b);return b};
 makeHandle('aqst-head-handle','head',head,'راهنمای مسیر');makeHandle('aqst-foot-handle','foot',foot,'اطلاعات مسیر');
 const resize=()=>{requestAnimationFrame(aqSyncPhase4BPanelInsets)};
 if(window.ResizeObserver){const ro=new ResizeObserver(resize);ro.observe(head);ro.observe(foot);nav._aqPhase4bResizeObserver=ro}
 const mo=new MutationObserver(()=>{if(!nav.hidden)resize()});mo.observe(nav,{attributes:true,attributeFilter:['hidden','class']});nav._aqPhase4bMutationObserver=mo;
 window.visualViewport?.addEventListener?.('resize',resize,{passive:true});window.addEventListener('orientationchange',resize,{passive:true});
 $('#aqst-stop')?.addEventListener('click',aqResetPhase4BPanels);
 aqResetPhase4BPanels();
}
'''.strip()


_PHASE4B_CSS = r'''
/* Aqua Map Phase 4B — true fullscreen navigation + collapsible glass sheets. */
html.aqst-nav-fullscreen #aqst-nav{display:block!important;overflow:hidden!important;background:#07131d!important;isolation:isolate}
html.aqst-nav-fullscreen #aqst-nav .aqst-navmap{position:absolute!important;inset:0!important;width:100%!important;height:100%!important;min-height:100%!important;margin:0!important;z-index:1!important;border-radius:0!important;overflow:hidden!important}
html.aqst-nav-fullscreen #aqst-nav #aqst-nav-map{position:absolute!important;inset:0!important;width:100%!important;height:100%!important;min-height:100%!important}
html.aqst-nav-fullscreen #aqst-nav .aqst-navhead,
html.aqst-nav-fullscreen #aqst-nav .aqst-navfoot{position:absolute!important;left:calc(env(safe-area-inset-left) + 8px)!important;right:calc(env(safe-area-inset-right) + 8px)!important;width:auto!important;margin:0!important;z-index:55!important;overflow:visible!important;transition:transform .32s cubic-bezier(.22,.8,.22,1),box-shadow .32s ease,background-color .32s ease!important;will-change:transform;backdrop-filter:blur(24px) saturate(1.15)!important;-webkit-backdrop-filter:blur(24px) saturate(1.15)!important;border:1px solid rgba(135,224,255,.18)!important;box-shadow:0 16px 46px rgba(0,0,0,.36),0 0 26px rgba(20,178,239,.14)!important}
html.aqst-nav-fullscreen #aqst-nav .aqst-navhead{top:calc(env(safe-area-inset-top) + 7px)!important;background:linear-gradient(145deg,rgba(4,15,24,.94),rgba(7,29,43,.86))!important;border-radius:24px!important}
html.aqst-nav-fullscreen #aqst-nav .aqst-navfoot{bottom:calc(env(safe-area-inset-bottom) + 7px)!important;padding:12px 11px 11px!important;background:linear-gradient(165deg,rgba(5,18,28,.92),rgba(8,32,46,.9))!important;border-radius:24px!important}
html.aqst-nav-fullscreen #aqst-nav .aqst-next-strip{position:absolute!important;top:var(--aqst-head-bottom,112px)!important;right:calc(env(safe-area-inset-right) + 15px)!important;left:calc(env(safe-area-inset-left) + 15px)!important;width:auto!important;margin:0!important;z-index:48!important;transition:opacity .25s ease,transform .32s cubic-bezier(.22,.8,.22,1),top .32s ease!important;box-shadow:0 10px 28px rgba(0,0,0,.24),0 0 18px rgba(20,178,239,.09)!important}
html.aqst-nav-fullscreen #aqst-nav #aqst-map-actions{top:calc(var(--aqst-head-bottom,112px) + 8px)!important;transition:top .32s cubic-bezier(.22,.8,.22,1)!important}
html.aqst-nav-fullscreen #aqst-nav .aqst-drive-mode,
html.aqst-nav-fullscreen #aqst-nav .aqst-recenter{bottom:var(--aqst-foot-clear,150px)!important;transition:bottom .32s cubic-bezier(.22,.8,.22,1)!important}
html.aqst-nav-fullscreen #aqst-nav .aqst-sheet-handle{position:absolute!important;left:50%!important;transform:translateX(-50%)!important;width:58px!important;height:34px!important;min-width:58px!important;min-height:34px!important;padding:0!important;border:0!important;border-radius:999px!important;background:transparent!important;color:transparent!important;z-index:70!important;touch-action:manipulation;-webkit-tap-highlight-color:transparent}
html.aqst-nav-fullscreen #aqst-nav .aqst-sheet-handle::before{content:"";position:absolute;left:50%;top:50%;width:31px;height:4px;border-radius:999px;background:rgba(205,242,255,.78);transform:translate(-50%,-50%);box-shadow:0 0 12px rgba(41,196,255,.48)}
html.aqst-nav-fullscreen #aqst-nav #aqst-head-handle{bottom:-22px!important}
html.aqst-nav-fullscreen #aqst-nav #aqst-foot-handle{top:-22px!important}
html.aqst-nav-fullscreen #aqst-nav.aqst-head-collapsed .aqst-navhead{transform:translateY(calc(-100% + 28px))!important;box-shadow:0 8px 24px rgba(0,0,0,.3),0 0 18px rgba(20,178,239,.13)!important}
html.aqst-nav-fullscreen #aqst-nav.aqst-foot-collapsed .aqst-navfoot{transform:translateY(calc(100% - 28px))!important;box-shadow:0 -8px 24px rgba(0,0,0,.3),0 0 18px rgba(20,178,239,.13)!important}
html.aqst-nav-fullscreen #aqst-nav.aqst-head-collapsed .aqst-next-strip{opacity:0!important;transform:translateY(-14px)!important;pointer-events:none!important}
html.aqst-nav-fullscreen #aqst-nav .aqst-navhead:focus-within,
html.aqst-nav-fullscreen #aqst-nav .aqst-navfoot:focus-within{box-shadow:0 16px 48px rgba(0,0,0,.38),0 0 32px rgba(38,197,255,.2)!important}
@media(max-width:520px){
 html.aqst-nav-fullscreen #aqst-nav .aqst-navhead{left:calc(env(safe-area-inset-left) + 6px)!important;right:calc(env(safe-area-inset-right) + 6px)!important;top:calc(env(safe-area-inset-top) + 5px)!important;border-radius:21px!important}
 html.aqst-nav-fullscreen #aqst-nav .aqst-navfoot{left:calc(env(safe-area-inset-left) + 6px)!important;right:calc(env(safe-area-inset-right) + 6px)!important;bottom:calc(env(safe-area-inset-bottom) + 5px)!important;border-radius:21px!important;padding:10px 9px 9px!important}
 html.aqst-nav-fullscreen #aqst-nav .aqst-next-strip{right:calc(env(safe-area-inset-right) + 11px)!important;left:calc(env(safe-area-inset-left) + 11px)!important}
 html.aqst-nav-fullscreen #aqst-nav .aqst-sheet-handle{width:64px!important;height:36px!important}
}
@media(max-height:520px) and (orientation:landscape){
 html.aqst-nav-fullscreen #aqst-nav .aqst-navhead{max-width:min(620px,72vw)!important;right:auto!important}
 html.aqst-nav-fullscreen #aqst-nav .aqst-navfoot{max-width:min(560px,72vw)!important;right:calc(env(safe-area-inset-right) + 6px)!important;left:auto!important}
}
@media(prefers-reduced-motion:reduce){html.aqst-nav-fullscreen #aqst-nav .aqst-navhead,html.aqst-nav-fullscreen #aqst-nav .aqst-navfoot,html.aqst-nav-fullscreen #aqst-nav .aqst-next-strip,html.aqst-nav-fullscreen #aqst-nav #aqst-map-actions,html.aqst-nav-fullscreen #aqst-nav .aqst-drive-mode,html.aqst-nav-fullscreen #aqst-nav .aqst-recenter{transition:none!important}}
'''.strip()


@app_v3.app.after_request
def aqua_navigation_fullscreen_panels_asset(response):
    try:
        if response.status_code != 200:
            return response
        if request.path == "/aqua-smart-tour.js":
            response.direct_passthrough = False
            source = response.get_data(as_text=True)
            marker = "function aqSyncPhase4BPanelInsets()"
            if marker not in source:
                hook = "refreshVoiceCapability();if(typeof aqSetupPolish==='function')aqSetupPolish();\n}"
                hook_new = "refreshVoiceCapability();if(typeof aqSetupPolish==='function')aqSetupPolish();if(typeof aqSetupPhase4BPanels==='function')aqSetupPhase4BPanels();\n}"
                if hook not in source:
                    raise RuntimeError("Phase 4B createNav hook was not found")
                source = source.replace(hook, hook_new, 1)
                anchor = "\nfunction enhance(){"
                if anchor not in source:
                    raise RuntimeError("Phase 4B helper anchor was not found")
                source = source.replace(anchor, "\n" + _PHASE4B_JS + anchor, 1)
                response.set_data(source)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            marker = "/* Aqua Map Phase 4B — true fullscreen navigation + collapsible glass sheets. */"
            if marker not in css:
                css += "\n" + _PHASE4B_CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_fullscreen_panels_failed: %s", str(exc)[:180])
    return response
