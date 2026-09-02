(()=>{
  if(window.__aquaRound6UserFixes)return;
  window.__aquaRound6UserFixes=true;

  const clean=value=>String(value??'').trim();

  function smartSection(){
    return [...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='smart'"));
  }

  function removeManualSmartDuplicates(){
    const section=smartSection();if(!section)return;
    const selectors=[
      'input[x-model="smartParsed.service_type"]',
      'input[x-model="smartParsed.payment_method"]',
      'input[placeholder="نوع سرویس"]',
      'input[placeholder*="نقد"]'
    ];
    for(const selector of selectors){
      section.querySelectorAll(selector).forEach(input=>{
        const model=input.getAttribute('x-model')||'';
        if(model==='smartParsed.service_type'||model==='smartParsed.payment_method'||input.getAttribute('placeholder')==='نوع سرویس'||/نقد/.test(input.getAttribute('placeholder')||'')){
          input.closest('label')?.remove();
        }
      });
    }
    section.querySelectorAll('label').forEach(label=>{
      const title=clean(label.firstChild?.textContent||label.querySelector('span')?.textContent||'');
      const input=label.querySelector('input');
      if(input&&(/^(نوع سرویس|روش پرداخت)$/.test(title))){
        const model=input.getAttribute('x-model')||'';
        if(model.includes('smartParsed.'))label.remove();
      }
    });
  }

  function ensureSmartChoiceControls(state){
    if(!state?.smartParsed)return;
    const section=smartSection();
    const card=section?.querySelector('.smart-result');
    if(!card)return;
    removeManualSmartDuplicates();
    if(card.querySelector('select[x-model="smartParsed.service_type"]')&&card.querySelector('select[x-model="smartParsed.payment_method"]'))return;
    document.getElementById('aqua-smart-choice-controls')?.remove();
    document.getElementById('aqua-smart-choice-controls-v6')?.remove();
    const gps=[...card.querySelectorAll('div')].find(el=>el.getAttribute?.(':class')?.includes('smartGps'));
    const controls=document.createElement('div');
    controls.id='aqua-smart-choice-controls-v6';
    controls.className='grid sm:grid-cols-2 gap-3 mt-4 aqua-smart-choice-controls';
    controls.innerHTML=`
      <label class="block"><span class="text-xs muted block mb-1">نوع سرویس</span><select class="field" x-model="smartParsed.service_type"><option value="ساید">ساید</option><option value="فیلتر دستگاه">فیلتر دستگاه</option><option value="دیگر">دیگر</option></select></label>
      <label class="block"><span class="text-xs muted block mb-1">روش پرداخت</span><select class="field" x-model="smartParsed.payment_method"><option value="">انتخاب روش پرداخت</option><option value="cash">نقد</option><option value="transfer">کارت به کارت</option><option value="card">کارتخوان</option></select></label>`;
    if(gps?.parentElement)gps.parentElement.insertBefore(controls,gps);else card.appendChild(controls);
    try{window.Alpine?.initTree?.(controls)}catch(error){console.warn('Aqua Round6 smart controls init',error)}
  }

  function patchCustomerTemplate(){
    const section=[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='customers'"));
    const template=[...(section?.querySelectorAll('template')||[])].find(el=>(el.getAttribute('x-for')||'').includes('filteredCustomers'));
    const article=template?.content?.querySelector('article');
    if(!article||article.querySelector('.aqua-customer-next-service'))return;
    const address=article.querySelector('[x-text*="c.address"]');
    const due=document.createElement('div');
    due.className='aqua-customer-next-service mt-3 rounded-xl p-3 border text-xs';
    due.setAttribute(':class','customerNextServiceClass(c)');
    due.innerHTML='<div class="flex items-center justify-between gap-2"><span class="muted">سرویس بعدی</span><b x-text="customerNextServiceLabel(c)"></b></div>';
    if(address)address.after(due);else article.appendChild(due);
  }

  function patchDashboardDueAlarm(){
    const section=[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='dashboard'"));
    if(!section||section.querySelector('#aqua-service-due-alarm'))return;
    const hero=section.querySelector('.aqua-hero,.hero');
    const alarm=document.createElement('div');
    alarm.id='aqua-service-due-alarm';
    alarm.setAttribute('x-show','aquaDueNow.length');
    alarm.style.display='none';
    alarm.className='card p-4 md:p-5 border border-amber-400/30 bg-amber-500/10';
    alarm.innerHTML=`<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3"><div><div class="text-xs text-amber-400 font-black">⏰ یادآوری سرویس دوره‌ای</div><b class="block mt-1 text-base" x-text="'موعد سرویس ۶ ماهه '+aquaDueNow.length+' مشتری رسیده است'"></b><div class="text-xs muted mt-1" x-text="aquaDueNow.slice(0,3).map(x=>x.last_name||x.first_name||'مشتری').join('، ')+(aquaDueNow.length>3?' …':'')"></div></div><button type="button" class="btn bg-amber-500/20 text-amber-300" @click="go('reminders')">دیدن موعدها</button></div>`;
    if(hero)hero.after(alarm);else section.prepend(alarm);
  }

  patchCustomerTemplate();
  patchDashboardDueAlarm();
  removeManualSmartDuplicates();

  const previous=window.app;
  if(typeof previous!=='function')return;

  window.app=function(){
    const state=previous();
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

    state.customerNextServiceRow=function(customer){
      return this.aquaServiceDueById[String(customer?.id)]||customer?.aqua_service_due||null;
    };
    state.customerNextServiceLabel=function(customer){
      const row=this.customerNextServiceRow(customer);
      if(!row?.last_service_at||!row?.next_service_at)return'بعد از اولین سرویس تعیین می‌شود';
      const prefix=row.due_now?'موعد رسیده • ':'';
      return prefix+this.persianDate(row.next_service_at);
    };
    state.customerNextServiceClass=function(customer){
      const row=this.customerNextServiceRow(customer);
      if(!row?.next_service_at)return'border-slate-500/15 bg-slate-500/5';
      return row.due_now?'border-red-500/30 bg-red-500/10 text-red-400':'border-cyan-500/20 bg-cyan-500/5 text-cyan-300';
    };
    state.showAquaDueAlarmOnce=function(){
      if(!this.aquaDueNow?.length)return;
      const day=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
      const signature=day+'|'+this.aquaDueNow.map(row=>row.customer_id).sort().join(',');
      try{if(localStorage.getItem('aqua_due_alert_seen')===signature)return;localStorage.setItem('aqua_due_alert_seen',signature)}catch{}
      this.toast?.(`⏰ موعد سرویس ${this.aquaDueNow.length} مشتری رسیده است`,'info');
    };

    const originalAlerts=Object.getOwnPropertyDescriptor(state,'dashboardAlerts');
    Object.defineProperty(state,'dashboardAlerts',{configurable:true,get(){
      const previousRows=originalAlerts?.get?originalAlerts.get.call(this):[];
      const rest=(previousRows||[]).filter(item=>item?.label!=='موعد سرویس');
      return [{label:'موعد سرویس امروز',value:this.aquaDueNow.length,page:'reminders',icon:'reminders'},...rest];
    }});

    state.loadAquaPaymentBreakdown=async function(){
      try{
        const data=await this.api('/reports/payment-methods-v2?_='+Date.now());
        const totals=data?.totals||{};
        this.aquaPaymentBreakdown={cash:Number(totals.cash||0),transfer:Number(totals.transfer||0),card:Number(totals.card||0)};
        this.aquaPaymentUnclassified=Number(totals.unclassified||0);
        this.aquaPaymentCounts=data?.counts||{};
      }catch(error){console.warn('Aqua Round6 payment breakdown failed',error)}
      return this.aquaPaymentBreakdown||{cash:0,transfer:0,card:0};
    };

    state.renderRound6PaymentChart=async function(){
      const totals=await this.loadAquaPaymentBreakdown();
      for(const key of ['cash','transfer','card']){
        const el=document.querySelector(`[data-aqua-payment-total="${key}"]`);
        if(el)el.textContent=this.money(Number(totals[key]||0))+' تومان';
      }
      let note=document.getElementById('aqua-payment-unclassified-note');
      const card=document.getElementById('paymentMethodChart')?.closest('.card');
      if(card&&!note){note=document.createElement('div');note.id='aqua-payment-unclassified-note';note.className='text-xs muted mt-3';card.appendChild(note)}
      if(note)note.textContent=this.aquaPaymentUnclassified>0?`مبلغ ${this.money(this.aquaPaymentUnclassified)} تومان از ثبت‌های قدیمی روش پرداخت مشخص و قابل بازیابی ندارد.`:'';
      const canvas=document.getElementById('paymentMethodChart');if(!canvas||!window.Chart)return totals;
      try{window.Chart.getChart?.(canvas)?.destroy?.()}catch{}
      try{this.aquaRound6PaymentChart?.destroy?.()}catch{}
      try{this.paymentMethodChart?.destroy?.()}catch{}
      try{this.financeDonutChart?.destroy?.()}catch{}
      const values=[Number(totals.cash||0),Number(totals.transfer||0),Number(totals.card||0)];
      const money=value=>this.money(value);
      const valueLabels={
        id:'aquaRound6PaymentValueLabels',
        afterDatasetsDraw(chart){
          const meta=chart.getDatasetMeta(0),ctx=chart.ctx;ctx.save();ctx.textAlign='center';ctx.textBaseline='middle';
          meta.data.forEach((arc,index)=>{
            const value=values[index];if(!value)return;
            const pos=arc.tooltipPosition();
            ctx.fillStyle='#fff';ctx.font='800 12px Vazirmatn';ctx.shadowColor='rgba(0,0,0,.55)';ctx.shadowBlur=4;
            ctx.fillText(money(value),pos.x,pos.y-7);ctx.font='700 10px Vazirmatn';ctx.fillText('تومان',pos.x,pos.y+9);
          });
          ctx.restore();
        }
      };
      this.aquaRound6PaymentChart=new Chart(canvas,{
        type:'pie',
        data:{labels:['نقد','کارت به کارت','کارتخوان'],datasets:[{data:values,backgroundColor:['#22c55e','#3b82f6','#8b5cf6'],borderColor:'rgba(7,20,24,.72)',borderWidth:2,hoverOffset:8}]},
        options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{position:'bottom',labels:{usePointStyle:true,boxWidth:12,generateLabels(chart){const base=Chart.defaults.plugins.legend.labels.generateLabels(chart);return base.map((item,index)=>({...item,text:`${item.text}: ${money(values[index])} تومان`}))}}},tooltip:{callbacks:{label(context){return `${context.label}: ${money(context.raw)} تومان`}}}}},
        plugins:[valueLabels]
      });
      return totals;
    };

    state.renderRound4Finance=async function(){
      try{await baseFinance?.()}catch(error){console.warn('Aqua finance base render recovered',error)}
      return this.renderRound6PaymentChart?.();
    };
    state.renderCharts=function(){return this.renderRound4Finance?.()};

    state.analyzeSmart=async function(...args){
      const result=await oldAnalyze?.(...args);
      setTimeout(removeManualSmartDuplicates,0);
      setTimeout(()=>ensureSmartChoiceControls(this),30);
      setTimeout(()=>{removeManualSmartDuplicates();ensureSmartChoiceControls(this)},180);
      return result;
    };

    state.refreshAll=async function(...args){
      const result=await oldRefresh?.(...args);
      await Promise.all([this.loadAquaServiceDue(),this.loadAquaRemindersV2()]);
      if(this.page==='finance')setTimeout(()=>this.renderRound6PaymentChart?.(),80);
      return result;
    };

    state.loadCustomers=async function(...args){
      const result=await oldLoadCustomers?.(...args);
      await this.loadAquaServiceDue();
      return result;
    };

    state.go=async function(page,...args){
      const result=await oldGo?.(page,...args);
      if(page==='smart'){setTimeout(removeManualSmartDuplicates,30);setTimeout(()=>ensureSmartChoiceControls(this),70)}
      if(page==='customers')await this.loadAquaServiceDue();
      if(page==='reminders')await Promise.all([this.loadAquaServiceDue(),this.loadAquaRemindersV2()]);
      if(page==='finance')setTimeout(()=>this.renderRound6PaymentChart?.(),100);
      return result;
    };

    return state;
  };

  const finishMount=()=>{
    patchCustomerTemplate();patchDashboardDueAlarm();removeManualSmartDuplicates();
    if(!document.getElementById('aqua-round6-style')){
      const style=document.createElement('style');style.id='aqua-round6-style';style.textContent=`
        #paymentMethodChart{display:block!important;width:100%!important;height:320px!important;max-height:320px!important}
        .aqua-customer-next-service b{font-weight:900}
        #aqua-service-due-alarm{overflow:hidden}
        @media(max-width:520px){#paymentMethodChart{height:285px!important;max-height:285px!important}}
      `;document.head.appendChild(style);
    }
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',finishMount,{once:true});else finishMount();
  const observer=new MutationObserver(()=>{removeManualSmartDuplicates()});
  observer.observe(document.documentElement,{childList:true,subtree:true});
})();
