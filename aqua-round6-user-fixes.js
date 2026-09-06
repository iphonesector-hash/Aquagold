(()=>{
  if(window.__aquaRound6UserFixes)return;
  window.__aquaRound6UserFixes=true;

  const clean=value=>String(value??'').trim();
  const faDigits=value=>String(value??'').replace(/[۰-۹]/g,d=>'۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٠-٩]/g,d=>'٠١٢٣٤٥٦٧٨٩'.indexOf(d));
  const pickMime=()=>{
    for(const value of ['audio/mp4','audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus']){
      try{if(window.MediaRecorder?.isTypeSupported?.(value))return value}catch{}
    }
    return'';
  };
  const escapeCss=value=>String(value??'').replace(/["\\]/g,'\\$&');

  const patchSmartDuplicates=()=>{
    const section=[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='smart'"));
    if(!section)return;
    for(const model of ['smartParsed.service_type','smartParsed.payment_method']){
      section.querySelectorAll(`input[x-model="${escapeCss(model)}"]`).forEach(input=>input.closest('label')?.remove());
    }
  };

  const patchDailyEditButton=()=>{
    const section=[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='daily'"));
    if(!section)return;
    const template=[...section.querySelectorAll('template')].find(el=>(el.getAttribute('x-for')||'').includes('d.completedJobs'));
    if(!template||template.dataset.aquaEditReady)return;
    template.dataset.aquaEditReady='1';
    template.innerHTML=`<div class="px-4 py-3 border-b flex items-center justify-between gap-3" style="border-color:var(--line)">
      <b class="min-w-0 truncate" x-text="dailySurname(j)"></b>
      <div class="flex items-center gap-2 shrink-0">
        <b class="text-emerald-500" x-text="money(j.received_amount)+' تومان'"></b>
        <button type="button" @click="openServiceEdit(j)" class="btn soft !py-1.5 !px-3 no-print">ویرایش</button>
      </div>
    </div>`;
  };

  const patchServiceEditModal=()=>{
    const modal=[...document.querySelectorAll('[x-show="serviceEditOpen"]')][0];
    if(!modal||modal.dataset.aquaRound6Edit)return;
    modal.dataset.aquaRound6Edit='1';
    const serviceInput=modal.querySelector('input[x-model="serviceEdit.service_type"]');
    if(serviceInput){
      const select=document.createElement('select');
      select.setAttribute('x-model','serviceEdit.service_type');
      select.className='field';
      select.innerHTML=`<option value="">انتخاب نوع سرویس</option>
        <option value="ساید">ساید</option>
        <option value="فیلتر دستگاه">فیلتر دستگاه</option>
        <option value="دیگر">دیگر</option>`;
      serviceInput.replaceWith(select);
    }
    if(!modal.querySelector('[x-model="serviceEdit.payment_method"]')){
      const status=modal.querySelector('select[x-model="serviceEdit.status"]');
      if(status){
        const payment=document.createElement('select');
        payment.setAttribute('x-model','serviceEdit.payment_method');
        payment.className='field';
        payment.innerHTML=`<option value="">روش پرداخت</option>
          <option value="cash">نقد</option>
          <option value="transfer">کارت‌به‌کارت</option>
          <option value="card">کارتخوان</option>
          <option value="cheque">چک</option>
          <option value="credit">نسیه</option>
          <option value="other">سایر</option>`;
        status.insertAdjacentElement('afterend',payment);
      }
    }
  };

  const patchBeforeAlpine=()=>{
    patchSmartDuplicates();
    patchDailyEditButton();
    patchServiceEditModal();
  };
  patchBeforeAlpine();

  const previous=window.app;
  if(typeof previous!=='function')return;

  window.app=function(){
    const state=previous();
    const oldRegisterSmart=state.registerSmart?.bind(state);
    const oldLoadBaleJobs=state.loadBaleJobs?.bind(state);
    const oldOpenServiceEdit=state.openServiceEdit?.bind(state);

    state.aquaMicRequestToken=0;
    state.aquaVoiceSeq=Number(state.aquaVoiceSeq||0);
    state.aquaVoiceCommittedRun=Number(state.aquaVoiceCommittedRun||0);

    state.baleAppointmentMinutes=function(job){
      const raw=faDigits(job?.time_text||job?.parsed?.time_text||job?.raw_text||'');
      const lines=raw.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
      const timeLine=lines.find(line=>/(شنبه|یکشنبه|دوشنبه|سه.?شنبه|چهارشنبه|پنجشنبه|جمعه|ساعت|الی|تا)/.test(line))||'';
      if(!timeLine)return 24*60+1;
      let match=timeLine.match(/(?:ساعت\s*)?([01]?\d|2[0-3])\s*[:٫.]\s*([0-5]\d)/);
      if(match)return Number(match[1])*60+Number(match[2]);
      match=timeLine.match(/(?:ساعت\s*)?([01]?\d|2[0-3])\s*(?:الی|تا)\s*(?:[01]?\d|2[0-3])/);
      if(match)return Number(match[1])*60;
      match=timeLine.match(/ساعت\s*([01]?\d|2[0-3])(?:\s*[:٫.]\s*([0-5]\d))?/);
      if(match)return Number(match[1])*60+Number(match[2]||0);
      return 24*60+1;
    };

    state.sortBaleJobsByAppointment=function(rows){
      return [...(rows||[])].sort((a,b)=>{
        const am=this.baleAppointmentMinutes(a),bm=this.baleAppointmentMinutes(b);
        if(am!==bm)return am-bm;
        const at=Date.parse(a?.received_at||a?.created_at||0)||0,bt=Date.parse(b?.received_at||b?.created_at||0)||0;
        return at-bt;
      });
    };

    state.loadBaleJobs=async function(tab=null){
      const result=await oldLoadBaleJobs?.(tab);
      const current=String(this.baleTab||tab||'new');
      if(current==='new'||current==='review')this.baleJobs=this.sortBaleJobsByAppointment(this.baleJobs);
      return result;
    };

    state.openServiceEdit=function(job){
      const result=oldOpenServiceEdit?.(job);
      this.serviceEdit=this.serviceEdit||{};
      this.serviceEdit.payment_method=clean(job?.payment_method);
      const current=clean(this.serviceEdit.service_type||job?.service_type);
      this.serviceEdit.service_type=current;
      queueMicrotask(()=>{
        const modal=[...document.querySelectorAll('[x-show="serviceEditOpen"]')][0];
        const select=modal?.querySelector('select[x-model="serviceEdit.service_type"]');
        if(!select||!current)return;
        const exists=[...select.options].some(option=>option.value===current);
        if(!exists){const option=document.createElement('option');option.value=current;option.textContent=current+' (ثبت‌شده)';select.appendChild(option)}
        select.value=current;
      });
      return result;
    };

    state.saveServiceEdit=async function(){
      if(this.serviceEditBusy)return;
      const id=clean(this.serviceEdit?.id);
      if(!id)return this.toast?.('سرویس برای ویرایش پیدا نشد','error');
      const serviceType=clean(this.serviceEdit?.service_type);
      if(!serviceType)return this.toast?.('نوع سرویس را انتخاب کن','error');
      this.serviceEditBusy=true;
      try{
        const payload={
          service_type:serviceType,
          description:clean(this.serviceEdit?.description),
          invoice_amount:this.num(this.serviceEdit?.invoice_amount),
          received_amount:this.num(this.serviceEdit?.received_amount),
          payment_method:clean(this.serviceEdit?.payment_method),
          status:clean(this.serviceEdit?.status)||'completed'
        };
        const response=await this.api('/jobs/'+id,{method:'PATCH',body:JSON.stringify(payload)});
        if(response?.queued){
          const pct=Number(this.financeSettings?.company_share_percent||0);
          const company=Math.round(payload.received_amount*pct/100);
          this.jobs=(this.jobs||[]).map(job=>String(job.id)===id?{
            ...job,...payload,
            company_share_percent:pct,
            company_share_amount:company,
            customer_balance:Math.max(payload.invoice_amount-payload.received_amount,0),
            overpayment_amount:Math.max(payload.received_amount-payload.invoice_amount,0),
            offline_pending:true
          }:job);
          this.serviceEditOpen=false;
          this.toast?.('ویرایش روی گوشی ذخیره شد و بعد از اتصال همگام می‌شود','success');
          return;
        }
        await this.refreshAll();
        try{await this.loadAquaDailyCancelled?.()}catch{}
        this.serviceEditOpen=false;
        if(this.page==='finance')setTimeout(()=>this.renderRound4Finance?.(),60);
        this.toast?.('ویرایش ذخیره شد؛ مبلغ‌ها و گزارش‌ها با مقدار جدید به‌روزرسانی شدند','success');
      }catch(error){
        this.toast?.(error?.message||'ویرایش سرویس ذخیره نشد','error');
      }finally{
        this.serviceEditBusy=false;
      }
    };

    state.registerSmart=async function(...args){
      const pending=this.baleSmartJob?{...this.baleSmartJob}:null;
      const savedOpenCustomer=this.openCustomer;
      if(pending&&typeof savedOpenCustomer==='function')this.openCustomer=async()=>{};
      let result;
      try{
        result=await oldRegisterSmart?.(...args);
      }finally{
        if(pending&&typeof savedOpenCustomer==='function')this.openCustomer=savedOpenCustomer;
      }
      if(!pending)return result;

      const finished=!this.smartParsed&&!clean(this.smartText);
      if(!finished)return result;

      const id=clean(pending.id);
      if(id)this.baleJobs=(this.baleJobs||[]).filter(job=>String(job.id)!==id);

      if(this.baleSmartJob&&String(this.baleSmartJob.id)===id){
        try{
          await this.api('/bale/jobs/'+id+'/finalize',{method:'POST',body:'{}'});
        }catch(error){
          const message=clean(error?.message);
          if(!/قبلاً تعیین تکلیف/.test(message)){
            this.toast?.(message||'ثبت انجام شد ولی بستن کار بله کامل نشد','error');
            return result;
          }
        }
      }

      this.baleSmartJob=null;
      this.smartText='';
      this.smartParsed=null;
      this.smartSuggestions=[];
      this.smartCustomerId='';
      this.smartGps={};
      this.selectedCustomer=null;
      this.selectedCustomerJobsRemote=[];
      try{
        await Promise.all([this.loadBaleCounts?.(),this.loadBaleJobs?.('new')]);
      }catch{}
      this.baleJobs=this.sortBaleJobsByAppointment(this.baleJobs);
      try{await this.go?.('bale-jobs')}catch{this.page='bale-jobs'}
      this.toast?.('ثبت شد و کار از فهرست کارهای بله خارج شد','success');
      return result;
    };

    state.toggleAquaRecording=async function(){
      const phase=this.aquaVoicePhase||'idle';
      if(phase==='recording'){
        this.setAquaVoicePhase?.('stopping');
        try{
          const recorder=this.aquaRecorder;
          if(recorder&&recorder.state!=='inactive'){
            try{recorder.requestData?.()}catch{}
            recorder.stop();
          }else this.setAquaVoicePhase?.('idle');
        }catch(error){
          this.setAquaVoicePhase?.('idle');
          this.toast?.(error?.message||'توقف ضبط انجام نشد','error');
        }
        return;
      }
      if(phase!=='idle'){
        if(phase==='starting'){
          this.aquaMicRequestToken=Number(this.aquaMicRequestToken||0)+1;
          try{this.aquaRecorder?.stop?.()}catch{}
          try{this.aquaStream?.getTracks?.().forEach(track=>track.stop())}catch{}
          this.aquaRecorder=null;this.aquaStream=null;
          this.setAquaVoicePhase?.('idle');
          this.toast?.('درخواست قبلی میکروفن لغو شد؛ دوباره بزن','info');
        }else{
          this.toast?.(phase==='transcribing'?'دارم صدات رو به متن تبدیل می‌کنم…':phase==='submitting'?'دارم همون پیام رو برای آریا می‌فرستم…':'ضبط قبلی هنوز کامل نشده…','info');
        }
        return;
      }
      if(this.aquaBusy||this.aquaSendLock||this.aquaSendPromise){
        this.toast?.('آریا هنوز در حال پاسخ‌دادنه؛ یک لحظه صبر کن','info');return;
      }
      if(!window.isSecureContext){
        this.toast?.('میکروفن فقط در اتصال امن HTTPS کار می‌کند','error');return;
      }
      if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){
        this.toast?.('ضبط صدا روی این مرورگر پشتیبانی نمی‌شود','error');return;
      }

      this.stopAquaSpeech?.();
      this.setAquaVoicePhase?.('starting');
      this.toast?.('در حال فعال‌کردن میکروفن…','info');

      const requestToken=Number(this.aquaMicRequestToken||0)+1;
      this.aquaMicRequestToken=requestToken;
      let stream=null,expired=false;
      const timeoutMs=15000;
      try{
        const mediaPromise=navigator.mediaDevices.getUserMedia({audio:true}).then(value=>{
          if(expired||requestToken!==this.aquaMicRequestToken){
            try{value?.getTracks?.().forEach(track=>track.stop())}catch{}
            throw Object.assign(new Error('درخواست میکروفن منقضی شد'),{name:'AquaMicTimeout'});
          }
          return value;
        });
        const timeoutPromise=new Promise((_,reject)=>setTimeout(()=>{
          expired=true;
          reject(Object.assign(new Error('اجازه میکروفن از iPhone دریافت نشد'),{name:'AquaMicTimeout'}));
        },timeoutMs));
        stream=await Promise.race([mediaPromise,timeoutPromise]);
        if(requestToken!==this.aquaMicRequestToken)throw Object.assign(new Error('درخواست میکروفن لغو شد'),{name:'AbortError'});

        try{await this.primeAquaAudio?.()}catch{}
        const mime=pickMime();
        const recorder=mime?new MediaRecorder(stream,{mimeType:mime}):new MediaRecorder(stream);
        const runId=++this.aquaVoiceSeq,parts=[];
        let finalized=false;
        this.aquaRecorder=recorder;this.aquaStream=stream;

        recorder.ondataavailable=event=>{if(event.data?.size)parts.push(event.data)};
        recorder.onerror=event=>this.toast?.(event?.error?.message||'خطای ضبط صدا','error');
        recorder.onstop=async()=>{
          if(finalized)return;finalized=true;
          try{stream?.getTracks?.().forEach(track=>track.stop())}catch{}
          if(runId!==this.aquaVoiceSeq){this.setAquaVoicePhase?.('idle');return}
          this.setAquaVoicePhase?.('transcribing');
          try{
            if(!parts.length)throw Error('صدایی ثبت نشد؛ دوباره امتحان کن');
            const type=recorder.mimeType||mime||parts[0]?.type||'audio/webm';
            const blob=new Blob(parts,{type});
            if(blob.size<256)throw Error('ویس خیلی کوتاه بود؛ دوباره امتحان کن');
            const extension=type.includes('mp4')?'m4a':type.includes('ogg')?'ogg':type.includes('wav')?'wav':'webm';
            const form=new FormData();form.append('audio',blob,'aqua.'+extension);
            const headers={},csrf=this.cookie?.('aquagold_csrf');if(csrf)headers['X-CSRF-Token']=csrf;
            const response=await fetch('/api/aqua-ai/transcribe',{method:'POST',body:form,headers,credentials:'same-origin',cache:'no-store'});
            let data={};try{data=await response.json()}catch{}
            if(!response.ok)throw Error(data.error||'تبدیل ویس به متن انجام نشد');
            const spoken=clean(data.text);
            if(!spoken)throw Error('حرفی از ویس تشخیص داده نشد');
            if(runId!==this.aquaVoiceSeq)return;
            this.aquaInput=spoken;
            this.setAquaVoicePhase?.('submitting');
            this.toast?.('صدات گرفته شد؛ دارم برای آریا می‌فرستم…','success');
            const sent=await this.submitAquaVoiceTranscript?.(spoken,runId);
            this.aquaInput=sent?'':spoken;
            if(!sent)this.toast?.('متن ویس در کادر ماند؛ دکمه ارسال را بزن','info');
          }catch(error){
            this.toast?.(error?.message||'ویس پردازش نشد','error');
          }finally{
            if(runId===this.aquaVoiceSeq){
              this.aquaRecorder=null;this.aquaStream=null;this.setAquaVoicePhase?.('idle');
            }
          }
        };

        recorder.start(250);
        this.setAquaVoicePhase?.('recording');
        this.toast?.('آریا گوش می‌ده؛ وقتی تموم شد دوباره میکروفن رو بزن','success');
      }catch(error){
        expired=true;
        try{stream?.getTracks?.().forEach(track=>track.stop())}catch{}
        this.aquaRecorder=null;this.aquaStream=null;
        this.setAquaVoicePhase?.('idle');
        const name=String(error?.name||'');
        if(name==='NotAllowedError'||name==='SecurityError'){
          this.toast?.('اجازه میکروفن بسته است؛ مجوز Microphone همین سایت را روی Allow بگذار و دوباره بزن','error');
        }else if(name==='AquaMicTimeout'){
          this.toast?.('پنجره اجازه میکروفن باز نشد یا بی‌پاسخ ماند؛ درخواست ریست شد. مجوز Microphone سایت را روی Allow بگذار و دوباره بزن','error');
        }else if(name!=='AbortError'){
          this.toast?.(error?.message||'دسترسی میکروفن یا شروع ضبط انجام نشد','error');
        }
      }
    };

    return state;
  };

  const keepPatched=()=>{
    patchSmartDuplicates();
    patchDailyEditButton();
    patchServiceEditModal();
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',keepPatched,{once:true});
  else keepPatched();
  const observer=new MutationObserver(()=>keepPatched());
  observer.observe(document.documentElement,{childList:true,subtree:true});
})();