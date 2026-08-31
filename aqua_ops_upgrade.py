"""Focused AquaGold upgrade: new Bale-job phone alerts + richer finance visuals."""
from __future__ import annotations

from flask import jsonify, request

import app_v3
import bale_bridge

app = app_v3.app

FINANCE_SCRIPT = r'''
(()=>{
 const fa=n=>new Intl.NumberFormat('fa-IR').format(Number(n||0));
 const toast=(title,body)=>{try{if(Notification.permission==='granted')new Notification(title,{body,icon:'/assets/aquagold-icon-192.png',tag:'aquagold-new-bale-job'});}catch(e){}};
 async function askNotify(){
   if(!('Notification' in window))return;
   if(Notification.permission==='default')try{await Notification.requestPermission();}catch(e){}
 }
 let last=null;
 async function pollJobs(){
   if(document.visibilityState!=='visible' && Notification.permission!=='granted')return;
   try{
    const r=await fetch('/api/bale/jobs/counts',{credentials:'include'}); if(!r.ok)return;
    const d=await r.json(); const current=Number(d.new||0)+Number(d.review||0);
    if(last!==null && current>last) toast('کار جدید AquaGold',`${fa(current-last)} کار جدید از بله دریافت شد`);
    last=current;
   }catch(e){}
 }
 function removeBottom(){document.querySelectorAll('.bottom-nav button').forEach(b=>{const s=[b.textContent,b.title,b.getAttribute('aria-label')].join(' ');if(/جست|اعلان|نوتیف|search|notification/i.test(s))b.remove();});}
 function fixDate(){
   const el=document.getElementById('aqua-jalali-clock'); if(!el)return;
   const now=new Date(); const date=new Intl.DateTimeFormat('fa-IR-u-ca-persian',{timeZone:'Asia/Tehran',weekday:'long',year:'numeric',month:'long',day:'numeric'}).format(now);
   const time=new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit',hour12:false}).format(now);
   el.textContent=`${date} — ساعت ${time}`;
 }
 async function financeCharts(){
   if(!location.hash.includes('finance') && !document.body.innerText.includes('گزارش مالی'))return;
   let host=document.getElementById('aqua-finance-visuals');
   if(host)return;
   try{
    const r=await fetch('/api/reports/insights',{credentials:'include'});if(!r.ok)return;const d=await r.json();
    const anchor=[...document.querySelectorAll('main,section,div')].find(x=>x.children?.length&&/گزارش مالی|مالی/.test(x.textContent||''));if(!anchor)return;
    host=document.createElement('section');host.id='aqua-finance-visuals';host.className='card mt-4 p-4';
    const cats=(d.expense_categories||[]).slice(0,6);const services=(d.service_analysis||[]).slice(0,7);
    const max=Math.max(1,...services.map(x=>Number(x.received||0)));
    host.innerHTML=`<div class="flex items-center justify-between"><div><b>تحلیل تصویری مالی</b><div class="text-xs muted mt-1">ترکیب درآمد خدمات و هزینه‌ها</div></div><span class="chip">زنده</span></div>
    <div class="aq-fin-grid mt-4"><div class="aq-chart-card"><b class="text-sm">درآمد بر اساس خدمت</b><div class="aq-linebars">${services.map(x=>`<div class="aq-bar-row"><span>${x.service_type||'نامشخص'}</span><i style="--w:${Math.max(4,Math.round(Number(x.received||0)/max*100))}%"></i><em>${fa(x.received)} ت</em></div>`).join('')}</div></div>
    <div class="aq-chart-card"><b class="text-sm">ترکیب هزینه‌ها</b><div class="aq-donut" style="--p:${cats.length?Math.min(85,25+cats.length*8):5}%"><span>${fa(cats.reduce((a,x)=>a+Number(x.amount||0),0))}<small>تومان</small></span></div><div class="aq-legend">${cats.map(x=>`<span>● ${x.category||'سایر'}: ${fa(x.amount)}</span>`).join('')}</div></div></div>`;
    anchor.appendChild(host);
   }catch(e){}
 }
 const css=document.createElement('style');css.textContent=`.aq-fin-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}.aq-chart-card{padding:16px;border:1px solid rgba(103,232,249,.16);border-radius:22px;background:linear-gradient(145deg,rgba(15,23,42,.76),rgba(8,47,73,.42))}.aq-linebars{display:grid;gap:10px;margin-top:14px}.aq-bar-row{display:grid;grid-template-columns:88px 1fr auto;gap:8px;align-items:center;font-size:11px}.aq-bar-row i{height:9px;border-radius:99px;background:linear-gradient(90deg,#22d3ee,#3b82f6,#8b5cf6);width:var(--w);box-shadow:0 0 18px rgba(34,211,238,.25)}.aq-bar-row em{font-style:normal;opacity:.8}.aq-donut{width:150px;height:150px;border-radius:50%;margin:18px auto;display:grid;place-items:center;background:conic-gradient(#22d3ee 0 var(--p),#8b5cf6 var(--p) 72%,#f59e0b 72% 88%,rgba(148,163,184,.18) 88%);position:relative}.aq-donut:after{content:'';position:absolute;inset:24px;border-radius:50%;background:#0f172a}.aq-donut span{z-index:1;text-align:center;font-weight:900}.aq-donut small{display:block;font-size:10px;opacity:.65}.aq-legend{display:grid;gap:5px;font-size:11px;opacity:.85}`;document.head.appendChild(css);
 removeBottom();fixDate();askNotify();pollJobs();financeCharts();
 setInterval(pollJobs,45000);setInterval(fixDate,30000);
 new MutationObserver(()=>{removeBottom();financeCharts();}).observe(document.documentElement,{subtree:true,childList:true});
})();
'''


@app.after_request
def aqua_ops_html(response):
    try:
        if request.path not in {'/', '/index.html'} or response.mimetype != 'text/html':
            return response
        response.direct_passthrough=False
        body=response.get_data(as_text=True)
        if 'id="aqua-ops-upgrade"' not in body:
            body=body.replace('</body>', f'<script id="aqua-ops-upgrade">{FINANCE_SCRIPT}</script></body>', 1)
            response.set_data(body)
            response.headers['Cache-Control']='no-store, max-age=0'
    except Exception as exc:
        app.logger.warning('aqua_ops_html_failed: %s', exc)
    return response


# Notify an already-registered private Bale management chat immediately for a newly accepted work message.
_original_webhook=app.view_functions.get('bale_webhook')

def _webhook_with_private_new_job_alert(secret):
    response=app.make_response(_original_webhook(secret))
    try:
        if response.status_code < 300 and response.is_json:
            payload=response.get_json() or {}
            if payload.get('registered'):
                with app_v3.get_db() as db, db.cursor() as cur:
                    cur.execute("select value from app_settings where key='bale_reports'")
                    row=cur.fetchone(); chat_id=str(((row or {}).get('value') or {}).get('chat_id') or '').strip()
                settings=bale_bridge._load_settings()
                if chat_id and settings.get('bot_token'):
                    update=request.get_json(silent=True) or {}
                    _,text,_,_,_=bale_bridge._message_payload(update)
                    bale_bridge._bale_call(settings['bot_token'],'sendMessage',{'chat_id':chat_id,'text':'🔔 کار جدید در AquaGold\n'+str(text)[:1200]},timeout=8)
    except Exception as exc:
        app.logger.warning('private_new_job_alert_failed: %s',exc)
    return response

if _original_webhook is not None:
    app.view_functions['bale_webhook']=_webhook_with_private_new_job_alert
