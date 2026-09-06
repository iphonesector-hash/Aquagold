'''Runtime guard for Smart Intake registration.

Keeps a successful Smart Intake submit from being followed by a misleading
second validation error, recovers the surname when necessary, and owns the
Smart-to-Bale completion bridge without changing unrelated Aqua flows.
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


def _link_bale_job_to_smart_visit(response, bale_job_id):
    if not bale_job_id or response.status_code >= 300 or not response.is_json:
        return response

    payload = response.get_json(silent=True) or {}
    visit_id = payload.get("visit_id")
    customer_id = payload.get("customer_id")
    finalized = False

    if visit_id and customer_id:
        try:
            with app_v3.get_db() as db, db.cursor() as cur:
                cur.execute(
                    "select status,service_visit_id from bale_jobs where id=%s::uuid for update",
                    (str(bale_job_id),),
                )
                job = cur.fetchone()
                if job and job["status"] in {"new", "review"}:
                    cur.execute(
                        "select received_amount from service_visits where id=%s::uuid and customer_id=%s::uuid",
                        (str(visit_id), str(customer_id)),
                    )
                    service = cur.fetchone()
                    if service:
                        cur.execute(
                            """update bale_jobs
                               set status='completed',customer_id=%s::uuid,service_visit_id=%s::uuid,
                                   received_amount=%s,completed_at=coalesce(completed_at,now()),updated_at=now()
                               where id=%s::uuid and status in ('new','review')
                               returning id""",
                            (str(customer_id), str(visit_id), service.get("received_amount") or 0, str(bale_job_id)),
                        )
                        updated = cur.fetchone()
                        finalized = bool(updated)
                        if finalized:
                            app_v3.audit(
                                cur,
                                "bale_job",
                                bale_job_id,
                                "smart_register_finalize",
                                before={"status": job["status"]},
                                after={"service_visit_id": str(visit_id), "customer_id": str(customer_id)},
                            )
                elif job and job["status"] == "completed":
                    finalized = True
        except Exception as exc:
            app_v3.logger.warning("smart_register_bale_link_failed: %s", exc)

    payload["bale_job_id"] = str(bale_job_id)
    payload["bale_finalized"] = bool(finalized)
    response.set_data(app_v3.app.json.dumps(payload))
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    return response


def _smart_register_resilient():
    data = request.get_json(silent=True)
    bale_job_id = None
    if isinstance(data, dict) and data.get("bale_job_id") not in (None, ""):
        bale_job_id = app_v3.valid_uuid(data.get("bale_job_id"), "شناسه کار بله")

    _fill_missing_surname()
    response = app_v3.app.make_response(_original_smart_register())
    return _link_bale_job_to_smart_visit(response, bale_job_id)


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

      const pending=this.baleSmartJob?{...this.baleSmartJob}:null;
      const pendingId=String(pending?.id||'').trim();
      const savedApi=this.api;
      const savedOpenCustomer=this.openCustomer;
      let smartResponse=null;
      let result;

      if(pendingId){
        // The Smart register request is the single owner of Bale completion.
        // Hide the pending marker from older inner wrappers so they cannot run
        // a second finalize request or open the customer detail page first.
        this.baleSmartJob=null;
        if(typeof savedOpenCustomer==='function')this.openCustomer=async()=>{};
        this.api=async (path,opts={})=>{
          if(path==='/smart/register'&&String(opts?.method||'GET').toUpperCase()==='POST'){
            let body={};
            try{body=JSON.parse(opts?.body||'{}')||{}}catch{}
            body.bale_job_id=pendingId;
            const response=await savedApi.call(this,path,{...opts,body:JSON.stringify(body)});
            smartResponse=response;
            return response;
          }
          return savedApi.call(this,path,opts);
        };
      }

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
        result=await original?.();
      }finally{
        if(pendingId){
          this.api=savedApi;
          if(typeof savedOpenCustomer==='function')this.openCustomer=savedOpenCustomer;
        }
        this.smartRegisterBusy=false;
      }

      if(pendingId){
        if(smartResponse?.bale_finalized===true){
          this.baleSmartJob=null;
          this.smartText='';
          this.smartParsed=null;
          this.smartSuggestions=[];
          this.smartCustomerId='';
          this.smartGps={};
          this.selectedCustomer=null;
          this.selectedCustomerJobsRemote=[];
          this.baleJobs=(this.baleJobs||[]).filter(job=>String(job?.id||'')!==pendingId);
          try{await Promise.all([this.loadBaleCounts?.(),this.loadBaleJobs?.('new')])}catch{}
          this.baleJobs=(this.baleJobs||[]).filter(job=>String(job?.id||'')!==pendingId);
          try{await this.go?.('bale-jobs')}catch{this.page='bale-jobs'}
          this.toast?.('ثبت شد و کار از فهرست کارهای بله خارج شد','success');
        }else{
          // Keep the original job reference available to the older outer guard
          // as a fallback only when the direct server link could not complete.
          this.baleSmartJob=pending;
        }
      }
      return result;
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