/* UI-STABILITY: this file may wrap app() before Alpine, but MUST NOT mutate DOM at top level. */
(()=>{
  if(window.__aquaRound6SafeUi)return;
  window.__aquaRound6SafeUi=true;

  const clean=value=>String(value??'').trim();
  const previous=window.app;
  if(typeof previous!=='function')return;

  const smartSection=()=>[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='smart'"));
  const pageSection=page=>[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes(`page==='${page}'`));

  function removeManualSmartDuplicates(){
    const section=smartSection();
    if(!section)return;
    for(const model of ['smartParsed.service_type','smartParsed.payment_method']){
      section.querySelectorAll(`input[x-model="${model}"]`).forEach(input=>input.closest('label')?.remove());
    }
  }

  function ensureSmartChoiceControls(state){
    if(!state?.smartParsed)return;
    const section=smartSection(),card=section?.querySelector('.smart-result');
    if(!card)return;
    removeManualSmartDuplicates();
    const serviceSelect=card.querySelector('select[x-model="smartParsed.service_type"]');
    const paymentSelect=card.querySelector('select[x-model="smartParsed.payment_method"]');
    if(serviceSelect&&paymentSelect)return;
    if(card.querySelector('#aqua-smart-choice-controls-safe'))return;

    const controls=document.createElement('div');
    controls.id='aqua-smart-choice-controls-safe';
    controls.className='grid sm:grid-cols-2 gap-3 mt-4 aqua-smart-choice-controls';
    controls.innerHTML=`
      <label class="block"><span class="text-xs muted block mb-1">نوع سرویس</span><select class="field" data-aqua-smart-service><option value="ساید">ساید</option><option value="فیلتر دستگاه">فیلتر دستگاه</option><option value="دیگر">دیگر</option></select></label>
      <label class="block"><span class="text-xs muted block mb-1">روش پرداخت</span><select class="field" data-aqua-smart-payment><option value="">انتخاب روش پرداخت</option><option value="cash">نقد</option><option value="transfer">کارت به کارت</option><option value="card">کارتخوان</option></select></label>`;
    const service=controls.querySelector('[data-aqua-smart-service]');
    const payment=controls.querySelector('[data-aqua-smart-payment]');
    service.value=['ساید','فیلتر دستگاه','دیگر'].includes(clean(state.smartParsed.service_type))?clean(state.smartParsed.service_type):'دیگر';
    payment.value=['cash','transfer','card'].includes(clean(state.smartParsed.payment_method))?clean(state.smartParsed.payment_method):'';
    service.addEventListener('change',()=>{if(state.smartParsed)state.smartParsed.service_type=service.value});
    payment.addEventListener('change',()=>{if(state.smartParsed)state.smartParsed.payment_method=payment.value});
    const gps=[...card.querySelectorAll('div')].find(el=>(el.getAttribute?.(':class')||'').includes('smartGps'));
    if(gps?.parentElement)gps.parentElement.insertBefore(controls,gps);else card.appendChild(controls);
  }

  function renderCustomerDueCards(state){
    if(state.page!=='customers')return;
    const section=pageSection('customers');
    if(!section)return;
    const customers=state.filteredCustomers||[];
    const cards=[...section.querySelectorAll('article.card')];
    cards.forEach((article,index)=>{
      const customer=customers[index];
      if(!customer)return;
      let box=article.querySelector('.aqua-customer-next-service');
      if(!box){
        box=document.createElement('div');
        box.className='aqua-customer-next-service mt-3 rounded-xl p-3 border text-xs';
        box.innerHTML='<div class="flex items-center justify-between gap-2"><span class="muted">سرویس بعدی</span><b data-aqua-next-service></b></div>';
        const address=article.querySelector('[x-text*="c.address"]');
        if(address)address.after(box);else article.appendChild(box);
      }
      const row=state.aquaServiceDueById?.[String(customer.id)]||customer.aqua_service_due||null;
      const label=box.querySelector('[data-aqua-next-service]');
      if(!row?.next_service_at){
        box.className='aqua-customer-next-service mt-3 rounded-xl p-3 border text-xs border-slate-500/15 bg-slate-500/5';
        label.textContent='بعد از اولین سرویس تعیین می‌شود';
      }else{
        box.className='aqua-customer-next-service mt-3 rounded-xl p-3 border text-xs '+(row.due_now?'border-red-500/30 bg-red-500/10 text-red-400':'border-cyan-500/20 bg-cyan-500/5 text-cyan-300');
        label.textContent=(row.due_now?'موعد رسیده • ':'')+state.persianDate(row.next_service_at);
      }
    });
  }

  function renderDashboardDue(state){
    if(state.page!=='dashboard')return;
    const section=pageSection('dashboard');
    if(!section)return;
    let alarm=section.querySelector('#aqua-service-due-alarm-safe');
    if(!alarm){
      alarm=document.createElement('div');
      alarm.id='aqua-service-due-alarm-safe';
      alarm.className='card p-4 md:p-5 border border-amber-400/30 bg-amber-500/10';
      alarm.innerHTML='<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3"><div><div class="text-xs text-amber-400 font-black">⏰ یادآوری سرویس دوره‌ای</div><b class="block mt-1 text-base" data-aqua-due-title></b><div class="text-xs muted mt-1" data-aqua-due-names></div></div><button type="button" class="btn bg-amber-500/20 text-amber-300">دیدن موعدها</button></div>';
      alarm.querySelector('button').addEventListener('click',()=>state.go('reminders'));
      const hero=section.querySelector('.aqua-hero,.hero');
      if(hero)hero.after(alarm);else section.prepend(alarm);
    }
    const due=state.aquaDueNow||[];
    alarm.style.display=due.length?'':'none';
    alarm.querySelector('[data-aqua-due-title]').textContent=`موعد سرویس ۶ ماهه ${due.length} مشتری رسیده است`;
    alarm.querySelector('[data-aqua-due-names]').textContent=due.slice(0,3).map(x=>x.last_name||x.first_name||x.name||'مشتری').join('، ')+(due.length>3?' …':'');
  }

  function mountSafeUi(state){
    renderCustomerDueCards(state);
    renderDashboardDue(state);
    if(state.page==='smart')ensureSmartChoiceControls(state);
  }

  window.app=function(){
    const state=previous();
    const oldInit=state.init?.bind(state);
    const oldRefresh=state.refreshAll?.bind(state);
    const oldLoadCustomers=state.loadCustomers?.bind(state);
    const oldAnalyze=state.analyzeSmart?.bind(state);
    const oldGo=state.go?.bind(state);
    const baseFinance=state.renderRound4Finance?.bind(state);

    state.aquaServiceDueRows=[];
    state.aquaServiceDueById={};
    state.aquaDueNow=[];
    state.aquaPaymentUnclassified=0;
    state.aquaPaymentCounts={cash:0,transfer:0,card:0,unclassified:0};
    state.aquaRound6PaymentChart=null;

    state.loadAquaServiceDue=async function(){
      try{
        const rows=await this.api('/customer-service-due?_='+Date.now());
        this.aquaServiceDueRows=Array.isArray(rows)?rows:[];
        this.aquaServiceDueById=Object.fromEntries(this.aquaServiceDueRows.map(row=>[String(row.customer_id),row]));
        this.aquaDueNow=this.aquaServiceDueRows.filter(row=>row?.next_service_at&&row?.due_now);
        for(const customer of (this.customers||[]))customer.aqua_service_due=this.aquaServiceDueById[String(customer.id)]||null;
        this.showAquaDueAlarmOnce?.();
      }catch(error){console.warn('Aqua service due load failed',error)}
      return this.aquaServiceDueRows;
    };

    state.loadAquaRemindersV2=async function(){
      try{
        const rows=await this.api('/reminders-v2?days=30&_='+Date.now());
        if(Array.isArray(rows))this.reminders=rows;
      }catch(error){console.warn('Aqua reminders v2 failed',error)}
      return this.reminders;
    };

    state.showAquaDueAlarmOnce=function(){
      if(!this.aquaDueNow?.length)return;
      const day=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
      const signature=day+'|'+this.aquaDueNow.map(row=>row.customer_id).sort().join(',');
      try{if(localStorage.getItem('aqua_due_alert_seen')===signature)return;localStorage.setItem('aqua_due_alert_seen',signature)}catch{}
      this.toast?.(`⏰ موعد سرویس ${this.aquaDueNow.length} مشتری رسیده است`,'info');
    };

    const originalAlerts=Object.getOwnPropertyDescriptor(state,'dashboardAlerts');
    if(originalAlerts?.configurable!==false){
      Object.defineProperty(state,'dashboardAlerts',{configurable:true,get(){
        const previousRows=originalAlerts?.get?originalAlerts.get.call(this):[];
        const rest=(previousRows||[]).filter(item=>item?.label!=='موعد سرویس'&&item?.label!=='موعد سرویس امروز');
        return [{label:'موعد سرویس امروز',value:this.aquaDueNow.length,page:'reminders',icon:'reminders'},...rest];
      }});
    }

    state.loadAquaPaymentBreakdown=async function(){
      try{
        const data=await this.api('/reports/payment-methods-v2?_='+Date.now());
        const totals=data?.totals||{};
        this.aquaPaymentBreakdown={cash:Number(totals.cash||0),transfer:Number(totals.transfer||0),card:Number(totals.card||0)};
        this.aquaPaymentUnclassified=Number(totals.unclassified||0);
        this.aquaPaymentCounts=data?.counts||{};
      }catch(error){console.warn('Aqua payment breakdown failed',error)}
      return this.aquaPaymentBreakdown||{cash:0,transfer:0,card:0};
    };

    state.renderRound6PaymentChart=async function(){
      const totals=await this.loadAquaPaymentBreakdown();
      for(const key of ['cash','transfer','card']){
        const el=document.querySelector(`[data-aqua-payment-total="${key}"]`);
        if(el)el.textContent=this.money(Number(totals[key]||0))+' تومان';
      }
      const canvas=document.getElementById('paymentMethodChart');
      if(!canvas||!window.Chart)return totals;
      try{window.Chart.getChart?.(canvas)?.destroy?.()}catch{}
      try{this.aquaRound6PaymentChart?.destroy?.()}catch{}
      const values=[Number(totals.cash||0),Number(totals.transfer||0),Number(totals.card||0)];
      const money=value=>this.money(value);
      const valueLabels={id:'aquaPaymentValueLabelsSafe',afterDatasetsDraw(chart){const meta=chart.getDatasetMeta(0),ctx=chart.ctx;ctx.save();ctx.textAlign='center';ctx.textBaseline='middle';meta.data.forEach((arc,index)=>{const value=values[index];if(!value)return;const pos=arc.tooltipPosition();ctx.fillStyle='#fff';ctx.font='800 12px Vazirmatn';ctx.shadowColor='rgba(0,0,0,.55)';ctx.shadowBlur=4;ctx.fillText(money(value),pos.x,pos.y-7);ctx.font='700 10px Vazirmatn';ctx.fillText('تومان',pos.x,pos.y+9)});ctx.restore()}};
      this.aquaRound6PaymentChart=new Chart(canvas,{type:'pie',data:{labels:['نقد','کارت به کارت','کارتخوان'],datasets:[{data:values,backgroundColor:['#22c55e','#3b82f6','#8b5cf6'],borderWidth:2,hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{position:'bottom',labels:{usePointStyle:true,generateLabels(chart){const base=Chart.defaults.plugins.legend.labels.generateLabels(chart);return base.map((item,index)=>({...item,text:`${item.text}: ${money(values[index])} تومان`}))}}},tooltip:{callbacks:{label(context){return `${context.label}: ${money(context.raw)} تومان`}}}}},plugins:[valueLabels]});
      return totals;
    };

    state.renderRound4Finance=async function(){
      try{await baseFinance?.()}catch(error){console.warn('Aqua finance base render recovered',error)}
      return this.renderRound6PaymentChart?.();
    };

    state.init=async function(...args){
      const result=await oldInit?.(...args);
      setTimeout(async()=>{try{await Promise.all([this.loadAquaServiceDue(),this.loadAquaRemindersV2()])}catch{}mountSafeUi(this)},120);
      return result;
    };

    state.analyzeSmart=async function(...args){
      const result=await oldAnalyze?.(...args);
      setTimeout(()=>ensureSmartChoiceControls(this),60);
      return result;
    };

    state.refreshAll=async function(...args){
      const result=await oldRefresh?.(...args);
      await Promise.all([this.loadAquaServiceDue(),this.loadAquaRemindersV2()]);
      setTimeout(()=>mountSafeUi(this),60);
      if(this.page==='finance')setTimeout(()=>this.renderRound6PaymentChart?.(),100);
      return result;
    };

    state.loadCustomers=async function(...args){
      const result=await oldLoadCustomers?.(...args);
      await this.loadAquaServiceDue();
      setTimeout(()=>renderCustomerDueCards(this),60);
      return result;
    };

    state.go=async function(page,...args){
      const result=await oldGo?.(page,...args);
      if(page==='customers')await this.loadAquaServiceDue();
      if(page==='reminders')await Promise.all([this.loadAquaServiceDue(),this.loadAquaRemindersV2()]);
      if(page==='finance')setTimeout(()=>this.renderRound6PaymentChart?.(),100);
      setTimeout(()=>mountSafeUi(this),70);
      return result;
    };

    return state;
  };
})();
