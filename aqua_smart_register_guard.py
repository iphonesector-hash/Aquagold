"""Runtime guard for Smart Intake registration.

Keeps a successful Smart Intake submit from being followed by a misleading
second validation error, and recovers the surname from the selected customer
or a fresh local parse when the edited UI object temporarily misses it.
"""
from __future__ import annotations

from flask import request

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


@app_v3.app.after_request
def inject_smart_register_guard(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        marker = 'id="aqua-smart-register-guard"'
        if marker not in body:
            body = body.replace(
                "</body>",
                f'<script id="aqua-smart-register-guard">{SMART_GUARD_SCRIPT}</script></body>',
                1,
            )
            response.set_data(body)
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("smart_register_guard_injection_failed: %s", exc)
    return response
