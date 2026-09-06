'''Runtime guard for Smart Intake registration.

Keeps a successful Smart Intake submit from being followed by a misleading
second validation error, recovers the surname when necessary, and owns the
last branch-only UI pass used for the September 6 field fixes.
'''
from __future__ import annotations

from flask import Response, request
import base64
from pathlib import Path

import app_v3


_original_smart_register = app_v3.app.view_functions.get("smart_register")


def _fill_missing_surname():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return
    parsed = data.get("parsed")
    if not isinstance(parsed, dict):
        parsed = {}
        data["parsed"] = parsed
    if str(parsed.get("last_name") or "").strip():
        return

    customer_id = data.get("customer_id")
    if customer_id:
        try:
            with app_v3.get_db() as db, db.cursor() as cur:
                cur.execute(
                    "select first_name,last_name from customers_v2 where id=%s::uuid and archived=false",
                    (str(customer_id),),
                )
                customer = cur.fetchone()
            if customer:
                surname = str(customer.get("last_name") or customer.get("first_name") or "").strip()
                if surname:
                    parsed["last_name"] = surname
                    return
        except Exception as exc:
            app_v3.logger.warning("smart_register_customer_surname_lookup_failed: %s", exc)

    raw_text = str(data.get("text") or parsed.get("raw_text") or "").strip()
    if raw_text:
        try:
            reparsed = app_v3.parse_intake(raw_text) or {}
            surname = str(reparsed.get("last_name") or "").strip()
            if surname:
                parsed["last_name"] = surname
        except Exception as exc:
            app_v3.logger.warning("smart_register_surname_reparse_failed: %s", exc)


def _smart_register_resilient():
    _fill_missing_surname()
    return _original_smart_register()


if _original_smart_register is not None:
    app_v3.app.view_functions["smart_register"] = _smart_register_resilient


SMART_GUARD_SCRIPT = r'''
(()=>{
  if(window.__aquaSmartRegisterGuard)return;
  const base=window.app;
  if(typeof base!=='function')return;
  window.__aquaSmartRegisterGuard=true;
  window.app=function(){
    const state=base();
    const original=state.registerSmart?.bind(state);
    state.smartRegisterBusy=false;
    state.registerSmart=async function(){
      if(this.smartRegisterBusy)return;
      this.smartRegisterBusy=true;
      try{
        if(this.smartParsed){
          const fields=[...document.querySelectorAll('input[placeholder="نام خانوادگی"]')];
          const field=fields.find(el=>el.offsetParent!==null);
          const typed=String(field?.value||'').trim();
          if(typed)this.smartParsed.last_name=typed;
          if(!String(this.smartParsed.last_name||'').trim()&&this.smartCustomerId){
            const customer=(this.customers||[]).find(c=>String(c.id)===String(this.smartCustomerId));
            const surname=String(customer?.last_name||customer?.name||'').trim();
            if(surname)this.smartParsed.last_name=surname;
          }
        }
        return await original?.();
      }finally{
        this.smartRegisterBusy=false;
      }
    };
    return state;
  };
})();
'''

BOOT_HEAD = (
    '<link rel="preload" as="image" href="/assets/aquagold-loading-v20260906.jpg">'
    '<link rel="apple-touch-startup-image" href="/assets/aquagold-loading-v20260906.jpg">'
    '<style>body[x-cloak]{display:block!important;overflow:hidden}</style>'
)

BOOT_HTML = r'''
<div id="aqua-boot-20260906" aria-label="در حال بارگذاری AquaGold" style="position:fixed;inset:0;z-index:2147483000;background:#010817;display:grid;place-items:center;overflow:hidden;transition:opacity .35s ease;opacity:1">
  <img src="/assets/aquagold-loading-v20260906.jpg" alt="Aqua sector" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center;user-select:none;-webkit-user-drag:none">
  <div style="position:absolute;left:12%;right:12%;bottom:max(42px,calc(env(safe-area-inset-bottom) + 26px));height:3px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden;box-shadow:0 0 18px rgba(35,206,255,.18)">
    <i style="display:block;width:42%;height:100%;border-radius:inherit;background:linear-gradient(90deg,#0789e8,#2be8ff);animation:aquaBootSweep 1.2s ease-in-out infinite alternate"></i>
  </div>
</div>
<style>@keyframes aquaBootSweep{from{transform:translateX(0)}to{transform:translateX(138%)}}</style>
<script>
(()=>{
 const id='aqua-boot-20260906';
 const hide=()=>{
   const el=document.getElementById(id);if(!el)return;
   el.style.opacity='0';el.style.pointerEvents='none';
   setTimeout(()=>el.remove(),420);
 };
 const show=()=>{const el=document.getElementById(id);if(el){el.style.opacity='1';el.style.pointerEvents='auto'}};
 window.AquaBoot={...(window.AquaBoot||{}),hide,show};
 const watch=()=>{
   const body=document.body;if(!body)return;
   if(!body.hasAttribute('x-cloak')){hide();return}
   const observer=new MutationObserver(()=>{if(!body.hasAttribute('x-cloak')){observer.disconnect();hide()}});
   observer.observe(body,{attributes:true,attributeFilter:['x-cloak']});
 };
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',watch,{once:true});else watch();
 document.addEventListener('alpine:initialized',()=>setTimeout(hide,180),{once:true});
 setTimeout(hide,12000);
})();
</script>
'''


_LOADING_B64 = "aqua-loading-v20260906.b64"


@app_v3.app.get("/assets/aquagold-loading-v20260906.jpg")
def aqua_round6_loading_image():
    asset_path = Path(__file__).resolve().parent / "assets" / _LOADING_B64
    payload = base64.b64decode(asset_path.read_text(encoding="ascii"))
    return Response(
        payload,
        mimetype="image/jpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app_v3.app.get("/aqua-round6-user-fixes.js")
def aqua_round6_user_fixes_js():
    return app_v3.send_from_directory(
        ".",
        "aqua-round6-user-fixes.js",
        mimetype="application/javascript",
        max_age=0,
    )


@app_v3.app.after_request
def inject_smart_register_guard(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response
        response.direct_passthrough = False
        body = response.get_data(as_text=True)

        if "/assets/aquagold-loading-v20260906.jpg" not in body:
            body = body.replace("</head>", BOOT_HEAD + "</head>", 1)

        boot_marker = 'id="aqua-boot-20260906"'
        if boot_marker not in body:
            body = body.replace(
                '<body x-data="app()" x-init="init()" x-cloak>',
                '<body x-data="app()" x-init="init()" x-cloak>' + BOOT_HTML,
                1,
            )

        marker = 'id="aqua-smart-register-guard"'
        if marker not in body:
            body = body.replace(
                "</body>",
                f'<script id="aqua-smart-register-guard">{SMART_GUARD_SCRIPT}</script>'
                '<script src="/aqua-round6-user-fixes.js?v=20260906-1"></script></body>',
                1,
            )
        elif "/aqua-round6-user-fixes.js?" not in body:
            body = body.replace(
                "</body>",
                '<script src="/aqua-round6-user-fixes.js?v=20260906-1"></script></body>',
                1,
            )

        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("smart_register_guard_injection_failed: %s", exc)
    return response
