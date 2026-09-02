(()=>{
  if(window.__aquaRound2Ui)return;
  window.__aquaRound2Ui=true;
  const previous=window.app;
  if(typeof previous!=='function')return;

  const cleanText=value=>String(value??'').trim();
  const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

  window.app=function(){
    const state=previous();
    state.aquaWorkMarkers=[];

    state.normalizeSmartChoices=function(){
      const p=this.smartParsed;
      if(!p)return;
      const service=cleanText(p.service_type).toLowerCase();
      if(service.includes('ساید'))p.service_type='ساید';
      else if(service.includes('فیلتر')||service.includes('دستگاه')||service.includes('یخچال'))p.service_type='فیلتر دستگاه';
      else p.service_type='دیگر';
      const payment=cleanText(p.payment_method).toLowerCase().replace(/‌/g,' ');
      if(/کارت\s*به\s*کارت|transfer|card.?to.?card/.test(payment))p.payment_method='transfer';
      else if(/کارتخوان|کارت\s*خوان|pos|card.?reader/.test(payment))p.payment_method='card';
      else if(/نقد|cash/.test(payment))p.payment_method='cash';
      else p.payment_method='';
    };

    const oldAnalyzeSmart=state.analyzeSmart?.bind(state);
    state.analyzeSmart=async function(){
      const result=await oldAnalyzeSmart?.();
      this.normalizeSmartChoices();
      setTimeout(mountSmartSelectors,0);
      return result;
    };

    state.paymentMethodTotals=function(){
      const totals={cash:0,transfer:0,card:0,other:0};
      for(const job of (this.jobs||[])){
        const amount=Number(job?.received_amount||0);
        const method=cleanText(job?.payment_method).toLowerCase().replace(/‌/g,' ');
        if(method==='cash'||method.includes('نقد'))totals.cash+=amount;
        else if(method==='transfer'||/کارت\s*به\s*کارت/.test(method))totals.transfer+=amount;
        else if(method==='card'||method==='pos'||/کارتخوان|کارت\s*خوان/.test(method))totals.card+=amount;
        else totals.other+=amount;
      }
      return totals;
    };

    state.loadInsightsRequested=async function(){
      try{
        const data=await this.api('/reports/insights?_='+Date.now());
        this.insights={top_customers:[],busy_days:[],expense_categories:[],areas:[],service_analysis:[],...(data||{})};
        return this.insights;
      }catch(error){
        console.warn('Aqua insights refresh failed',error);
        this.toast?.(error?.message||'دریافت بینش‌ها انجام نشد','error');
        return this.insights;
      }
    };

    state.renderRequestedFinanceCharts=function(){
      if(!window.Chart)return;
      mountFinancePaymentUi();
      const totals=this.paymentMethodTotals();
      for(const [key,value] of Object.entries(totals)){
        const el=document.querySelector(`[data-aqua-payment-total="${key}"]`);
        if(el)el.textContent=this.money(value)+' تومان';
      }
      const destroy=name=>{try{this[name]?.destroy?.()}catch{}this[name]=null};
      const monthly=(this.jalaliMonthlyMetrics||[]).slice(-12);
      const yearly=(this.jalaliYearlyMetrics||[]).slice(-6);
      const serviceMap={};
      for(const job of (this.jobs||[])){
        const name=cleanText(job?.service_type)||'دیگر';
        if(!serviceMap[name])serviceMap[name]={name,received:0,count:0};
        serviceMap[name].received+=Number(job?.received_amount||0);
        serviceMap[name].count++;
      }
      const services=Object.values(serviceMap).sort((a,b)=>b.received-a.received).slice(0,10);
      const common={responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{labels:{boxWidth:12,usePointStyle:true}}}};
      const monthlyCanvas=document.getElementById('monthlyChart');
      if(monthlyCanvas){
        destroy('monthlyChart');
        this.monthlyChart=new Chart(monthlyCanvas,{type:'line',data:{labels:monthly.map(x=>x.label),datasets:[
          {label:'دریافتی',data:monthly.map(x=>x.received),borderColor:'#22c55e',backgroundColor:'rgba(34,197,94,.12)',tension:.3,fill:true},
          {label:'سهم شرکت',data:monthly.map(x=>x.company_share),borderColor:'#06b6d4',backgroundColor:'rgba(6,182,212,.08)',tension:.3},
          {label:'هزینه',data:monthly.map(x=>x.expenses),borderColor:'#f59e0b',backgroundColor:'rgba(245,158,11,.08)',tension:.3},
          {label:'سود خالص',data:monthly.map(x=>x.net_profit),borderColor:'#8b5cf6',backgroundColor:'rgba(139,92,246,.08)',tension:.3}
        ]},options:{...common,scales:{y:{beginAtZero:true}}}});
      }
      const yearlyCanvas=document.getElementById('yearlyChart');
      if(yearlyCanvas){
        destroy('yearlyChart');
        this.yearlyChart=new Chart(yearlyCanvas,{type:'bar',data:{labels:yearly.map(x=>x.year),datasets:[
          {label:'دریافتی',data:yearly.map(x=>x.received),backgroundColor:'rgba(34,197,94,.72)'},
          {label:'سود خالص',data:yearly.map(x=>x.net_profit),backgroundColor:'rgba(139,92,246,.72)'}
        ]},options:{...common,scales:{y:{beginAtZero:true}}}});
      }
      const serviceCanvas=document.getElementById('serviceChart');
      if(serviceCanvas){
        destroy('serviceChart');
        this.serviceChart=new Chart(serviceCanvas,{type:'bar',data:{labels:services.map(x=>x.name),datasets:[{label:'دریافتی',data:services.map(x=>x.received),backgroundColor:'rgba(14,165,168,.72)'}]},options:{...common,indexAxis:'y',scales:{x:{beginAtZero:true}}}});
      }
      const paymentCanvas=document.getElementById('paymentMethodChart');
      if(paymentCanvas){
        destroy('financeDonutChart');
        this.financeDonutChart=new Chart(paymentCanvas,{type:'doughnut',data:{labels:['نقد','کارت به کارت','کارتخوان'],datasets:[{data:[totals.cash,totals.transfer,totals.card],backgroundColor:['#22c55e','#3b82f6','#8b5cf6'],borderWidth:0}]},options:{...common,cutout:'60%'}});
      }
    };

    state.renderRequestedWorkPins=function(){
      if(!window.L||!this.mainMap)return;
      for(const marker of (this.aquaWorkMarkers||[])){try{this.mainMap.removeLayer(marker)}catch{}}
      this.aquaWorkMarkers=[];
      const customers=new Map((this.customers||[]).map(c=>[String(c.id),c]));
      const latestByCustomer=new Map();
      for(const job of (this.jobs||[])){
        const cid=String(job?.customer_id||'');
        if(!cid||!customers.has(cid))continue;
        const stamp=new Date(job?.date||job?.visited_at||job?.created_at||0).getTime()||0;
        const old=latestByCustomer.get(cid);
        if(!old||stamp>old.stamp)latestByCustomer.set(cid,{job,stamp});
      }
      for(const [cid,item] of latestByCustomer){
        const customer=customers.get(cid),lat=Number(customer?.latitude),lng=Number(customer?.longitude);
        if(!Number.isFinite(lat)||!Number.isFinite(lng))continue;
        const job=item.job;
        const icon=L.divIcon({className:'aq-work-marker',html:'<span></span>',iconSize:[28,34],iconAnchor:[14,30]});
        const marker=L.marker([lat,lng],{icon});
        const name=escapeHtml(customer?.map_label||customer?.name||job?.name||'کار');
        const service=escapeHtml(job?.service_type||job?.description||'سرویس');
        marker.bindPopup(`<div dir="rtl"><b>${name}</b><br>${service}<br><b>${this.money(job?.received_amount||0)} تومان</b></div>`);
        marker.addTo(this.mainMap);
        this.aquaWorkMarkers.push(marker);
      }
    };

    const oldLoadBale=state.loadBaleJobs?.bind(state);
    state.loadBaleJobs=async function(tab=null){
      if(tab)this.baleTab=tab;
      const result=await oldLoadBale?.(tab);
      const wanted=String(this.baleTab||'new');
      if(wanted!=='all')this.baleJobs=(this.baleJobs||[]).filter(job=>String(job?.status||'')===wanted);
      return result;
    };

    const oldCancelBale=state.confirmBaleCancel?.bind(state);
    state.confirmBaleCancel=async function(){
      const id=String(this.baleCancelJob?.id||'');
      const result=await oldCancelBale?.();
      if(id){
        this.baleJobs=(this.baleJobs||[]).filter(job=>String(job?.id||'')!==id);
        try{await this.loadBaleCounts?.()}catch{}
      }
      return result;
    };

    const oldCompleteBale=state.confirmBaleComplete?.bind(state);
    state.confirmBaleComplete=async function(){
      const id=String(this.baleCompleteJob?.id||'');
      const result=await oldCompleteBale?.();
      if(id){
        this.baleJobs=(this.baleJobs||[]).filter(job=>String(job?.id||'')!==id);
        try{await Promise.all([this.loadBaleCounts?.(),this.loadBaleJobs?.('new')])}catch{}
      }
      return result;
    };

    const oldRegisterSmart=state.registerSmart?.bind(state);
    state.registerSmart=async function(){
      this.normalizeSmartChoices();
      if(this.smartParsed){
        if(!['ساید','فیلتر دستگاه','دیگر'].includes(cleanText(this.smartParsed.service_type)))return this.toast?.('نوع سرویس را انتخاب کن','error');
        if(!['cash','transfer','card'].includes(cleanText(this.smartParsed.payment_method)))return this.toast?.('روش پرداخت را انتخاب کن','error');
      }
      const pending=this.baleSmartJob?{id:String(this.baleSmartJob.id||'')}:null;
      const result=await oldRegisterSmart?.();
      if(!pending?.id)return result;
      const smartCleared=!cleanText(this.smartText)&&!this.smartParsed;
      if(!smartCleared)return result;
      this.baleJobs=(this.baleJobs||[]).filter(job=>String(job?.id||'')!==pending.id);
      try{
        let fresh=await this.api('/bale/jobs?status=new&_='+Date.now());
        const remains=(fresh||[]).some(job=>String(job?.id||'')===pending.id);
        if(remains){
          try{await this.api('/bale/jobs/'+pending.id+'/finalize',{method:'POST',body:'{}'})}catch(error){
            const message=String(error?.message||'');
            if(!/قبلاً تعیین تکلیف|already/i.test(message))this.toast?.(message||'سرویس ثبت شد ولی بستن کار بله کامل نشد','error');
          }
          fresh=await this.api('/bale/jobs?status=new&_='+Date.now());
        }
        this.baleSmartJob=null;
        if(this.baleTab==='new')this.baleJobs=(fresh||[]).filter(job=>String(job?.status||'')==='new'&&String(job?.id||'')!==pending.id);
        await this.loadBaleCounts?.();
      }catch(error){console.warn('Aqua Bale post-register refresh',error)}
      return result;
    };

    const oldGo=state.go?.bind(state);
    state.go=async function(page,...args){
      const result=await oldGo?.(page,...args);
      if(page==='insights')this.loadInsightsRequested?.();
      if(page==='finance')setTimeout(()=>this.renderRequestedFinanceCharts?.(),140);
      if(page==='map')setTimeout(()=>this.renderRequestedWorkPins?.(),180);
      return result;
    };

    const oldRefresh=state.refreshAll?.bind(state);
    state.refreshAll=async function(...args){
      const result=await oldRefresh?.(...args);
      if(this.page==='insights')await this.loadInsightsRequested?.();
      if(this.page==='finance')setTimeout(()=>this.renderRequestedFinanceCharts?.(),80);
      if(this.page==='map')setTimeout(()=>this.renderRequestedWorkPins?.(),120);
      return result;
    };

    state.requestAquaNotificationAccess=async function(){
      const ios=/iPhone|iPad|iPod/i.test(navigator.userAgent);
      const standalone=(window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches)||navigator.standalone===true;
      const tell=(message,type='info')=>this.toast?this.toast(message,type):alert(message);
      if(ios&&!standalone){tell('برای نوتیف آیفون، AquaGold را از آیکون Home Screen باز کن و دوباره این دکمه را بزن.','error');return}
      await this.enableAquaPush?.();
      await this.refreshPushStatus?.();
    };
    return state;
  };

  function mountSmartSelectors(){
    if(!window.Alpine)return;
    const labels=[...document.querySelectorAll('section[x-show*="page===\'smart\'"] label')];
    const replace=(label,model,options)=>{
      if(!label||label.querySelector('select[data-aqua-round3]'))return;
      const control=label.querySelector('input,select');if(!control)return;
      const select=document.createElement('select');
      select.className=control.className||'field mt-1';
      select.setAttribute('x-model',model);select.dataset.aquaRound3='1';
      select.innerHTML=options.map(([value,text])=>`<option value="${value}">${text}</option>`).join('');
      control.replaceWith(select);
      try{Alpine.initTree(select)}catch{}
    };
    const serviceLabel=labels.find(l=>cleanText(l.childNodes?.[0]?.textContent).includes('نوع سرویس'));
    const paymentLabel=labels.find(l=>cleanText(l.childNodes?.[0]?.textContent).includes('روش پرداخت'));
    replace(serviceLabel,'smartParsed.service_type',[['ساید','ساید'],['فیلتر دستگاه','فیلتر دستگاه'],['دیگر','دیگر']]);
    replace(paymentLabel,'smartParsed.payment_method',[['','انتخاب روش پرداخت'],['cash','نقد'],['transfer','کارت به کارت'],['card','کارتخوان']]);
  }

  function mountLatestServicesAccordion(){
    const title=[...document.querySelectorAll('h3')].find(h=>cleanText(h.textContent)==='آخرین سرویس‌ها');
    const card=title?.closest('.card');if(!card||card.dataset.aquaLatestAccordion)return;
    card.dataset.aquaLatestAccordion='1';card.classList.add('aqua-latest-card','aqua-latest-collapsed');
    const head=card.firstElementChild;if(!head)return;
    head.style.cursor='pointer';
    const toggle=document.createElement('button');toggle.type='button';toggle.className='btn soft !py-2 aqua-latest-toggle';toggle.textContent='نمایش آخرین سرویس‌ها';
    head.appendChild(toggle);
    const act=event=>{event?.preventDefault?.();const closed=card.classList.toggle('aqua-latest-collapsed');toggle.textContent=closed?'نمایش آخرین سرویس‌ها':'بستن آخرین سرویس‌ها'};
    toggle.addEventListener('click',act);title.parentElement?.addEventListener('click',event=>{if(event.target!==toggle)act(event)});
  }

  function mountFinancePaymentUi(){
    const finance=[...document.querySelectorAll('section')].find(x=>(x.getAttribute('x-show')||'').includes("page==='finance'"));
    if(!finance)return;
    const monthly=document.getElementById('monthlyChart');const grid=monthly?.closest('.grid');if(!grid)return;
    if(!document.getElementById('aqua-payment-summary')){
      const summary=document.createElement('div');summary.id='aqua-payment-summary';summary.className='grid grid-cols-1 sm:grid-cols-3 gap-3';
      summary.innerHTML=`<div class="card stat"><small class="muted">دریافتی نقد</small><b class="block mt-1" data-aqua-payment-total="cash">۰ تومان</b></div><div class="card stat"><small class="muted">کارت به کارت</small><b class="block mt-1" data-aqua-payment-total="transfer">۰ تومان</b></div><div class="card stat"><small class="muted">کارتخوان</small><b class="block mt-1" data-aqua-payment-total="card">۰ تومان</b></div>`;
      grid.parentElement?.insertBefore(summary,grid);
    }
    if(!document.getElementById('paymentMethodChart')){
      const card=document.createElement('div');card.className='card p-5';card.innerHTML='<h3 class="font-black mb-3">روش‌های پرداخت</h3><canvas id="paymentMethodChart"></canvas>';
      grid.appendChild(card);
    }
  }

  const mount=()=>{
    if(!document.getElementById('aqua-round2-style')){
      const style=document.createElement('style');style.id='aqua-round2-style';
      style.textContent=`
        .aq-map-marker span,.aq-work-marker span{display:block;width:24px;height:24px;border-radius:50% 50% 50% 0;background:#ef3340!important;border:3px solid #fff!important;box-shadow:0 4px 14px rgba(239,51,64,.42)!important;transform:rotate(-45deg)}
        .aq-work-marker{background:transparent!important;border:0!important}
        .aqua-latest-card.aqua-latest-collapsed>:not(:first-child){display:none!important}
        .aqua-latest-toggle{margin-inline-start:auto;white-space:nowrap}
        #monthlyChart,#yearlyChart,#serviceChart,#paymentMethodChart{display:block!important;width:100%!important;height:270px!important;max-height:270px!important;min-height:270px!important}
        section[x-show="page==='finance'"] .card{min-width:0!important;overflow:hidden!important}
        section[x-show="page==='finance'"] canvas{box-sizing:border-box!important}
        @media(max-width:520px){#monthlyChart,#yearlyChart,#serviceChart,#paymentMethodChart{height:235px!important;max-height:235px!important;min-height:235px!important}.aqua-latest-toggle{font-size:.72rem;padding:.55rem .7rem!important}}
      `;document.head.appendChild(style);
    }
    const pushCard=document.getElementById('aqua-ios-push-card');const primary=pushCard?.querySelector('button.btn.primary');
    if(primary&&!primary.dataset.round2Push){primary.dataset.round2Push='1';primary.removeAttribute('x-text');primary.setAttribute('@click','requestAquaNotificationAccess()');primary.textContent='دادن دسترسی نوتیف آیفون'}
    mountSmartSelectors();mountLatestServicesAccordion();mountFinancePaymentUi();
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(mount,40),{once:true});else setTimeout(mount,40);
})();
