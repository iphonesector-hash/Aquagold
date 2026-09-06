"""Final field-runtime repair for AquaGold test preview.

This module intentionally does NOT touch the boot/loading screen.
It only injects the final iPhone microphone + daily report edit runtime script.
"""
from __future__ import annotations

from flask import request

import app_v3


FINAL_JS = "/aqua-round8-mic-edit-only.js"

# Daily rows are rendered by Alpine x-for. Earlier runtime patches changed the
# template itself, but already-rendered iPhone rows could still keep the older
# click path. This final fallback acts on the actual rendered button and asks
# Alpine to evaluate the canonical app expression inside that exact row scope.
# It does not alter the microphone runtime or any other page.
DAILY_EDIT_CLICK_FIX = r'''
<script id="aqua-daily-edit-rendered-row-fix">
(()=>{
  if(window.__aquaDailyRenderedRowFix)return;
  window.__aquaDailyRenderedRowFix=true;

  const isDailyEditButton=(button)=>{
    if(!button)return false;
    const section=button.closest?.('section');
    if(!section)return false;
    const show=section.getAttribute?.('x-show')||'';
    if(!show.includes("page==='daily'"))return false;
    return String(button.textContent||'').trim()==='ویرایش';
  };

  const fallbackOpen=(button)=>{
    const scopes=[];
    try{if(Array.isArray(button?._x_dataStack))scopes.push(...button._x_dataStack)}catch{}
    let job=null;
    let state=null;
    for(const scope of scopes){
      if(!job&&scope?.j)job=scope.j;
      if(!state&&scope&&typeof scope.openServiceEdit==='function')state=scope;
    }
    try{
      if(!state&&Array.isArray(document.body?._x_dataStack)){
        state=document.body._x_dataStack.find(scope=>scope&&typeof scope.openServiceEdit==='function')||null;
      }
    }catch{}
    if(!job||!state)return false;
    state.openServiceEdit.call(state,job);
    return true;
  };

  const openCanonical=(button)=>{
    try{
      if(window.Alpine&&typeof window.Alpine.evaluate==='function'){
        window.Alpine.evaluate(button,'openServiceEdit(j)');
        return true;
      }
    }catch(error){
      console.warn('aqua_daily_edit_alpine_evaluate_failed',error);
    }
    return fallbackOpen(button);
  };

  document.addEventListener('click',event=>{
    const button=event.target?.closest?.('button');
    if(!isDailyEditButton(button))return;
    try{
      if(openCanonical(button)){
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }catch(error){
      console.warn('aqua_daily_edit_rendered_row_failed',error);
    }
  },true);
})();
</script>
'''


@app_v3.app.get(FINAL_JS)
def aqua_round8_mic_edit_only_js():
    return app_v3.send_from_directory(
        ".",
        "aqua-round8-mic-edit-only.js",
        mimetype="application/javascript",
        max_age=0,
    )


@app_v3.app.after_request
def finalize_aqua_round8_field_runtime(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response

        response.direct_passthrough = False
        body = response.get_data(as_text=True)

        # Important: leave every loader/splash asset and observer exactly as the
        # previous working preview had it. This layer is mic + daily edit only.
        if FINAL_JS + "?" not in body:
            body = body.replace(
                "</body>",
                f'<script src="{FINAL_JS}?v=20260906-5"></script></body>',
                1,
            )
        if 'id="aqua-daily-edit-rendered-row-fix"' not in body:
            body = body.replace("</body>", DAILY_EDIT_CLICK_FIX + "</body>", 1)

        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_round8_field_runtime_failed detail=%s", str(exc)[:320])
    return response
