(()=>{
  if(window.__aquaRound5UserFixes)return;
  window.__aquaRound5UserFixes=true;

  const clean=value=>String(value??'').trim();
  const paymentKey=value=>{
    const method=clean(value).toLowerCase().replace(/\u200c/g,' ');
    if(method==='cash'||method.includes('نقد'))return'cash';
    if(method==='transfer'||/کارت\s*به\s*کارت|card.?to.?card/.test(method))return'transfer';
    if(method==='card'||method==='pos'||/کارت\s*خوان|کارتخوان|card.?reader/.test(method))return'card';
    return'other';
  };
  const pickMime=()=>{
    for(const value of ['audio/mp4','audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus']){
      try{if(window.MediaRecorder?.isTypeSupported?.(value))return value}catch{}
    }
    return'';
  };

  const patchSmartDuplicates=()=>{
    const section=[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='smart'"));
    if(!section)return;
    for(const model of ['smartParsed.service_type','smartParsed.payment_method']){
      const input=section.querySelector(`input[x-model="${model}"]`);
      input?.closest('label')?.remove();
    }
  };

  const patchDailyMarkup=()=>{
    const section=[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='daily'"));
    if(!section||section.dataset.aquaRound5Daily)return;
    section.dataset.aquaRound5Daily='1';
    section.className='space-y-4';
    section.innerHTML=`
      <div class="flex flex-col md:flex-row md:justify-between gap-3">
        <div><h2 class="section-title">گزارش روزانه شمسی</h2><p class="text-sm muted">انجام‌شده‌ها، کنسلی‌ها و جمع مالی هر روز</p></div>
        <div class="flex gap-2 no-print"><button type="button" @click="copyAllDaily" class="btn soft flex items-center gap-2"><span x-html="icon('copy')"></span><span>کپی همه</span></button><button type="button" @click="printPdf" class="btn glass flex items-center gap-2"><span x-html="icon('print')"></span><span>چاپ / PDF</span></button></div>
      </div>
      <template x-for="d in dailyGroups" :key="d.iso">
        <article class="card overflow-hidden mb-4">
          <div class="p-4 md:p-5 flex justify-between items-center" style="background:linear-gradient(135deg,rgba(8,123,121,.08),rgba(48,197,210,.04))">
            <div><b class="text-lg" x-text="persianDate(d.iso)"></b><div class="text-xs muted" x-text="d.completedCount+' انجام‌شده • '+d.cancelledCount+' کنسل‌شده'"></div></div>
            <button type="button" @click="copyDay(d)" class="btn glass !py-2 flex items-center gap-2"><span x-html="icon('copy')"></span><span>کپی</span></button>
          </div>
          <div x-show="d.completedJobs.length">
            <div class="px-4 pt-4 pb-1 text-xs font-black text-emerald-500">انجام‌شده‌ها</div>
            <template x-for="j in d.completedJobs" :key="'done-'+j.id"><div class="px-4 py-3 border-b flex justify-between gap-3" style="border-color:var(--line)"><b x-text="dailySurname(j)"></b><b class="text-emerald-500" x-text="money(j.received_amount)+' تومان'"></b></div></template>
          </div>
          <div x-show="d.cancelledJobs.length">
            <div class="px-4 pt-4 pb-1 text-xs font-black text-red-500">کنسل‌شده‌ها</div>
            <template x-for="j in d.cancelledJobs" :key="'cancel-'+j.id"><div class="px-4 py-3 border-b grid grid-cols-[auto_1fr] gap-3" style="border-color:var(--line)"><b x-text="dailySurname(j)"></b><span class="text-sm text-red-500 text-left" x-text="j.cancel_reason||'علت ثبت نشده'"></span></div></template>
          </div>
          <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2 p-4">
            <div class="rounded-2xl p-3 bg-teal-500/10"><small class="muted">دریافتی</small><b class="block" x-text="money(d.received)"></b></div>
            <div class="rounded-2xl p-3 bg-cyan-500/10"><small class="muted">سهم شرکت</small><b class="block" x-text="money(d.company_share)"></b></div>
            <div class="rounded-2xl p-3 bg-amber-500/10"><small class="muted">هزینه</small><b class="block" x-text="money(d.expenses)"></b></div>
            <div class="rounded-2xl p-3 bg-red-500/10"><small class="muted">مانده</small><b class="block" x-text="money(d.customer_balance)"></b></div>
            <div class="rounded-2xl p-3 bg-blue-500/10"><small class="muted">تعداد کارها</small><b class="block" x-text="d.completedCount+' انجام‌شده'"></b><span class="text-xs text-red-500" x-text="d.cancelledCount+' کنسلی'"></span></div>
            <div class="rounded-2xl p-3 bg-emerald-500/10"><small class="muted">سود خالص</small><b class="block text-emerald-600" x-text="money(d.net_profit)"></b></div>
          </div>
        </article>
      </template>
      <div x-show="!dailyGroups.length" class="card empty"><div class="empty-icon" x-html="icon('daily')"></div><b>گزارشی برای نمایش نیست</b></div>`;
  };

  patchSmartDuplicates();
  patchDailyMarkup();

  const previous=window.app;
  if(typeof previous!=='function')return;
  window.app=function(){
    const state=previous();
    const baseFinance=state.renderRound4Finance?.bind(state);
    const baseToggleRecording=state.toggleAquaRecording?.bind(state);
    const oldGo=state.go;

    state.aquaDailyCancelled=[];
    state.aquaDailyCancelledLoaded=false;
    state.aquaFinanceRenderPromise=null;
    state.paymentMethodChart=null;

    state.dailySurname=function(row){
      const explicit=clean(row?.last_name);if(explicit)return explicit;
      const value=clean(row?.name||row?.customer_name);if(!value)return'بدون نام';
      const parts=value.split(/\s+/).filter(Boolean);return parts[parts.length-1]||value;
    };

    state.loadAquaDailyCancelled=async function(){
      try{
        const rows=await this.api('/bale/jobs?status=cancelled&_='+Date.now());
        this.aquaDailyCancelled=Array.isArray(rows)?rows:[];
        this.aquaDailyCancelledLoaded=true;
      }catch(error){
        console.warn('Aqua daily cancellations unavailable',error);
        if(!this.aquaDailyCancelledLoaded)this.aquaDailyCancelled=[];
      }
      return this.aquaDailyCancelled;
    };

    Object.defineProperty(state,'dailyGroups',{configurable:true,get(){
      const by={};
      const ensure=(key,stamp)=>{
        if(!key)return null;
        if(!by[key])by[key]={iso:key,completedJobs:[],cancelledJobs:[],jobs:[],services:0,completedCount:0,cancelledCount:0,received:0,company_share:0,customer_balance:0,expenses:0,net_profit:0,sort:stamp||0};
        by[key].sort=Math.max(Number(by[key].sort||0),Number(stamp||0));
        return by[key];
      };
      for(const job of (this.jobs||[])){
        const status=clean(job?.status).toLowerCase();
        if(status==='cancelled'||status==='scheduled')continue;
        const when=job?.date||job?.visited_at||job?.created_at;if(!when)continue;
        let key='';try{key=this.tehranDay(when)}catch{continue}
        const stamp=new Date(when).getTime()||0,row=ensure(key,stamp);if(!row)continue;
        row.completedJobs.push(job);row.jobs.push(job);row.completedCount++;row.services++;
        row.received+=Number(job?.received_amount||0);row.company_share+=Number(job?.company_share_amount||0);row.customer_balance+=Number(job?.customer_balance||0);
      }
      for(const item of (this.aquaDailyCancelled||[])){
        const when=item?.cancelled_at||item?.updated_at||item?.received_at;if(!when)continue;
        let key='';try{key=this.tehranDay(when)}catch{continue}
        const stamp=new Date(when).getTime()||0,row=ensure(key,stamp);if(!row)continue;
        row.cancelledJobs.push(item);row.cancelledCount++;
      }
      for(const expense of (this.expenses||[])){
        const when=expense?.expense_date;if(!when)continue;
        let key='';try{key=this.tehranDay(when)}catch{continue}
        const stamp=new Date(when).getTime()||0,row=ensure(key,stamp);if(!row)continue;
        row.expenses+=Number(expense?.amount||0);
      }
      for(const row of Object.values(by))row.net_profit=row.received-row.company_share-row.expenses;
      return Object.values(by).sort((a,b)=>b.sort-a.sort);
    }});

    state.dayReportText=function(d){
      const lines=[`📅 ${this.persianDate(d.iso)}`,'✅ انجام‌شده‌ها'];
      (d.completedJobs||[]).forEach((j,i)=>lines.push(`${i+1}) ${this.dailySurname(j)} — ${this.money(j.received_amount)} تومان`));
      if(!(d.completedJobs||[]).length)lines.push('—');
      lines.push('❌ کنسل‌شده‌ها');
      (d.cancelledJobs||[]).forEach((j,i)=>lines.push(`${i+1}) ${this.dailySurname(j)} — ${j.cancel_reason||'علت ثبت نشده'}`));
      if(!(d.cancelledJobs||[]).length)lines.push('—');
      lines.push(`دریافتی: ${this.money(d.received)} تومان`,`سهم شرکت: ${this.money(d.company_share)} تومان`,`هزینه: ${this.money(d.expenses)} تومان`,`مانده: ${this.money(d.customer_balance)} تومان`,`تعداد: ${d.completedCount} انجام‌شده • ${d.cancelledCount} کنسلی`,`سود خالص: ${this.money(d.net_profit)} تومان`);
      return lines.join('\n');
    };

    const localPaymentTotals=function(){
      const totals={cash:0,transfer:0,card:0,other:0};
      for(const job of (this.jobs||[]))totals[paymentKey(job?.payment_method)]+=Number(job?.received_amount||0);
      return totals;
    };
    state.renderAquaPaymentOnly=async function(){
      try{await this.loadAquaPaymentBreakdown?.()}catch{}
      let totals=this.aquaPaymentBreakdown||this.paymentMethodTotals?.()||null;
      const local=localPaymentTotals.call(this);
      if(!totals||(['cash','transfer','card'].every(key=>Number(totals?.[key]||0)===0)&&['cash','transfer','card'].some(key=>Number(local[key]||0)>0)))totals=local;
      totals={cash:Number(totals?.cash||0),transfer:Number(totals?.transfer||0),card:Number(totals?.card||0),other:Number(totals?.other||0)};
      for(const key of ['cash','transfer','card','other']){
        const el=document.querySelector(`[data-aqua-payment-total="${key}"]`);if(el)el.textContent=this.money(totals[key])+' تومان';
      }
      const canvas=document.getElementById('paymentMethodChart');if(!canvas||!window.Chart)return totals;
      try{window.Chart.getChart?.(canvas)?.destroy?.()}catch{}
      try{this.paymentMethodChart?.destroy?.()}catch{}
      this.paymentMethodChart=new Chart(canvas,{type:'doughnut',data:{labels:['نقد','کارت به کارت','کارتخوان','سایر'],datasets:[{data:[totals.cash,totals.transfer,totals.card,totals.other],backgroundColor:['#22c55e','#3b82f6','#8b5cf6','#f59e0b'],borderWidth:0,hoverOffset:7}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',animation:false,plugins:{legend:{position:'bottom',labels:{usePointStyle:true,boxWidth:12}}}}});
      return totals;
    };

    state.renderAquaShareCharts=function(){
      if(!window.Chart)return;
      const colors={cyan:'#22d3ee',violet:'#8b5cf6',amber:'#f59e0b',teal:'#2dd4bf',rose:'#f43f5e',blue:'#38bdf8'};
      const legend={position:'bottom',labels:{usePointStyle:true,boxWidth:12}};
      const totals=this.analytics?.totals||{};
      const donut=document.getElementById('financeDonutChart');
      if(donut){
        try{window.Chart.getChart?.(donut)?.destroy?.()}catch{}
        try{this.financeDonutChart?.destroy?.()}catch{}
        this.financeDonutChart=new Chart(donut,{type:'doughnut',data:{labels:['سهم شرکت','هزینه‌ها','سود خالص'],datasets:[{data:[Math.max(Number(totals.company_share||0),0),Math.max(Number(totals.expenses||0),0),Math.max(Number(totals.net_profit||0),0)],backgroundColor:[colors.cyan,colors.amber,colors.violet],borderWidth:0,hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,cutout:'66%',animation:false,plugins:{legend}}});
      }
      const types=this.analytics?.service_types||[];
      const polar=document.getElementById('financePolarChart');
      if(polar){
        try{window.Chart.getChart?.(polar)?.destroy?.()}catch{}
        try{this.financePolarChart?.destroy?.()}catch{}
        this.financePolarChart=new Chart(polar,{type:'polarArea',data:{labels:types.slice(0,6).map(x=>x.service_type||'نامشخص'),datasets:[{data:types.slice(0,6).map(x=>Number(x.received||0)),backgroundColor:['#2dd4bfaa','#22d3eeaa','#8b5cf6aa','#f59e0baa','#f43f5eaa','#38bdf8aa'],borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend}}});
      }
    };
    state.renderRound4Finance=async function(){
      if(this.aquaFinanceRenderPromise)return this.aquaFinanceRenderPromise;
      const operation=(async()=>{
        try{await baseFinance?.()}catch(error){console.warn('Aqua finance base render recovered',error)}
        try{this.renderAquaShareCharts?.()}catch(error){console.warn('Aqua share charts recovered',error)}
        try{return await this.renderAquaPaymentOnly()}catch(error){console.warn('Aqua payment render failed',error);return null}
      })();
      this.aquaFinanceRenderPromise=operation;
      try{return await operation}finally{if(this.aquaFinanceRenderPromise===operation)this.aquaFinanceRenderPromise=null}
    };
    state.renderCharts=function(){return this.renderRound4Finance?.()};

    state.go=async function(page,...args){
      const result=await oldGo?.apply(this,[page,...args]);
      if(page==='daily')await this.loadAquaDailyCancelled?.();
      return result;
    };

    if(window.webkitSpeechRecognition||window.SpeechRecognition){
      return state;
    }
    state.toggleAquaRecording=async function(){
      if(typeof baseToggleRecording==='function')return await baseToggleRecording();
      this.toast?.('ضبط صدا آماده نیست','error');
    };

    return state;
  };
})();
