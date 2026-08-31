"""Consolidated AquaGold operations layer: real PWA push, lighter startup,
finance visuals, Jalali formatting, invoice export hardening, and Bale new-job alerts.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from flask import Response, jsonify, request
from pywebpush import WebPushException, webpush

import app_v3
import bale_bridge

app = app_v3.app

PUSH_SETTINGS_KEY = "web_push"
PUSH_TABLE_SQL = """
create table if not exists public.push_subscriptions (
  endpoint_hash text primary key,
  endpoint text not null,
  subscription jsonb not null,
  user_id text,
  user_agent text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
)
"""


def _ensure_push_table(cur=None):
    if cur is not None:
        cur.execute(PUSH_TABLE_SQL)
        return
    with app_v3.get_db() as db, db.cursor() as cursor:
        cursor.execute(PUSH_TABLE_SQL)


def _load_push_settings(cur=None):
    own = cur is None
    ctx = app_v3.get_db() if own else None
    db = ctx.__enter__() if own else None
    cursor = db.cursor() if own else cur
    try:
        cursor.execute("select value from app_settings where key=%s", (PUSH_SETTINGS_KEY,))
        row = cursor.fetchone()
        return dict((row or {}).get("value") or {})
    finally:
        if own:
            cursor.close()
            ctx.__exit__(None, None, None)


def _vapid_keys():
    with app_v3.get_db() as db, db.cursor() as cur:
        raw = _load_push_settings(cur)
        private_pem = bale_bridge._decrypt(raw.get("private_key_cipher"))
        public_key = str(raw.get("public_key") or "")
        if private_pem and public_key:
            return private_pem, public_key

        key = ec.generate_private_key(ec.SECP256R1())
        private_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        public_bytes = key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode()
        stored = {
            "private_key_cipher": bale_bridge._encrypt(private_pem),
            "public_key": public_key,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        cur.execute(
            """insert into app_settings(key,value,updated_at) values(%s,%s,now())
               on conflict(key) do update set value=excluded.value,updated_at=now()""",
            (PUSH_SETTINGS_KEY, app_v3.Jsonb(stored)),
        )
        return private_pem, public_key


def _subscription_hash(endpoint):
    return hashlib.sha256(str(endpoint).encode()).hexdigest()


def _send_push(payload):
    _ensure_push_table()
    private_pem, _ = _vapid_keys()
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select endpoint_hash,subscription from push_subscriptions order by updated_at desc")
        rows = list(cur.fetchall())
    delivered = 0
    stale = []
    for row in rows:
        try:
            webpush(
                subscription_info=dict(row["subscription"]),
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=private_pem,
                vapid_claims={"sub": "mailto:notifications@aquagold.app"},
                ttl=180,
            )
            delivered += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in {404, 410}:
                stale.append(row["endpoint_hash"])
            else:
                app.logger.warning("web_push_failed status=%s detail=%s", status, str(exc)[:300])
        except Exception as exc:
            app.logger.warning("web_push_failed detail=%s", str(exc)[:300])
    if stale:
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("delete from push_subscriptions where endpoint_hash = any(%s)", (stale,))
    return delivered


@app.get("/api/push/config")
@app_v3.roles_required("technician")
def push_config():
    _, public_key = _vapid_keys()
    _ensure_push_table()
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select count(*)::int count from push_subscriptions")
        count = int((cur.fetchone() or {}).get("count") or 0)
    return jsonify({"public_key": public_key, "subscriptions": count})


@app.post("/api/push/subscribe")
@app_v3.roles_required("technician")
def push_subscribe():
    data = request.get_json(silent=True) or {}
    endpoint = str(data.get("endpoint") or "").strip()
    keys = data.get("keys") or {}
    if not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
        return jsonify({"error": "اشتراک Push معتبر نیست"}), 400
    _ensure_push_table()
    payload = {"endpoint": endpoint, "expirationTime": data.get("expirationTime"), "keys": keys}
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """insert into push_subscriptions(endpoint_hash,endpoint,subscription,user_id,user_agent,updated_at)
               values(%s,%s,%s,%s,%s,now())
               on conflict(endpoint_hash) do update
               set endpoint=excluded.endpoint,subscription=excluded.subscription,user_id=excluded.user_id,
                   user_agent=excluded.user_agent,updated_at=now()""",
            (
                _subscription_hash(endpoint),
                endpoint,
                app_v3.Jsonb(payload),
                str(request.current_user.get("user_id") or ""),
                str(request.headers.get("User-Agent") or "")[:600],
            ),
        )
    return jsonify({"ok": True})


@app.delete("/api/push/subscribe")
@app_v3.roles_required("technician")
def push_unsubscribe():
    endpoint = str((request.get_json(silent=True) or {}).get("endpoint") or "").strip()
    if endpoint:
        _ensure_push_table()
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("delete from push_subscriptions where endpoint_hash=%s", (_subscription_hash(endpoint),))
    return jsonify({"ok": True})


@app.post("/api/push/test")
@app_v3.roles_required("technician")
def push_test():
    count = _send_push(
        {
            "title": "AquaGold",
            "body": "اعلان گوشی با موفقیت فعال است.",
            "url": "/?open=bale-jobs",
            "tag": "aquagold-push-test",
        }
    )
    return jsonify({"ok": True, "delivered": count})


# Notify phones only after a genuinely new Bale job was inserted.
_original_webhook = app.view_functions.get("bale_webhook")


def _webhook_with_web_push(secret):
    response = app.make_response(_original_webhook(secret))
    try:
        payload = response.get_json(silent=True) if response.is_json else {}
        if response.status_code < 300 and (payload or {}).get("registered"):
            job_id = str((payload or {}).get("job_id") or "")
            with app_v3.get_db() as db, db.cursor() as cur:
                cur.execute(
                    """select coalesce(nullif(trim(customer_name),''),'مشتری جدید') customer_name,
                              coalesce(nullif(trim(job_type),''),'سرویس') job_type,
                              coalesce(nullif(trim(address),''),'') address
                       from bale_jobs where id=%s::uuid""",
                    (job_id,),
                )
                job = cur.fetchone()
            if job:
                body = f"{job['customer_name']} • {job['job_type']}"
                if job.get("address"):
                    body += f" • {str(job['address'])[:90]}"
                _send_push(
                    {
                        "title": "🔔 کار جدید AquaGold",
                        "body": body,
                        "url": "/?open=bale-jobs",
                        "tag": f"bale-job-{job_id}",
                    }
                )
    except Exception as exc:
        app.logger.warning("new_bale_job_web_push_failed: %s", exc)
    return response


if _original_webhook is not None:
    app.view_functions["bale_webhook"] = _webhook_with_web_push


RUNTIME_JS = r"""
(()=>{
 if(window.__aquaOpsV8)return; window.__aquaOpsV8=true;
 const previous=window.app;
 if(typeof previous!=='function')return;
 const faDigits=n=>String(n).replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[Number(d)]);
 const two=n=>String(n).padStart(2,'0');
 const dateParts=v=>{
   const d=v instanceof Date?v:new Date(v);
   const parts=new Intl.DateTimeFormat('en-US-u-ca-persian',{timeZone:'Asia/Tehran',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(d);
   const o={};parts.forEach(p=>{if(['year','month','day'].includes(p.type))o[p.type]=Number(p.value)});
   return o;
 };
 const jalaliNumeric=v=>{const p=dateParts(v);return `\u2066${faDigits(p.year)}/${faDigits(two(p.month))}/${faDigits(two(p.day))}\u2069`};
 const weekDay=v=>new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',weekday:'long'}).format(new Date(v));
 const timeText=v=>new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(v));
 const b64ToBytes=s=>{const pad='='.repeat((4-s.length%4)%4),raw=atob((s+pad).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from([...raw].map(c=>c.charCodeAt(0)))};

 window.app=function(){
   const s=previous();

   if(typeof s.refreshAll==='function'){
     const originalRefreshAll=s.refreshAll.bind(s);let refreshPromise=null;
     s.refreshAll=async function(){
       if(refreshPromise)return refreshPromise;
       refreshPromise=Promise.resolve(originalRefreshAll()).finally(()=>{refreshPromise=null});
       return refreshPromise;
     };
   }

   if(typeof s.refreshCommerce==='function'){
     const originalRefreshCommerce=s.refreshCommerce.bind(s);let commercePromise=null;
     s.refreshCommerce=async function(force=false){
       if(!force && !['products','product-edit','invoices','invoice-new','invoice-view'].includes(this.page))return;
       if(commercePromise)return commercePromise;
       commercePromise=Promise.resolve(originalRefreshCommerce()).finally(()=>{commercePromise=null});
       return commercePromise;
     };
   }

   s.persianDate=function(v){
     if(!v)return'';
     const d=/^\d{4}-\d{2}-\d{2}$/.test(String(v))?new Date(String(v)+'T12:00:00+03:30'):new Date(v);
     return `${weekDay(d)} • ${jalaliNumeric(d)}`;
   };
   s.persianDateTime=function(v){
     if(!v)return'';
     try{return `${jalaliNumeric(v)} • ${timeText(v)}`}catch{return String(v)}
   };

   s.pushStatus='نامشخص';
   s.enablePhonePush=async function(){
     if(!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window)){
       return this.toast?.('Push روی این مرورگر پشتیبانی نمی‌شود','error');
     }
     const isIOS=/iPhone|iPad|iPod/i.test(navigator.userAgent);
     const standalone=window.matchMedia?.('(display-mode: standalone)').matches||navigator.standalone===true;
     if(isIOS&&!standalone){
       return this.toast?.('برای اعلان آیفون، AquaGold را اول Add to Home Screen کن و از آیکن برنامه باز کن.','info');
     }
     const permission=await Notification.requestPermission();
     if(permission!=='granted')return this.toast?.('اجازه اعلان داده نشد','error');
     const config=await this.api('/push/config');
     const registration=await navigator.serviceWorker.ready;
     let subscription=await registration.pushManager.getSubscription();
     if(!subscription){
       subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64ToBytes(config.public_key)});
     }
     await this.api('/push/subscribe',{method:'POST',body:JSON.stringify(subscription.toJSON())});
     this.pushStatus='فعال';
     this.toast?.('اعلان کار جدید روی گوشی فعال شد','success');
   };
   s.disablePhonePush=async function(){
     const registration=await navigator.serviceWorker.ready;
     const subscription=await registration.pushManager.getSubscription();
     if(subscription){
       await this.api('/push/subscribe',{method:'DELETE',body:JSON.stringify({endpoint:subscription.endpoint})});
       await subscription.unsubscribe();
     }
     this.pushStatus='غیرفعال';this.toast?.('اعلان گوشی غیرفعال شد','info');
   };
   s.testPhonePush=async function(){
     const r=await this.api('/push/test',{method:'POST',body:'{}'});
     this.toast?.(r.delivered?'اعلان آزمایشی ارسال شد':'اشتراک فعالی پیدا نشد',r.delivered?'success':'info');
   };
   s.syncPhonePush=async function(){
     try{
       if(!('serviceWorker' in navigator)||!('PushManager' in window)){this.pushStatus='پشتیبانی نمی‌شود';return}
       const registration=await navigator.serviceWorker.ready;
       const subscription=await registration.pushManager.getSubscription();
       this.pushStatus=subscription&&Notification.permission==='granted'?'فعال':'غیرفعال';
       if(subscription&&Notification.permission==='granted'){
         await this.api('/push/subscribe',{method:'POST',body:JSON.stringify(subscription.toJSON())});
       }
     }catch{}
   };

   const originalRender=s.renderCharts?.bind(s);
   s.renderCharts=function(){
     if(!window.Chart)return originalRender?.();
     const palette=['#22d3ee','#3b82f6','#8b5cf6','#14b8a6','#f59e0b','#f43f5e','#84cc16','#06b6d4'];
     const months=this.jalaliMonthlyMetrics||[],labels=months.map(m=>m.label),c1=document.getElementById('monthlyChart');
     if(c1){this.monthlyChart?.destroy?.();this.monthlyChart=new Chart(c1,{type:'line',data:{labels,datasets:[
       {label:'دریافتی',data:months.map(m=>m.received),borderColor:palette[0],backgroundColor:'rgba(34,211,238,.14)',fill:true,tension:.35},
       {label:'سود خالص',data:months.map(m=>m.net_profit),borderColor:palette[3],backgroundColor:'rgba(20,184,166,.08)',fill:true,tension:.35},
       {label:'هزینه',data:months.map(m=>m.expenses),borderColor:palette[5],tension:.35}
     ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true}}}})}
     const years=this.jalaliYearlyMetrics||[],cy=document.getElementById('yearlyChart');
     if(cy){this.yearlyChart?.destroy?.();this.yearlyChart=new Chart(cy,{type:'bar',data:{labels:years.map(y=>faDigits(y.year)),datasets:[
       {label:'دریافتی',data:years.map(y=>y.received),backgroundColor:palette[1],borderRadius:10},
       {label:'سود خالص',data:years.map(y=>y.net_profit),backgroundColor:palette[3],borderRadius:10}
     ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true}}}})}
     const types=this.analytics?.service_types||[],cs=document.getElementById('serviceChart');
     if(cs){this.serviceChart?.destroy?.();this.serviceChart=new Chart(cs,{type:'doughnut',data:{labels:types.map(x=>x.service_type||'نامشخص'),datasets:[{data:types.map(x=>x.received),backgroundColor:palette,borderWidth:0,hoverOffset:10}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{legend:{position:'bottom'}}}})}
     const ce=document.getElementById('expensePolarChart'),cats=this.insights?.expense_categories||[];
     if(ce){this.expensePolarChart?.destroy?.();this.expensePolarChart=new Chart(ce,{type:'polarArea',data:{labels:cats.map(x=>this.expenseCategory?.(x.category)||x.category||'سایر'),datasets:[{data:cats.map(x=>x.amount),backgroundColor:palette.map(x=>x+'cc'),borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}}}})}
   };

   s.renderInvoicePng=async function(){
     const source=document.getElementById('invoicePaper');if(!source)throw Error('پیش‌نمایش فاکتور آماده نیست');
     if(!window.html2canvas){
       await new Promise((resolve,reject)=>{const sc=document.createElement('script');sc.src='/vendor/html2canvas-1.4.1.min.js';sc.onload=resolve;sc.onerror=reject;document.head.appendChild(sc)});
     }
     await document.fonts?.ready;
     const holder=document.createElement('div');holder.className='aq-invoice-export-holder';
     const clone=source.cloneNode(true);clone.id='invoicePaperExport';clone.classList.add('aq-invoice-export');
     holder.appendChild(clone);document.body.appendChild(holder);
     try{
       const canvas=await html2canvas(clone,{scale:2,backgroundColor:'#ffffff',useCORS:true,logging:false,width:760,windowWidth:800,scrollX:0,scrollY:0});
       return await new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('ساخت تصویر فاکتور ناموفق بود')),'image/png',.98));
     }finally{holder.remove()}
   };

   const originalInit=s.init?.bind(s);
   s.init=async function(){
     await originalInit?.();
     if(this.token){
       this.syncPhonePush?.();
       setTimeout(()=>{document.querySelectorAll('.aq-float').forEach(x=>x.remove())},0);
     }
   };
   return s;
 };

 const prepareStaticUI=()=>{
   document.querySelectorAll('.aq-float').forEach(x=>x.remove());

   const service=document.getElementById('serviceChart');
   const grid=service?.closest('.grid');
   if(grid&&!document.getElementById('expensePolarChart')){
     const card=document.createElement('div');card.className='card p-5';
     card.innerHTML='<h3 class="font-black mb-3">ترکیب هزینه‌ها</h3><div class="aq-chart-height"><canvas id="expensePolarChart"></canvas></div>';
     grid.appendChild(card);
   }
   document.querySelectorAll('#monthlyChart,#yearlyChart,#serviceChart').forEach(c=>{const p=c.parentElement;if(p&&!p.querySelector('.aq-chart-height')){c.style.height='300px'}});

   const settings=[...document.querySelectorAll('section')].find(x=>(x.getAttribute('x-show')||'').includes("page==='settings'"));
   if(settings&&!document.getElementById('aq-push-settings')){
     const card=document.createElement('div');card.id='aq-push-settings';card.className='card p-5';
     card.innerHTML=`<div class="flex items-start justify-between gap-3"><div><h3 class="section-title">اعلان کار جدید روی گوشی</h3><p class="text-sm muted mt-1">بعد از رسیدن کار جدید از بله، حتی وقتی AquaGold در پس‌زمینه است اعلان PWA دریافت کن.</p></div><span class="chip bg-cyan-500/10 text-cyan-600" x-text="pushStatus"></span></div>
       <div class="grid sm:grid-cols-3 gap-2 mt-4"><button type="button" class="btn primary" @click="enablePhonePush">فعال‌سازی</button><button type="button" class="btn soft" @click="testPhonePush">تست اعلان</button><button type="button" class="btn bg-red-500/10 text-red-500" @click="disablePhonePush">غیرفعال‌سازی</button></div>
       <div class="text-xs muted mt-3">در آیفون باید AquaGold از طریق Add to Home Screen نصب و از آیکن برنامه باز شود.</div>`;
     settings.appendChild(card);
   }

   const invoiceNew=[...document.querySelectorAll('section')].find(x=>(x.getAttribute('x-show')||'').includes("page==='invoice-new'"));
   if(invoiceNew){
     invoiceNew.classList.add('aq-invoice-new');
     const label=(el,text)=>{
       if(!el||el.dataset.aqLabelled)return;el.dataset.aqLabelled='1';
       const wrap=document.createElement('label');wrap.className='aq-field-box';const title=document.createElement('span');title.className='aq-field-title';title.textContent=text;
       el.parentNode.insertBefore(wrap,el);wrap.append(title,el);
     };
     label(invoiceNew.querySelector('select[x-model="invoiceForm.customer_id"]'),'مشتری');
     label(invoiceNew.querySelector('input[x-model="invoiceForm.discount"]'),'تخفیف');
     label(invoiceNew.querySelector('textarea[x-model="invoiceForm.notes"]'),'توضیحات فاکتور');
     invoiceNew.querySelectorAll('input[x-model="it.title"]').forEach(x=>label(x,'شرح کالا / خدمت'));
     invoiceNew.querySelectorAll('input[x-model="it.quantity"]').forEach(x=>label(x,'تعداد'));
     invoiceNew.querySelectorAll('input[x-model="it.unit_price"]').forEach(x=>label(x,'قیمت واحد (تومان)'));
   }
 };
 const style=document.createElement('style');style.id='aqua-ops-v8-style';style.textContent=`
 .aq-chart-height{height:300px;position:relative}.aq-field-box{display:block;border:1px solid color-mix(in srgb,var(--brand2) 24%,var(--line));border-radius:17px;padding:8px;background:color-mix(in srgb,var(--surface-2) 94%,transparent)}.aq-field-title{display:block;font-size:11px;font-weight:900;color:var(--muted);padding:0 5px 5px}.aq-field-box>.field{border:0!important;box-shadow:none!important;padding-top:.55rem;padding-bottom:.55rem;background:transparent!important}.aq-invoice-new .rounded-2xl.border{border-color:color-mix(in srgb,var(--brand2) 28%,var(--line))!important;background:color-mix(in srgb,var(--surface-2) 96%,transparent)}.invoice-table{table-layout:fixed}.invoice-table th,.invoice-table td{word-break:break-word}.aq-invoice-export-holder{position:fixed;left:-10000px;top:0;width:800px;background:#fff;z-index:-1}.aq-invoice-export{width:760px!important;min-height:1075px!important;max-width:760px!important;border-radius:0!important;box-shadow:none!important;overflow:visible!important}.aq-invoice-export .invoice-body{padding:28px 32px!important}.aq-invoice-export .invoice-table{width:100%!important;table-layout:fixed!important}.aq-invoice-export .overflow-x-auto{overflow:visible!important}.aq-invoice-export .grid{min-width:0!important}@media(max-width:640px){.aq-field-box{padding:7px}.aq-chart-height{height:260px}}@media print{@page{size:A4 portrait;margin:10mm}body.invoice-print #invoicePaper{width:190mm!important;max-width:190mm!important;margin:auto!important}}
 `;
 document.head.appendChild(style);
 prepareStaticUI();
 new MutationObserver(()=>{document.querySelectorAll('.aq-float').forEach(x=>x.remove());prepareStaticUI()}).observe(document.body,{childList:true,subtree:true});
})();
"""


@app.get("/aqua-ops-v8.js")
def aqua_ops_v8_js():
    return Response(RUNTIME_JS, mimetype="application/javascript", headers={"Cache-Control": "no-store, max-age=0"})


@app.after_request
def inject_aqua_ops_v8(response):
    try:
        if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
            response.direct_passthrough = False
            body = response.get_data(as_text=True)
            body = body.replace('<script src="/vendor/leaflet-1.9.4.js"></script>', '<script defer src="/vendor/leaflet-1.9.4.js"></script>')
            body = body.replace('<script src="/vendor/chart-4.4.7.min.js"></script>', '<script defer src="/vendor/chart-4.4.7.min.js"></script>')
            if "/aqua-ops-v8.js" not in body:
                body = body.replace("</body>", '<script src="/aqua-ops-v8.js?v=20260831-1"></script></body>', 1)
            response.set_data(body)
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app.logger.warning("inject_aqua_ops_v8_failed: %s", exc)
    return response
