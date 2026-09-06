(()=>{
  if(window.__aquaRound4Ui)return;
  window.__aquaRound4Ui=true;
  const previous=window.app;
  if(typeof previous!=='function')return;
  const clean=value=>String(value??'').trim();

  function normalizeChoices(state){
    const p=state?.smartParsed;
    if(!p)return;
    const service=clean(p.service_type).toLowerCase();
    if(service.includes('ساید')||service.includes('یخچال'))p.service_type='ساید';
    else if(service.includes('فیلتر')||service.includes('دستگاه'))p.service_type='فیلتر دستگاه';
    else if(!['ساید','فیلتر دستگاه','دیگر'].includes(p.service_type))p.service_type='دیگر';
    const payment=clean(p.payment_method).toLowerCase().replace(/‌/g,' ');
    if(/کارت\s*به\s*کارت|transfer|card.?to.?card/.test(payment))p.payment_method='transfer';
    else if(/کارتخوان|کارت\s*خوان|\bpos\b|card.?reader/.test(payment))p.payment_method='card';
    else if(/نقد|cash/.test(payment))p.payment_method='cash';
    else if(!['cash','transfer','card'].includes(p.payment_method))p.payment_method='';
  }

  function mountSmartControls(state){
    if(!state?.smartParsed)return;
    const section=[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='smart'"));
    const card=section?.querySelector('.smart-result');
    if(!card||card.querySelector('#aqua-smart-choice-controls'))return;
    const gps=[...card.querySelectorAll('div')].find(el=>el.getAttribute?.(':class')?.includes('smartGps'));
    const controls=document.createElement('div');
    controls.id='aqua-smart-choice-controls';
    controls.className='grid sm:grid-cols-2 gap-3 mt-4 aqua-smart-choice-controls';
    controls.innerHTML=`
      <label class="block"><span class="text-xs muted block mb-1">نوع سرویس</span><select class="field" x-model="smartParsed.service_type"><option value="ساید">ساید</option><option value="فیلتر دستگاه">فیلتر دستگاه</option><option value="دیگر">دیگر</option></select></label>
      <label class="block"><span class="text-xs muted block mb-1">روش پرداخت</span><select class="field" x-model="smartParsed.payment_method"><option value="">انتخاب روش پرداخت</option><option value="cash">نقد</option><option value="transfer">کارت به کارت</option><option value="card">کارتخوان</option></select></label>
      <label class="block sm:col-span-2"><span class="text-xs muted block mb-1">توضیحات / شرح سرویس</span><textarea class="field min-h-24" x-model="smartParsed.description" placeholder="اگر «دیگر» را انتخاب کردی، نوع سرویس و جزئیاتش را اینجا بنویس"></textarea></label>`;
    if(gps?.parentElement)gps.parentElement.insertBefore(controls,gps);
    else card.appendChild(controls);
    try{window.Alpine?.initTree?.(controls)}catch(error){console.warn('Aqua smart controls init',error)}
  }

  function mountLatestServicesAccordion(){
    const title=[...document.querySelectorAll('h3')].find(el=>clean(el.textContent)==='آخرین سرویس‌ها');
    const card=title?.closest('.card');
    if(!card||card.dataset.aquaRound4Accordion)return;
    card.dataset.aquaRound4Accordion='1';
    const header=card.firstElementChild;
    if(!header)return;
    const titleBox=title.parentElement||header;
    const toggle=document.createElement('button');
    toggle.type='button';
    toggle.className='btn soft !py-2 !px-3 mt-2';
    titleBox.appendChild(toggle);
    const setClosed=closed=>{
      card.classList.toggle('aqua-latest-collapsed',closed);
      toggle.textContent=closed?'نمایش آخرین سرویس‌ها':'بستن آخرین سرویس‌ها';
      toggle.setAttribute('aria-expanded',String(!closed));
    };
    toggle.addEventListener('click',event=>{
      event.preventDefault();event.stopPropagation();
      setClosed(!card.classList.contains('aqua-latest-collapsed'));
    });
    setClosed(true);
  }

  function mountFinancePaymentUi(){
    const finance=[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='finance'"));
    if(!finance)return;
    const monthly=document.getElementById('monthlyChart');
    const grid=monthly?.closest('.grid');
    if(!grid)return;
    const otherCard='<div class="card stat"><small class="muted">سایر</small><b class="block mt-1" data-aqua-payment-total="other">۰ تومان</b></div>';
    let summary=document.getElementById('aqua-payment-summary');
    if(!summary){
      summary=document.createElement('div');
      summary.id='aqua-payment-summary';
      summary.className='grid grid-cols-2 lg:grid-cols-4 gap-3';
      summary.innerHTML='<div class="card stat"><small class="muted">دریافتی نقد</small><b class="block mt-1" data-aqua-payment-total="cash">۰ تومان</b></div><div class="card stat"><small class="muted">کارت به کارت</small><b class="block mt-1" data-aqua-payment-total="transfer">۰ تومان</b></div><div class="card stat"><small class="muted">کارتخوان</small><b class="block mt-1" data-aqua-payment-total="card">۰ تومان</b></div>'+otherCard;
      grid.parentElement?.insertBefore(summary,grid);
    }else{
      summary.className='grid grid-cols-2 lg:grid-cols-4 gap-3';
      if(!summary.querySelector('[data-aqua-payment-total="other"]'))summary.insertAdjacentHTML('beforeend',otherCard);
    }
    if(!document.getElementById('paymentMethodChart')){
      const card=document.createElement('div');
      card.className='card p-5 aqua-payment-chart-card';
      card.innerHTML='<h3 class="font-black mb-3">روش‌های پرداخت</h3><div class="aqua-payment-chart-wrap"><canvas id="paymentMethodChart"></canvas></div>';
      grid.appendChild(card);
    }
  }

  window.app=function(){
    const state=previous();
    const oldAnalyze=state.analyzeSmart;
    const oldRegister=state.registerSmart;
    const oldGo=state.go;
    const oldRefresh=state.refreshAll;

    state.normalizeRequestedSmartChoices=function(){normalizeChoices(this)};

    state.analyzeSmart=async function(...args){
      const result=await oldAnalyze?.apply(this,args);
      normalizeChoices(this);
      setTimeout(()=>mountSmartControls(this),30);
      setTimeout(()=>mountSmartControls(this),180);
      return result;
    };

    state.registerSmart=async function(...args){
      normalizeChoices(this);
      if(this.smartParsed){
        if(!['ساید','فیلتر دستگاه','دیگر'].includes(clean(this.smartParsed.service_type))){this.toast?.('نوع سرویس را انتخاب کن','error');return false}
        if(!['cash','transfer','card'].includes(clean(this.smartParsed.payment_method))){this.toast?.('روش پرداخت را انتخاب کن','error');return false}
        if(this.smartParsed.service_type==='دیگر'&&!clean(this.smartParsed.description)){this.toast?.('برای «دیگر» توضیحات سرویس را بنویس','error');return false}
      }
      return oldRegister?.apply(this,args);
    };

    state.renderRound4Finance=async function(){
      if(!window.Chart)return;
      mountFinancePaymentUi();
      try{await this.loadAquaPaymentBreakdown?.()}catch{}
      const totals=this.paymentMethodTotals?.()||{cash:0,transfer:0,card:0,other:0};
      for(const key of ['cash','transfer','card','other']){
        const el=document.querySelector(`[data-aqua-payment-total="${key}"]`);
        if(el)el.textContent=this.money(Number(totals[key]||0))+' تومان';
      }
      const destroy=name=>{try{this[name]?.destroy?.()}catch{}this[name]=null};
      const monthly=(this.jalaliMonthlyMetrics||[]).slice(-12);
      const yearly=(this.jalaliYearlyMetrics||[]).slice(-6);
      const services={};
      for(const job of (this.jobs||[])){
        const name=clean(job.service_type)||'دیگر';
        services[name]=services[name]||{name,received:0};
        services[name].received+=Number(job.received_amount||0);
      }
      const serviceRows=Object.values(services).sort((a,b)=>b.received-a.received).slice(0,10);
      const common={responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{labels:{boxWidth:12,usePointStyle:true}}}};

      const monthlyCanvas=document.getElementById('monthlyChart');
      if(monthlyCanvas){
        destroy('monthlyChart');
        this.monthlyChart=new Chart(monthlyCanvas,{
          type:'line',
          data:{labels:monthly.map(x=>x.label),datasets:[
            {label:'دریافتی',data:monthly.map(x=>x.received),borderColor:'#22c55e',backgroundColor:'rgba(34,197,94,.12)',tension:.3,fill:true},
            {label:'سهم شرکت',data:monthly.map(x=>x.company_share),borderColor:'#06b6d4',tension:.3},
            {label:'هزینه',data:monthly.map(x=>x.expenses),borderColor:'#f59e0b',tension:.3},
            {label:'سود خالص',data:monthly.map(x=>x.net_profit),borderColor:'#8b5cf6',tension:.3}
          ]},
          options:{...common,scales:{y:{beginAtZero:true}}}
        });
      }

      const yearlyCanvas=document.getElementById('yearlyChart');
      if(yearlyCanvas){
        destroy('yearlyChart');
        this.yearlyChart=new Chart(yearlyCanvas,{
          type:'bar',
          data:{labels:yearly.map(x=>x.year),datasets:[
            {label:'دریافتی',data:yearly.map(x=>x.received),backgroundColor:'rgba(34,197,94,.72)'},
            {label:'سود خالص',data:yearly.map(x=>x.net_profit),backgroundColor:'rgba(139,92,246,.72)'}
          ]},
          options:{...common,scales:{y:{beginAtZero:true}}}
        });
      }

      const serviceCanvas=document.getElementById('serviceChart');
      if(serviceCanvas){
        destroy('serviceChart');
        this.serviceChart=new Chart(serviceCanvas,{
          type:'bar',
          data:{labels:serviceRows.map(x=>x.name),datasets:[{label:'دریافتی',data:serviceRows.map(x=>x.received),backgroundColor:'rgba(14,165,168,.72)'}]},
          options:{...common,indexAxis:'y',scales:{x:{beginAtZero:true}}}
        });
      }

      const paymentCanvas=document.getElementById('paymentMethodChart');
      if(paymentCanvas){
        destroy('paymentMethodChart');
        this.paymentMethodChart=new Chart(paymentCanvas,{
          type:'doughnut',
          data:{
            labels:['نقد','کارت به کارت','کارتخوان','سایر'],
            datasets:[{
              data:[Number(totals.cash||0),Number(totals.transfer||0),Number(totals.card||0),Number(totals.other||0)],
              backgroundColor:['#22c55e','#3b82f6','#8b5cf6','#f59e0b'],
              borderWidth:0
            }]
          },
          options:{...common,cutout:'62%'}
        });
      }
    };

    state.go=async function(page,...args){
      const result=await oldGo?.apply(this,[page,...args]);
      if(page==='smart')setTimeout(()=>mountSmartControls(this),80);
      if(page==='dashboard')setTimeout(mountLatestServicesAccordion,80);
      if(page==='insights')setTimeout(()=>this.loadInsightsRequested?.(),80);
      if(page==='finance')setTimeout(()=>this.renderRound4Finance?.(),120);
      if(page==='map')setTimeout(()=>this.renderRequestedWorkPins?.(),160);
      return result;
    };

    state.refreshAll=async function(...args){
      const result=await oldRefresh?.apply(this,args);
      if(this.page==='dashboard')setTimeout(mountLatestServicesAccordion,40);
      if(this.page==='smart')setTimeout(()=>mountSmartControls(this),40);
      if(this.page==='insights')await this.loadInsightsRequested?.();
      if(this.page==='finance')setTimeout(()=>this.renderRound4Finance?.(),80);
      if(this.page==='map')setTimeout(()=>this.renderRequestedWorkPins?.(),100);
      return result;
    };
    return state;
  };

  const mount=()=>{
    if(!document.getElementById('aqua-round4-style')){
      const style=document.createElement('style');
      style.id='aqua-round4-style';
      style.textContent=`
        .aqua-latest-collapsed>:not(:first-child){display:none!important}
        .aqua-payment-chart-wrap{height:290px;position:relative}
        #monthlyChart,#yearlyChart,#serviceChart{display:block!important;width:100%!important;height:270px!important;max-height:270px!important;min-height:270px!important}
        #paymentMethodChart{display:block!important;width:100%!important;height:280px!important;max-height:280px!important}
        .aq-work-marker{background:transparent!important;border:0!important}.aq-work-marker span{display:block;width:24px;height:24px;border-radius:50% 50% 50% 0;background:#ef3340;border:3px solid #fff;box-shadow:0 4px 14px rgba(239,51,64,.48);transform:rotate(-45deg)}
        .aqua-smart-choice-controls .field{font-size:16px}
        @media(max-width:520px){.aqua-payment-chart-wrap{height:245px}#monthlyChart,#yearlyChart,#serviceChart{height:235px!important;max-height:235px!important;min-height:235px!important}#paymentMethodChart{height:235px!important;max-height:235px!important}}
      `;
      document.head.appendChild(style);
    }
    mountLatestServicesAccordion();
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();