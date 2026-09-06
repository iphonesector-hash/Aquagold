(()=>{
  if(window.__aquaRound9MicDaily)return;
  window.__aquaRound9MicDaily=true;

  const clean=value=>String(value??'').trim();
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const isIOS=()=>/iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);

  const rootStateFrom=el=>{
    const stacks=[];
    try{if(Array.isArray(el?._x_dataStack))stacks.push(...el._x_dataStack)}catch{}
    try{if(Array.isArray(document.body?._x_dataStack))stacks.push(...document.body._x_dataStack)}catch{}
    for(const state of stacks){
      if(state&&(typeof state.openServiceEdit==='function'||Object.prototype.hasOwnProperty.call(state,'serviceEditOpen')))return state;
    }
    try{
      const state=window.Alpine?.$data?.(document.body);
      if(state&&(typeof state.openServiceEdit==='function'||'serviceEditOpen' in state))return state;
    }catch{}
    return null;
  };

  const openDailyEdit=(job,el)=>{
    const state=rootStateFrom(el);
    if(!state||!job)return false;
    try{
      if(typeof state.openServiceEdit==='function')state.openServiceEdit(job);
    }catch{}
    if(!state.serviceEditOpen){
      state.serviceEdit={
        id:job?.id||null,
        service_type:job?.service_type||'',
        description:job?.description||'',
        invoice_amount:Number(job?.invoice_amount||0),
        received_amount:Number(job?.received_amount||0),
        payment_method:job?.payment_method||'',
        status:job?.status||'completed',
      };
      state.serviceEditOpen=true;
    }
    return !!state.serviceEditOpen;
  };
  window.__aquaOpenDailyServiceEdit=openDailyEdit;

  const patchDailyTemplate=()=>{
    const section=[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='daily'"));
    if(!section)return;
    const template=[...section.querySelectorAll('template')].find(el=>(el.getAttribute('x-for')||'').includes('j in d.jobs'));
    if(!template)return;
    template.innerHTML=`<div class="p-4 border-b flex items-center justify-between gap-3" style="border-color:var(--line)" data-aqua-daily-row>
      <div class="min-w-0">
        <b x-text="j.name"></b>
        <div class="text-xs muted mt-1" x-text="j.description||j.service_type||'سرویس'"></div>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <b x-text="money(j.received_amount)+' تومان'"></b>
        <button type="button" class="btn soft !py-1.5 !px-3 no-print" data-aqua-daily-edit @click.stop.prevent="window.__aquaOpenDailyServiceEdit(j,$el)">ویرایش</button>
      </div>
    </div>`;
  };

  patchDailyTemplate();
  document.addEventListener('alpine:init',patchDailyTemplate,{once:true});
  document.addEventListener('click',event=>{
    const button=event.target?.closest?.('[data-aqua-daily-edit]');
    if(!button)return;
    let job=null;
    try{
      for(const scope of button._x_dataStack||[]){if(scope?.j){job=scope.j;break}}
    }catch{}
    if(!job)return;
    if(openDailyEdit(job,button)){
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  },true);

  const stopPlaybackForMic=async state=>{
    try{state.stopAquaSpeech?.()}catch{}
    try{window.speechSynthesis?.cancel?.()}catch{}
    try{
      const keeper=state.aquaAudioKeeper;
      keeper?.osc?.stop?.();keeper?.osc?.disconnect?.();keeper?.gain?.disconnect?.();
      state.aquaAudioKeeper=null;
    }catch{}
    try{if(state.aquaAudioContext?.state==='running')await state.aquaAudioContext.suspend?.()}catch{}
  };

  const previous=window.app;
  if(typeof previous!=='function')return;
  window.app=function(){
    const state=previous();
    state.aquaMicRun=Number(state.aquaMicRun||0);
    state.aquaMicStopRun=0;
    state.aquaMicFinalizing=false;

    state.toggleAquaRecording=async function(){
      const phase=this.aquaVoicePhase||(this.aquaRecording?'recording':'idle');

      if(phase==='recording'||this.aquaRecording){
        const recorder=this.aquaRecorder;
        if(!recorder||recorder.state==='inactive'){
          this.aquaRecording=false;
          this.setAquaVoicePhase?.('idle');
          return;
        }
        this.aquaMicStopRun=Number(this.aquaMicRun||0);
        this.setAquaVoicePhase?.('stopping');
        try{recorder.stop()}catch(error){
          this.setAquaVoicePhase?.('idle');
          this.toast?.(error?.message||'توقف ضبط انجام نشد','error');
        }
        return;
      }

      if(phase!=='idle'||this.aquaTranscribing||this.aquaVoiceSending||this.aquaBusy||this.aquaSendLock||this.aquaSendPromise){
        this.toast?.(phase==='transcribing'?'دارم صدات رو به متن تبدیل می‌کنم…':phase==='submitting'?'دارم پیام ویس رو می‌فرستم…':'کار قبلی آریا هنوز کامل نشده…','info');
        return;
      }
      if(!window.isSecureContext){this.toast?.('میکروفن فقط روی HTTPS کار می‌کند','error');return}
      if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){this.toast?.('ضبط صدا روی این مرورگر پشتیبانی نمی‌شود','error');return}

      await stopPlaybackForMic(this);
      this.setAquaVoicePhase?.('starting');
      this.aquaRecording=false;
      let stream=null;
      try{
        stream=await navigator.mediaDevices.getUserMedia({audio:true});
        const track=stream?.getAudioTracks?.()[0];
        if(!track||track.readyState!=='live')throw new Error('میکروفن فعال نشد');

        const recorder=new MediaRecorder(stream);
        const runId=Number(this.aquaMicRun||0)+1;
        this.aquaMicRun=runId;
        this.aquaMicStopRun=0;
        this.aquaMicFinalizing=false;
        const chunks=[];
        let stopped=false;
        let finalizeTimer=null;
        let started=false;

        this.aquaRecorder=recorder;
        this.aquaStream=stream;
        this.aquaChunks=chunks;

        const cleanup=()=>{
          if(finalizeTimer)clearTimeout(finalizeTimer);
          try{stream?.getTracks?.().forEach(t=>t.stop())}catch{}
          if(runId===this.aquaMicRun){
            this.aquaRecorder=null;this.aquaStream=null;this.aquaRecording=false;this.aquaTranscribing=false;this.aquaVoiceSending=false;this.aquaVoiceSubmitActive=false;
            this.setAquaVoicePhase?.('idle');
          }
        };

        const finalize=async()=>{
          if(this.aquaMicFinalizing||runId!==this.aquaMicRun)return;
          this.aquaMicFinalizing=true;
          const intentional=Number(this.aquaMicStopRun||0)===runId;
          if(!intentional){
            cleanup();
            this.toast?.('ضبط توسط iPhone ناگهانی قطع شد؛ دوباره امتحان کن','error');
            return;
          }
          this.aquaTranscribing=true;
          this.setAquaVoicePhase?.('transcribing');
          try{
            for(let i=0;i<6&&!chunks.length;i++)await sleep(120);
            if(!chunks.length)throw new Error('iPhone فایل صدا را تحویل نداد؛ دوباره ضبط کن');
            const type=recorder.mimeType||chunks.find(x=>x?.type)?.type||(isIOS()?'audio/mp4':'audio/webm');
            const blob=new Blob(chunks,{type});
            if(blob.size<128)throw new Error('ویس خیلی کوتاه بود؛ دوباره امتحان کن');
            const ext=type.includes('mp4')?'m4a':type.includes('ogg')?'ogg':'webm';
            const form=new FormData();
            form.append('audio',blob,'aqua.'+ext);
            const headers={};
            const csrf=this.cookie?.('aquagold_csrf');
            if(csrf)headers['X-CSRF-Token']=csrf;

            const response=await fetch('/api/aqua-ai/transcribe',{method:'POST',body:form,headers,credentials:'same-origin',cache:'no-store'});
            let data={};try{data=await response.json()}catch{}
            if(!response.ok)throw new Error(data.error||'تبدیل ویس به متن انجام نشد');
            const spoken=clean(data.text);
            if(!spoken)throw new Error('حرفی از ویس تشخیص داده نشد');
            if(runId!==this.aquaMicRun)return;

            this.aquaInput=spoken;
            this.aquaTranscribing=false;
            this.setAquaVoicePhase?.('submitting');
            this.toast?.('ویس تبدیل شد؛ دارم برای آریا می‌فرستم…','success');
            let sent=false;
            if(typeof this.submitAquaText==='function')sent=await this.submitAquaText(spoken,'voice',runId);
            else if(typeof this.submitAquaVoiceTranscript==='function')sent=await this.submitAquaVoiceTranscript(spoken,runId);
            this.aquaInput=sent?'':spoken;
            if(!sent)this.toast?.('متن ویس آماده شد ولی ارسال خودکار انجام نشد','error');
          }catch(error){
            this.toast?.(error?.message||'ویس پردازش نشد','error');
          }finally{
            cleanup();
          }
        };

        const scheduleFinalize=()=>{
          if(!stopped||runId!==this.aquaMicRun)return;
          if(finalizeTimer)clearTimeout(finalizeTimer);
          finalizeTimer=setTimeout(finalize,isIOS()?420:120);
        };

        recorder.onstart=()=>{
          started=true;
          if(runId!==this.aquaMicRun)return;
          this.aquaRecording=true;
          this.setAquaVoicePhase?.('recording');
          this.toast?.('آریا گوش می‌ده؛ برای پایان دوباره میکروفن رو بزن','success');
        };
        recorder.ondataavailable=event=>{
          if(event.data?.size)chunks.push(event.data);
          if(stopped)scheduleFinalize();
        };
        recorder.onerror=event=>{this.toast?.(event?.error?.message||'خطای ضبط صدا','error')};
        recorder.onstop=()=>{stopped=true;this.aquaRecording=false;scheduleFinalize()};
        track.addEventListener?.('ended',()=>{
          if(recorder.state!=='inactive'){
            try{recorder.stop()}catch{}
          }
        },{once:true});

        if(isIOS())recorder.start();else recorder.start(500);
        setTimeout(()=>{
          if(runId!==this.aquaMicRun||started||recorder.state==='inactive')return;
          this.aquaRecording=true;this.setAquaVoicePhase?.('recording');
        },600);
      }catch(error){
        try{stream?.getTracks?.().forEach(track=>track.stop())}catch{}
        this.aquaRecorder=null;this.aquaStream=null;this.aquaRecording=false;this.setAquaVoicePhase?.('idle');
        const name=String(error?.name||'');
        if(name==='NotAllowedError'||name==='SecurityError')this.toast?.('اجازه میکروفن بسته است؛ Microphone سایت را روی Allow بگذار','error');
        else this.toast?.(error?.message||'شروع ضبط صدا انجام نشد','error');
      }
    };

    return state;
  };
})();
