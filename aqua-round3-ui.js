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
    const baseToggleRecording=state.toggleAquaRecording?.bind(state);
    const baseStopSpeech=state.stopAquaSpeech?.bind(state);
    state.aquaPaymentBreakdown=null;
    state.aquaNativeRecognition=null;
    state.aquaNativeTranscript='';
    if(state.aquaSettings)state.aquaSettings.auto_speak=true;

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

    // iOS speech priming is created inside the user's tap. Do not cancel that
    // primed session again just before the asynchronous Aria response is spoken.
    state.stopAquaSpeech=function(){
      const synth=window.speechSynthesis;
      if(this.aquaSpeechPrimed&&!this.aquaSpeaking&&synth&&!synth.speaking&&!synth.pending){
        this.aquaSpeechSeq=Number(this.aquaSpeechSeq||0)+1;
        this.aquaSpeechUtterance=null;
        this.aquaSpeechPrimeUtterance=null;
        return;
      }
      return baseStopSpeech?.();
    };

    // Prefer Safari's own Persian speech recognition on iPhone. It gives us the
    // transcript while the user is speaking, then submits it exactly once when
    // recording stops. Other browsers keep the existing MediaRecorder/STT path.
    state.toggleAquaRecording=async function(){
      const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
      if(!Recognition)return baseToggleRecording?.();
      const phase=this.aquaVoicePhase||'idle';
      if(phase==='recording'&&this.aquaNativeRecognition){
        this.setAquaVoicePhase?.('stopping');
        try{this.aquaNativeRecognition.stop()}catch{this.setAquaVoicePhase?.('idle')}
        return;
      }
      if(phase!=='idle'){
        this.toast?.(phase==='transcribing'?'دارم صدات رو به متن تبدیل می‌کنم…':phase==='submitting'?'دارم همون پیام رو برای آریا می‌فرستم…':'ضبط قبلی هنوز کامل نشده…','info');
        return;
      }
      if(this.aquaBusy||this.aquaSendLock||this.aquaSendPromise){this.toast?.('آریا هنوز در حال پاسخ‌دادنه','info');return}
      this.stopAquaSpeech?.();this.primeAquaDeviceSpeech?.();
      const recognition=new Recognition(),runId=++this.aquaVoiceSeq;
      let finalText='',finished=false,started=false;
      this.aquaNativeRecognition=recognition;this.aquaNativeTranscript='';
      recognition.lang='fa-IR';recognition.continuous=true;recognition.interimResults=true;recognition.maxAlternatives=1;

      const finish=async()=>{
        if(finished)return;finished=true;
        this.aquaNativeRecognition=null;
        if(runId!==this.aquaVoiceSeq){this.setAquaVoicePhase?.('idle');return}
        const spoken=text(finalText||this.aquaNativeTranscript||this.aquaInput);
        if(!spoken){this.setAquaVoicePhase?.('idle');this.toast?.('حرفی از صدات تشخیص داده نشد؛ دوباره امتحان کن','info');return}
        this.aquaInput=spoken;this.setAquaVoicePhase?.('submitting');
        this.toast?.('گرفتمش؛ دارم برای آریا می‌فرستم…','success');
        const sent=await this.submitAquaVoiceTranscript?.(spoken,runId);
        this.aquaInput=sent?'':spoken;
        this.setAquaVoicePhase?.('idle');
        if(!sent)this.toast?.('متن ویس در کادر ماند؛ دکمه ارسال را بزن','info');
      };

      recognition.onstart=()=>{started=true;this.setAquaVoicePhase?.('recording')};
      recognition.onresult=event=>{
        let interim='';
        for(let i=event.resultIndex;i<event.results.length;i++){
          const piece=text(event.results[i]?.[0]?.transcript);if(!piece)continue;
          if(event.results[i].isFinal)finalText=(finalText+' '+piece).trim();else interim=(interim+' '+piece).trim();
        }
        this.aquaNativeTranscript=(finalText+' '+interim).trim();
        this.aquaInput=this.aquaNativeTranscript;
      };
      recognition.onerror=event=>{
        const code=String(event?.error||'');
        if(!['aborted','no-speech'].includes(code))this.toast?.(code==='not-allowed'?'اجازه میکروفن آیفون داده نشده':'تشخیص صدای آیفون خطا داد؛ دوباره امتحان کن','error');
      };
      recognition.onend=()=>void finish();
      try{this.setAquaVoicePhase?.('starting');recognition.start()}
      catch(error){this.aquaNativeRecognition=null;this.setAquaVoicePhase?.('idle');if(!started)return baseToggleRecording?.();throw error}
    };

    return state;
  };
})();
