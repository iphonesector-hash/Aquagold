(()=>{
  if(window.__aquaSystemPolishLoaded)return;
  window.__aquaSystemPolishLoaded=true;
  const previous=window.app;
  if(typeof previous!=='function')return;

  const FA='۰۱۲۳۴۵۶۷۸۹';
  const palette=['#22d3ee','#3b82f6','#8b5cf6','#14b8a6','#f59e0b','#f43f5e','#84cc16','#06b6d4'];
  const fa=v=>String(v??'').replace(/\d/g,d=>FA[Number(d)]);
  const pad=n=>String(n).padStart(2,'0');
  const urlKeyToBytes=s=>{
    const p='='.repeat((4-s.length%4)%4);
    const raw=atob((s+p).replace(/-/g,'+').replace(/_/g,'/'));
    return Uint8Array.from([...raw],c=>c.charCodeAt(0));
  };
  const jalaliParts=value=>{
    const d=value instanceof Date?value:new Date(value);
    const parts=new Intl.DateTimeFormat('en-US-u-ca-persian',{timeZone:'Asia/Tehran',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(d);
    const out={};
    for(const p of parts)if(['year','month','day'].includes(p.type))out[p.type]=Number(p.value);
    return out;
  };
  const jalaliNumeric=value=>{
    const p=jalaliParts(value);
    return `\u2066${fa(p.year)}/${fa(pad(p.month))}/${fa(pad(p.day))}\u2069`;
  };
  const weekday=value=>new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',weekday:'long'}).format(new Date(value));
  const clock=value=>new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));
  const cleanupFloat=()=>document.querySelectorAll('.aq-float').forEach(el=>el.remove());
  const loadHtml2Canvas=()=>new Promise((resolve,reject)=>{
    if(window.html2canvas)return resolve();
    const existing=[...document.scripts].find(x=>x.src.includes('html2canvas-1.4.1'));
    if(existing){existing.addEventListener('load',resolve,{once:true});existing.addEventListener('error',reject,{once:true});return;}
    const s=document.createElement('script');s.src='/vendor/html2canvas-1.4.1.min.js';s.onload=resolve;s.onerror=reject;document.head.appendChild(s);
  });

  window.app=function(){
    const s=previous();
    Object.assign(s,{pushBusy:false,pushActive:false,pushPermission:(window.Notification?.permission||'default'),financePolarChart:null});

    // Prevent duplicate simultaneous full refreshes from stacked legacy wrappers.
    if(typeof s.refreshAll==='function'){
      const original=s.refreshAll.bind(s);let inflight=null;
      s.refreshAll=async function(){
        if(inflight)return inflight;
        inflight=Promise.resolve(original()).finally(()=>{inflight=null});
        return inflight;
      };
    }

    // Commerce data is heavy and was loading on every startup. Load it only when commerce is opened.
    if(typeof s.refreshCommerce==='function'){
      const original=s.refreshCommerce.bind(s);let inflight=null;
      s.refreshCommerce=async function(force=false){
        const pages=['products','product-edit','invoices','invoice-new','invoice-view'];
        if(!force&&!pages.includes(this.page))return;
        if(inflight)return inflight;
        inflight=Promise.resolve(original()).finally(()=>{inflight=null});
        return inflight;
      };
    }

    s.persianDate=function(v){
      if(!v)return'';
      const d=/^\d{4}-\d{2}-\d{2}$/.test(String(v))?new Date(String(v)+'T12:00:00+03:30'):new Date(v);
      return `${weekday(d)} • ${jalaliNumeric(d)}`;
    };
    s.persianDateTime=function(v){
      if(!v)return'';
      try{return `${jalaliNumeric(v)} • ${clock(v)}`}catch{return String(v)}
    };

    s.refreshPushStatus=async function(){
      this.pushPermission=window.Notification?.permission||'unsupported';
      if(!('serviceWorker'in navigator)||!('PushManager'in window)){this.pushActive=false;return}
      try{const reg=await navigator.serviceWorker.ready;this.pushActive=!!(await reg.pushManager.getSubscription())}catch{this.pushActive=false}
    };
    s.enableAquaPush=async function(){
      if(this.pushBusy)return;
      if(!('serviceWorker'in navigator)||!('PushManager'in window)||!window.Notification)return this.toast?.('اعلان Push روی این مرورگر پشتیبانی نمی‌شود','error');
      const ios=/iPhone|iPad|iPod/i.test(navigator.userAgent);
      const standalone=window.matchMedia?.('(display-mode: standalone)').matches||navigator.standalone===true;
      if(ios&&!standalone)return this.toast?.('در آیفون ابتدا AquaGold را با Add to Home Screen نصب کن و از آیکن برنامه باز کن.','info');
      this.pushBusy=true;
      try{
        const permission=await Notification.requestPermission();this.pushPermission=permission;
        if(permission!=='granted')throw Error('اجازه نوتیفیکیشن داده نشد');
        const key=await this.api('/push/public-key');
        const reg=await navigator.serviceWorker.ready;
        let sub=await reg.pushManager.getSubscription();
        if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:urlKeyToBytes(key.public_key)});
        await this.api('/push/subscribe',{method:'POST',body:JSON.stringify(sub.toJSON())});
        this.pushActive=true;this.toast?.('اعلان کارهای جدید روی این گوشی فعال شد','success');
      }catch(e){this.toast?.(e.message||'فعال‌سازی اعلان انجام نشد','error')}
      finally{this.pushBusy=false}
    };
    s.disableAquaPush=async function(){
      if(this.pushBusy)return;this.pushBusy=true;
      try{
        const reg=await navigator.serviceWorker.ready,sub=await reg.pushManager.getSubscription();
        if(sub){await this.api('/push/subscribe',{method:'DELETE',body:JSON.stringify({endpoint:sub.endpoint})});await sub.unsubscribe()}
        this.pushActive=false;this.toast?.('اعلان این گوشی غیرفعال شد','info');
      }catch(e){this.toast?.(e.message||'غیرفعال‌سازی اعلان انجام نشد','error')}
      finally{this.pushBusy=false}
    };
    s.sendFinanceBaleImage=async function(){
      if(this.pushBusy)return;this.pushBusy=true;
      try{const r=await this.api('/reports/finance-image/send',{method:'POST',body:'{}'});if(!r.ok)throw Error(r.error||'ارسال تصویر انجام نشد');this.toast?.('گزارش تصویری مالی به چت خصوصی بله ارسال شد','success')}
      catch(e){this.toast?.(e.message||'ارسال گزارش تصویری انجام نشد','error')}
      finally{this.pushBusy=false}
    };

    s.renderCharts=function(){
      if(!window.Chart)return;
      const months=this.jalaliMonthlyMetrics||[],labels=months.map(m=>fa(m.label));
      const c1=document.getElementById('monthlyChart');
      if(c1){this.monthlyChart?.destroy?.();this.monthlyChart=new Chart(c1,{type:'line',data:{labels,datasets:[
        {label:'دریافتی',data:months.map(m=>m.received),borderColor:palette[0],backgroundColor:'rgba(34,211,238,.16)',fill:true,tension:.38,pointRadius:3},
        {label:'سود خالص',data:months.map(m=>m.net_profit),borderColor:palette[3],backgroundColor:'rgba(20,184,166,.10)',fill:true,tension:.38,pointRadius:3},
        {label:'هزینه',data:months.map(m=>m.expenses),borderColor:palette[5],tension:.38,pointRadius:3}
      ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true}}}})}
      const years=this.jalaliYearlyMetrics||[],cy=document.getElementById('yearlyChart');
      if(cy){this.yearlyChart?.destroy?.();this.yearlyChart=new Chart(cy,{type:'bar',data:{labels:years.map(y=>fa(y.year)),datasets:[
        {label:'دریافتی',data:years.map(y=>y.received),backgroundColor:palette[1],borderRadius:10},
        {label:'سود خالص',data:years.map(y=>y.net_profit),backgroundColor:palette[3],borderRadius:10}
      ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true}}}})}
      const types=this.analytics?.service_types||[],cs=document.getElementById('serviceChart');
      if(cs){this.serviceChart?.destroy?.();this.serviceChart=new Chart(cs,{type:'doughnut',data:{labels:types.map(x=>x.service_type||'نامشخص'),datasets:[{data:types.map(x=>x.received),backgroundColor:palette,borderWidth:0,hoverOffset:10}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{legend:{position:'bottom'}}}})}
      const cats=this.insights?.expense_categories||[],cp=document.getElementById('expensePolarChart');
      if(cp){this.financePolarChart?.destroy?.();this.financePolarChart=new Chart(cp,{type:'polarArea',data:{labels:cats.map(x=>this.expenseCategory?.(x.category)||x.category||'سایر'),datasets:[{data:cats.map(x=>x.amount),backgroundColor:palette.map(x=>x+'cc'),borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}}}})}
    };

    s.renderInvoicePng=async function(){
      const source=document.getElementById('invoicePaper');if(!source)throw Error('پیش‌نمایش فاکتور آماده نیست');
      await loadHtml2Canvas();await document.fonts?.ready;
      const holder=document.createElement('div');holder.className='aq-invoice-export-holder';
      const clone=source.cloneNode(true);clone.id='invoicePaperExport';clone.classList.add('aq-invoice-export');holder.appendChild(clone);document.body.appendChild(holder);
      try{
        const canvas=await window.html2canvas(clone,{scale:2,backgroundColor:'#ffffff',useCORS:true,logging:false,width:760,windowWidth:800,scrollX:0,scrollY:0});
        return await new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('ساخت تصویر فاکتور ناموفق بود')),'image/png',.98));
      }finally{holder.remove()}
    };

    const decorateFinance=()=>{
      const service=document.getElementById('serviceChart');if(!service)return;
      [document.getElementById('monthlyChart'),document.getElementById('yearlyChart'),service].filter(Boolean).forEach(c=>{c.parentElement?.classList.add('aq-chart-height')});
      const grid=service.closest('.grid');
      if(grid&&!document.getElementById('expensePolarChart')){
        const card=document.createElement('div');card.className='card p-5';card.innerHTML='<h3 class="font-black mb-3">ترکیب هزینه‌ها</h3><div class="aq-chart-height"><canvas id="expensePolarChart"></canvas></div>';grid.appendChild(card);
      }
    };
    const decorateSettings=()=>{
      const sec=[...document.querySelectorAll('section')].find(x=>(x.getAttribute('x-show')||'').includes("page==='settings'"));
      if(!sec||document.getElementById('aq-push-card'))return;
      const card=document.createElement('div');card.id='aq-push-card';card.className='card p-5';
      card.innerHTML=`<div class="flex items-start justify-between gap-3"><div><h3 class="section-title">اعلان کار جدید روی گوشی</h3><p class="text-sm muted mt-1">با رسیدن کار جدید از بله، روی گوشی اعلان واقعی PWA دریافت کن.</p></div><span class="chip" x-text="pushActive?'فعال':'غیرفعال'"></span></div><div class="grid sm:grid-cols-2 gap-2 mt-4"><button type="button" class="btn primary" @click="enableAquaPush" :disabled="pushBusy">فعال‌سازی اعلان</button><button type="button" class="btn soft" @click="disableAquaPush" :disabled="pushBusy">غیرفعال‌سازی</button></div><p class="text-xs muted mt-3">در آیفون، برنامه باید از Home Screen اجرا شود.</p>`;
      sec.appendChild(card);window.Alpine?.initTree?.(card);
    };
    const labelField=(el,title)=>{
      if(!el||el.dataset.aqLabelled)return;el.dataset.aqLabelled='1';
      const box=document.createElement('label');box.className='aq-field-box';const t=document.createElement('span');t.className='aq-field-title';t.textContent=title;
      el.parentNode.insertBefore(box,el);box.append(t,el);
    };
    const decorateInvoice=()=>{
      const sec=[...document.querySelectorAll('section')].find(x=>(x.getAttribute('x-show')||'').includes("page==='invoice-new'"));if(!sec)return;
      sec.classList.add('aq-invoice-new');
      labelField(sec.querySelector('select[x-model="invoiceForm.customer_id"]'),'مشتری');
      labelField(sec.querySelector('input[x-model="invoiceForm.discount"]'),'تخفیف (تومان)');
      labelField(sec.querySelector('textarea[x-model="invoiceForm.notes"]'),'توضیحات فاکتور');
      sec.querySelectorAll('input[x-model="it.title"]').forEach(x=>labelField(x,'شرح کالا / خدمت'));
      sec.querySelectorAll('input[x-model="it.quantity"]').forEach(x=>labelField(x,'تعداد'));
      sec.querySelectorAll('input[x-model="it.unit_price"]').forEach(x=>labelField(x,'قیمت واحد (تومان)'));
    };

    if(typeof s.mountEnhancements==='function'){
      const original=s.mountEnhancements.bind(s);
      s.mountEnhancements=function(){const r=original();cleanupFloat();return r};
    }
    if(typeof s.mountCommerce==='function'){
      const original=s.mountCommerce.bind(s);
      s.mountCommerce=function(){const r=original();decorateInvoice();return r};
    }
    if(typeof s.go==='function'){
      const original=s.go.bind(s);
      s.go=async function(p){const r=await original(p);cleanupFloat();if(p==='finance'){decorateFinance();setTimeout(()=>this.renderCharts(),20)}if(p==='settings'){decorateSettings();this.refreshPushStatus?.()}if(['invoice-new','invoice-view'].includes(p))decorateInvoice();return r};
    }
    if(typeof s.init==='function'){
      const original=s.init.bind(s);
      s.init=async function(){const r=await original();cleanupFloat();if(this.token){this.refreshPushStatus?.();decorateSettings();setTimeout(cleanupFloat,180)}return r};
    }
    return s;
  };

  const style=document.createElement('style');style.id='aqua-system-polish-style';style.textContent=`
    .aq-chart-height{height:300px;position:relative}.aq-field-box{display:block;border:1px solid color-mix(in srgb,var(--brand2) 26%,var(--line));border-radius:17px;padding:8px;background:color-mix(in srgb,var(--surface-2) 95%,transparent)}.aq-field-title{display:block;font-size:11px;font-weight:900;color:var(--muted);padding:0 5px 5px}.aq-field-box>.field{border:0!important;box-shadow:none!important;padding-top:.55rem;padding-bottom:.55rem;background:transparent!important}.aq-invoice-new .rounded-2xl.border{border-color:color-mix(in srgb,var(--brand2) 30%,var(--line))!important;background:color-mix(in srgb,var(--surface-2) 96%,transparent)}.invoice-paper{border:1px solid #d8e5e8!important}.invoice-body>div{min-width:0}.invoice-table{table-layout:fixed}.invoice-table th,.invoice-table td{word-break:break-word;border:1px solid #e4edef}.invoice-table th{background:#eefafa}.invoice-total{border:1px solid #d4ebea}.aq-invoice-export-holder{position:fixed;left:-10000px;top:0;width:800px;background:#fff;z-index:-1}.aq-invoice-export{width:760px!important;max-width:760px!important;min-height:1075px!important;border-radius:0!important;box-shadow:none!important;overflow:visible!important}.aq-invoice-export .invoice-body{padding:28px 32px!important}.aq-invoice-export .overflow-x-auto{overflow:visible!important}.aq-invoice-export .invoice-table{width:100%!important;table-layout:fixed!important}@media(max-width:640px){.aq-chart-height{height:260px}.aq-field-box{padding:7px}}@media print{@page{size:A4 portrait;margin:10mm}body.invoice-print #invoicePaper{width:190mm!important;max-width:190mm!important;margin:auto!important}}
  `;document.head.appendChild(style);
})();
