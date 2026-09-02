(()=>{
  if(window.__aquaRound3Ui)return;
  window.__aquaRound3Ui=true;
  const previous=window.app;
  if(typeof previous!=='function')return;
  const text=value=>String(value??'').trim();

  const insightFallback=(state,data)=>{
    const out={top_customers:[],busy_days:[],expense_categories:[],areas:[],service_analysis:[],...(data||{})};
    const jobs=state.jobs||[],customers=state.customers||[],expenses=state.expenses||[];

    if(!out.top_customers?.length&&jobs.length){
      const map=new Map();
      for(const job of jobs){
        const id=String(job.customer_id||job.name||'');if(!id)continue;
        const row=map.get(id)||{id,name:job.name||'مشتری',received:0,services:0};
        row.received+=Number(job.received_amount||0);row.services++;map.set(id,row);
      }
      out.top_customers=[...map.values()].sort((a,b)=>b.received-a.received).slice(0,10);
    }
    if(!out.busy_days?.length&&jobs.length){
      const map=new Map();
      for(const job of jobs){
        const d=new Date(job.date||job.visited_at||job.created_at||0);if(Number.isNaN(d.getTime()))continue;
        const weekday=d.getDay()===0?7:d.getDay(),row=map.get(weekday)||{weekday,services:0,received:0};
        row.services++;row.received+=Number(job.received_amount||0);map.set(weekday,row);
      }
      out.busy_days=[...map.values()].sort((a,b)=>b.services-a.services);
    }
    if(!out.expense_categories?.length&&expenses.length){
      const map=new Map();
      for(const expense of expenses){const key=text(expense.category)||'other',row=map.get(key)||{category:key,count:0,amount:0};row.count++;row.amount+=Number(expense.amount||0);map.set(key,row)}
      out.expense_categories=[...map.values()].sort((a,b)=>b.amount-a.amount);
    }
    if(!out.areas?.length&&customers.length){
      const map=new Map();
      for(const customer of customers){const address=text(customer.address);if(!address)continue;const area=address.split(/\s+/).slice(0,2).join(' ');map.set(area,(map.get(area)||0)+1)}
      out.areas=[...map.entries()].map(([area,count])=>({area,customers:count})).sort((a,b)=>b.customers-a.customers).slice(0,10);
    }
    if(!out.service_analysis?.length&&jobs.length){
      const map=new Map();
      for(const job of jobs){const key=text(job.service_type)||'نامشخص',row=map.get(key)||{service_type:key,services:0,received:0,avg_received:0};row.services++;row.received+=Number(job.received_amount||0);map.set(key,row)}
      out.service_analysis=[...map.values()].map(row=>({...row,avg_received:row.services?Math.round(row.received/row.services):0})).sort((a,b)=>b.received-a.received).slice(0,15);
    }
    return out;
  };

  window.app=function(){
    const state=previous();
    const localPaymentTotals=state.paymentMethodTotals?.bind(state);
    const baseFinanceRender=state.renderRequestedFinanceCharts?.bind(state);
    const baseWorkPins=state.renderRequestedWorkPins?.bind(state);
    state.aquaPaymentBreakdown=null;

    state.loadInsightsRequested=async function(){
      let data={};
      try{data=await this.api('/reports/insights?_='+Date.now())}catch(error){console.warn('Aqua insights API fallback',error)}
      this.insights=insightFallback(this,data);
      return this.insights;
    };

    state.loadAquaPaymentBreakdown=async function(){
      try{
        const data=await this.api('/reports/payment-methods?_='+Date.now());
        this.aquaPaymentBreakdown={cash:Number(data?.totals?.cash||0),transfer:Number(data?.totals?.transfer||0),card:Number(data?.totals?.card||0),other:Number(data?.totals?.other||0)};
      }catch(error){console.warn('Aqua payment breakdown fallback',error);this.aquaPaymentBreakdown=null}
      return this.aquaPaymentBreakdown;
    };

    state.paymentMethodTotals=function(){
      return this.aquaPaymentBreakdown||localPaymentTotals?.()||{cash:0,transfer:0,card:0,other:0};
    };

    state.renderRequestedFinanceCharts=async function(){
      await this.loadAquaPaymentBreakdown();
      return baseFinanceRender?.();
    };

    state.renderRequestedWorkPins=async function(){
      if(!window.L||!this.mainMap)return;
      try{
        const rows=await this.api('/map/work-pins?_='+Date.now());
        for(const marker of (this.aquaWorkMarkers||[])){try{this.mainMap.removeLayer(marker)}catch{}}
        this.aquaWorkMarkers=[];
        for(const job of (rows||[])){
          const lat=Number(job.latitude),lng=Number(job.longitude);if(!Number.isFinite(lat)||!Number.isFinite(lng))continue;
          const icon=L.divIcon({className:'aq-work-marker',html:'<span aria-hidden="true"></span>',iconSize:[28,34],iconAnchor:[14,30],popupAnchor:[0,-28]});
          const marker=L.marker([lat,lng],{icon});
          const esc=value=>this.escapeHtml?this.escapeHtml(value):String(value??'');
          marker.bindPopup(`<div dir="rtl"><b>${esc(job.map_label||job.name||'کار')}</b><br>${esc(job.service_type||job.description||'سرویس')}<br><b>${this.money(job.received_amount||0)} تومان</b></div>`);
          marker.addTo(this.mainMap);this.aquaWorkMarkers.push(marker);
        }
        return this.aquaWorkMarkers;
      }catch(error){console.warn('Aqua work pins fallback',error);return baseWorkPins?.()}
    };

    return state;
  };
})();
