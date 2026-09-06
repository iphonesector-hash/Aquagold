"""Final field-runtime repair for AquaGold test preview.

This module intentionally does NOT touch the boot/loading screen.
It keeps the iPhone microphone runtime and gives the daily report its own
native editor so the edit action no longer depends on layered Alpine shims.
"""
from __future__ import annotations

from flask import request

import app_v3


FINAL_JS = "/aqua-round8-mic-edit-only.js"

# The daily edit button has accumulated multiple Alpine/runtime click shims on
# this branch. On the real iPhone build the visible button can therefore exist
# while its Alpine action never reaches the editor. This inline repair does not
# call openServiceEdit at all. It reads the exact row's `j` scope, opens a
# native DOM modal, and saves through the root Aqua api() helper (or a direct
# authenticated PATCH fallback). Pointer/touch interception happens before the
# older click listeners, so those shims cannot swallow the action.
DAILY_EDIT_NATIVE = r'''
<script id="aqua-daily-edit-native-v1">
(()=>{
  if(window.__aquaDailyNativeV1)return;
  window.__aquaDailyNativeV1=true;

  let currentJob=null;
  let currentState=null;
  let lastOpenAt=0;

  const faToEn=value=>String(value??'')
    .replace(/[۰-۹]/g,d=>'۰۱۲۳۴۵۶۷۸۹'.indexOf(d))
    .replace(/[٠-٩]/g,d=>'٠١٢٣٤٥٦٧٨٩'.indexOf(d));
  const num=value=>Number(faToEn(value).replace(/[^0-9.-]/g,''))||0;
  const cookie=name=>{
    const hit=document.cookie.split('; ').find(x=>x.startsWith(name+'='));
    return hit?decodeURIComponent(hit.slice(name.length+1)):'';
  };

  const isDailyButton=button=>{
    if(!button||String(button.textContent||'').trim()!=='ویرایش')return false;
    const section=button.closest?.('section');
    return !!section&&String(section.getAttribute?.('x-show')||'').includes("page==='daily'");
  };

  const scopesFrom=node=>{
    const out=[];
    let el=node;
    while(el&&el!==document.documentElement){
      try{if(Array.isArray(el._x_dataStack))out.push(...el._x_dataStack)}catch{}
      el=el.parentElement;
    }
    return out;
  };

  const resolveContext=button=>{
    const scopes=scopesFrom(button);
    let job=null;
    let state=null;
    for(const scope of scopes){
      if(!job&&scope?.j)job=scope.j;
      if(!state&&scope&&typeof scope.api==='function')state=scope;
    }
    try{
      if(!state&&Array.isArray(document.body?._x_dataStack)){
        state=document.body._x_dataStack.find(scope=>scope&&typeof scope.api==='function')||null;
      }
    }catch{}
    return {job,state};
  };

  const ensureModal=()=>{
    let modal=document.getElementById('aqua-native-daily-edit-modal');
    if(modal)return modal;
    modal=document.createElement('div');
    modal.id='aqua-native-daily-edit-modal';
    modal.dir='rtl';
    modal.style.cssText='display:none;position:fixed;inset:0;z-index:2147483000;background:rgba(0,0,0,.68);padding:16px;align-items:center;justify-content:center;';
    modal.innerHTML=`
      <div class="card" style="width:min(560px,100%);max-height:90vh;overflow:auto;padding:20px;position:relative">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px">
          <div><b style="font-size:1.1rem">ویرایش سرویس روزانه</b><div id="aqua-native-edit-name" class="muted" style="font-size:.8rem;margin-top:3px"></div></div>
          <button type="button" id="aqua-native-edit-close" class="btn glass">بستن</button>
        </div>
        <div style="display:grid;gap:12px">
          <input id="aqua-native-edit-service" class="field" placeholder="نوع سرویس">
          <select id="aqua-native-edit-status" class="field">
            <option value="completed">تکمیل شده</option><option value="registered">ثبت شده</option>
            <option value="scheduled">برنامه‌ریزی شده</option><option value="revisit">نیاز به مراجعه</option>
            <option value="partial">تسویه ناقص</option><option value="unpaid">پرداخت نشده</option>
          </select>
          <input id="aqua-native-edit-invoice" inputmode="numeric" class="field" placeholder="مبلغ فاکتور">
          <input id="aqua-native-edit-received" inputmode="numeric" class="field" placeholder="مبلغ دریافت‌شده">
          <textarea id="aqua-native-edit-description" class="field" rows="3" placeholder="شرح کار"></textarea>
        </div>
        <button type="button" id="aqua-native-edit-save" class="btn primary" style="width:100%;margin-top:16px">ذخیره ویرایش</button>
      </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#aqua-native-edit-close').addEventListener('click',()=>{modal.style.display='none'});
    modal.addEventListener('click',event=>{if(event.target===modal)modal.style.display='none'});
    modal.querySelector('#aqua-native-edit-save').addEventListener('click',saveCurrent);
    return modal;
  };

  const fillAndOpen=(job,state)=>{
    currentJob=job;
    currentState=state;
    const modal=ensureModal();
    modal.querySelector('#aqua-native-edit-name').textContent=job?.name||'';
    modal.querySelector('#aqua-native-edit-service').value=job?.service_type||'';
    modal.querySelector('#aqua-native-edit-status').value=job?.status||'completed';
    modal.querySelector('#aqua-native-edit-invoice').value=Number(job?.invoice_amount||0);
    modal.querySelector('#aqua-native-edit-received').value=Number(job?.received_amount||0);
    modal.querySelector('#aqua-native-edit-description').value=job?.description||'';
    modal.style.display='flex';
  };

  async function directPatch(id,payload){
    const headers={'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()};
    const csrf=cookie('aquagold_csrf');
    if(csrf)headers['X-CSRF-Token']=csrf;
    const response=await fetch('/api/jobs/'+encodeURIComponent(id),{
      method:'PATCH',headers,body:JSON.stringify(payload),credentials:'same-origin',cache:'no-store'
    });
    let data={};
    try{data=await response.json()}catch{}
    if(!response.ok)throw new Error(data.error||'ویرایش سرویس انجام نشد');
    return data;
  }

  async function saveCurrent(){
    if(!currentJob?.id)return alert('سرویس این ردیف پیدا نشد');
    const modal=ensureModal();
    const save=modal.querySelector('#aqua-native-edit-save');
    if(save.disabled)return;
    const payload={
      service_type:modal.querySelector('#aqua-native-edit-service').value||'',
      status:modal.querySelector('#aqua-native-edit-status').value||'completed',
      invoice_amount:num(modal.querySelector('#aqua-native-edit-invoice').value),
      received_amount:num(modal.querySelector('#aqua-native-edit-received').value),
      description:modal.querySelector('#aqua-native-edit-description').value||''
    };
    save.disabled=true;
    const oldText=save.textContent;
    save.textContent='در حال ذخیره…';
    try{
      let result;
      if(currentState&&typeof currentState.api==='function'){
        result=await currentState.api('/jobs/'+currentJob.id,{method:'PATCH',body:JSON.stringify(payload)});
      }else{
        result=await directPatch(currentJob.id,payload);
      }
      Object.assign(currentJob,payload);
      modal.style.display='none';
      if(result?.queued){
        alert('ویرایش روی گوشی ذخیره شد و بعد از اتصال همگام می‌شود');
      }else{
        try{if(currentState&&typeof currentState.refreshAll==='function')await currentState.refreshAll()}catch{}
        alert('سرویس و مبلغ‌ها ویرایش شد');
      }
    }catch(error){
      alert(error?.message||'ویرایش سرویس انجام نشد');
    }finally{
      save.disabled=false;
      save.textContent=oldText;
    }
  }

  const intercept=event=>{
    const button=event.target?.closest?.('button');
    if(!isDailyButton(button))return;
    const now=Date.now();
    event.preventDefault();
    event.stopImmediatePropagation();
    if(now-lastOpenAt<350)return;
    lastOpenAt=now;
    const {job,state}=resolveContext(button);
    if(!job){
      alert('اطلاعات این سرویس از ردیف روزانه خوانده نشد؛ صفحه را یک‌بار تازه کن');
      return;
    }
    fillAndOpen(job,state);
  };

  document.addEventListener('pointerdown',intercept,true);
  document.addEventListener('touchstart',intercept,{capture:true,passive:false});
  document.addEventListener('click',intercept,true);
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

        # Leave the splash/loader exactly as the previous preview had it. This
        # layer only owns the iPhone mic runtime and the daily native editor.
        if FINAL_JS + "?" not in body:
            body = body.replace(
                "</body>",
                f'<script src="{FINAL_JS}?v=20260906-6"></script></body>',
                1,
            )
        if 'id="aqua-daily-edit-native-v1"' not in body:
            body = body.replace("</body>", DAILY_EDIT_NATIVE + "</body>", 1)

        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_round8_field_runtime_failed detail=%s", str(exc)[:320])
    return response
