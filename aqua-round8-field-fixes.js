(()=>{
  if(window.__aquaRound8FieldFixes)return;
  window.__aquaRound8FieldFixes=true;

  const clean=value=>String(value??'').trim();
  const isIOS=()=>/iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
  const pickMime=()=>{
    for(const value of ['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus','audio/mp4']){
      try{if(window.MediaRecorder?.isTypeSupported?.(value))return value}catch{}
    }
    return '';
  };
  const stopKeeper=async state=>{
    try{
      const keeper=state?.aquaAudioKeeper;
      keeper?.osc?.stop?.();
      keeper?.osc?.disconnect?.();
      keeper?.gain?.disconnect?.();
      state.aquaAudioKeeper=null;
    }catch{}
    try{
      if(state?.aquaAudioContext?.state==='running')await state.aquaAudioContext.suspend?.();
    }catch{}
    try{window.speechSynthesis?.cancel?.()}catch{}
  };

  const previous=window.app;
  if(typeof previous==='function'){
    window.app=function(){
      const state=previous();
      state.aquaMicRequestToken=Number(state.aquaMicRequestToken||0);
      state.aquaVoiceSeq=Number(state.aquaVoiceSeq||0);
      state.aquaVoiceStopRequestedRun=Number(state.aquaVoiceStopRequestedRun||0);

      state.toggleAquaRecording=async function(){
        const phase=this.aquaVoicePhase||(this.aquaRecording?'recording':'idle');

        if(phase==='recording'||this.aquaRecording){
          const recorder=this.aquaRecorder;
          if(!recorder||recorder.state==='inactive'){
            this.aquaRecording=false;
            this.setAquaVoicePhase?.('idle');
            return;
          }
          this.aquaVoiceStopRequestedRun=Number(this.aquaVoiceSeq||0);
          this.setAquaVoicePhase?.('stopping');
          try{recorder.requestData?.()}catch{}
          try{recorder.stop()}catch(error){
            this.aquaRecording=false;
            this.setAquaVoicePhase?.('idle');
            this.toast?.(error?.message||'توقف ضبط انجام نشد','error');
          }
          return;
        }

        if(phase==='starting'){
          this.aquaMicRequestToken=Number(this.aquaMicRequestToken||0)+1;
          try{this.aquaStream?.getTracks?.().forEach(track=>track.stop())}catch{}
          this.aquaStream=null;
          this.aquaRecorder=null;
          this.aquaRecording=false;
          this.setAquaVoicePhase?.('idle');
          this.toast?.('درخواست میکروفن لغو شد؛ دوباره بزن','info');
          return;
        }

        if(phase!=='idle'||this.aquaTranscribing||this.aquaVoiceSending||this.aquaBusy||this.aquaVoiceSubmitActive||this.aquaSendLock||this.aquaSendPromise){
          this.toast?.(
            phase==='transcribing'?'دارم صدات رو به متن تبدیل می‌کنم…':
            phase==='submitting'?'دارم پیام رو برای آریا می‌فرستم…':
            'کار قبلی آریا هنوز کامل نشده…',
            'info'
          );
          return;
        }

        if(!window.isSecureContext){
          this.toast?.('میکروفن فقط روی اتصال امن HTTPS کار می‌کند','error');
          return;
        }
        if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){
          this.toast?.('ضبط صدا روی این مرورگر پشتیبانی نمی‌شود','error');
          return;
        }

        this.stopAquaSpeech?.();
        await stopKeeper(this);
        this.setAquaVoicePhase?.('starting');
        this.aquaRecording=false;
        this.toast?.('در حال فعال‌کردن میکروفن…','info');

        const requestToken=Number(this.aquaMicRequestToken||0)+1;
        this.aquaMicRequestToken=requestToken;
        let stream=null;
        let timeoutId=null;

        try{
          const mediaPromise=navigator.mediaDevices.getUserMedia({audio:true});
          const timeoutPromise=new Promise((_,reject)=>{
            timeoutId=setTimeout(()=>reject(Object.assign(new Error('اجازه میکروفن از iPhone دریافت نشد'),{name:'AquaMicTimeout'})),15000);
          });
          stream=await Promise.race([mediaPromise,timeoutPromise]);
          clearTimeout(timeoutId);

          if(requestToken!==this.aquaMicRequestToken){
            try{stream?.getTracks?.().forEach(track=>track.stop())}catch{}
            throw Object.assign(new Error('درخواست میکروفن لغو شد'),{name:'AbortError'});
          }

          const track=stream?.getAudioTracks?.()[0];
          if(!track||track.readyState!=='live')throw new Error('میکروفن فعال نشد');

          const ios=isIOS();
          const mime=ios?'':pickMime();
          const recorder=mime?new MediaRecorder(stream,{mimeType:mime}):new MediaRecorder(stream);
          const runId=Number(this.aquaVoiceSeq||0)+1;
          this.aquaVoiceSeq=runId;
          this.aquaVoiceStopRequestedRun=0;
          const parts=[];
          let finalized=false;
          let started=false;

          this.aquaRecorder=recorder;
          this.aquaStream=stream;
          this.aquaChunks=parts;

          recorder.onstart=()=>{
            started=true;
            if(runId!==this.aquaVoiceSeq)return;
            this.aquaRecording=true;
            this.setAquaVoicePhase?.('recording');
            this.toast?.('آریا گوش می‌ده؛ وقتی تموم شد دوباره میکروفن رو بزن','success');
          };

          recorder.ondataavailable=event=>{
            if(event.data?.size)parts.push(event.data);
          };

          recorder.onerror=event=>{
            this.toast?.(event?.error?.message||'خطای ضبط صدا','error');
          };

          recorder.onstop=async()=>{
            if(finalized)return;
            finalized=true;
            const intentional=Number(this.aquaVoiceStopRequestedRun||0)===runId;
            this.aquaRecording=false;
            try{stream?.getTracks?.().forEach(item=>item.stop())}catch{}

            if(runId!==this.aquaVoiceSeq){
              this.setAquaVoicePhase?.('idle');
              return;
            }

            if(!intentional){
              this.aquaRecorder=null;
              this.aquaStream=null;
              this.setAquaVoicePhase?.('idle');
              this.toast?.(
                started?'ضبط صدا توسط iPhone ناگهانی قطع شد؛ دوباره میکروفن را بزن':'میکروفن شروع نشد؛ دوباره امتحان کن',
                'error'
              );
              return;
            }

            this.setAquaVoicePhase?.('transcribing');
            this.aquaTranscribing=true;

            try{
              if(!parts.length)throw new Error('صدایی ثبت نشد؛ دوباره امتحان کن');
              const type=recorder.mimeType||mime||parts[0]?.type||'audio/mp4';
              const blob=new Blob(parts,{type});
              if(blob.size<256)throw new Error('ویس خیلی کوتاه بود؛ دوباره امتحان کن');

              const extension=type.includes('mp4')?'m4a':type.includes('ogg')?'ogg':type.includes('wav')?'wav':'webm';
              const form=new FormData();
              form.append('audio',blob,'aqua.'+extension);
              const headers={};
              const csrf=this.cookie?.('aquagold_csrf');
              if(csrf)headers['X-CSRF-Token']=csrf;

              const response=await fetch('/api/aqua-ai/transcribe',{
                method:'POST',
                body:form,
                headers,
                credentials:'same-origin',
                cache:'no-store'
              });
              let data={};
              try{data=await response.json()}catch{}
              if(!response.ok)throw new Error(data.error||'تبدیل ویس به متن انجام نشد');

              const spoken=clean(data.text);
              if(!spoken)throw new Error('حرفی از ویس تشخیص داده نشد');
              if(runId!==this.aquaVoiceSeq)return;

              this.aquaInput=spoken;
              this.aquaTranscribing=false;
              this.setAquaVoicePhase?.('submitting');
              this.aquaVoiceSubmitActive=true;
              this.toast?.('صدات گرفته شد؛ دارم برای آریا می‌فرستم…','success');

              let sent=false;
              if(typeof this.submitAquaVoiceTranscript==='function'){
                sent=await this.submitAquaVoiceTranscript(spoken,runId);
              }else if(typeof this.submitAquaText==='function'){
                sent=await this.submitAquaText(spoken,'voice');
              }
              this.aquaInput=sent?'':spoken;
              if(!sent)this.toast?.('متن ویس در کادر ماند؛ دکمه ارسال را بزن','info');
            }catch(error){
              this.toast?.(error?.message||'ویس پردازش نشد','error');
            }finally{
              if(runId===this.aquaVoiceSeq){
                this.aquaTranscribing=false;
                this.aquaVoiceSubmitActive=false;
                this.aquaRecorder=null;
                this.aquaStream=null;
                this.setAquaVoicePhase?.('idle');
              }
            }
          };

          track.addEventListener?.('ended',()=>{
            if(recorder.state!=='inactive'){
              try{recorder.stop()}catch{}
            }
          },{once:true});

          // Safari/iOS is more stable when it chooses its own MP4 container and
          // receives no timeslice. Non-iOS browsers can keep periodic chunks.
          if(ios)recorder.start();
          else recorder.start(250);

          setTimeout(()=>{
            if(runId!==this.aquaVoiceSeq||started||recorder.state==='inactive')return;
            this.aquaRecording=true;
            this.setAquaVoicePhase?.('recording');
          },500);
        }catch(error){
          clearTimeout(timeoutId);
          try{stream?.getTracks?.().forEach(track=>track.stop())}catch{}
          this.aquaRecorder=null;
          this.aquaStream=null;
          this.aquaRecording=false;
          this.setAquaVoicePhase?.('idle');
          const name=String(error?.name||'');
          if(name==='NotAllowedError'||name==='SecurityError'){
            this.toast?.('اجازه میکروفن بسته است؛ Microphone این سایت را روی Allow بگذار','error');
          }else if(name==='AquaMicTimeout'){
            this.toast?.('اجازه میکروفن از iPhone نرسید؛ مجوز Microphone سایت را بررسی کن','error');
          }else if(name!=='AbortError'){
            this.toast?.(error?.message||'شروع ضبط صدا انجام نشد','error');
          }
        }
      };

      return state;
    };
  }

  const appState=()=>{
    try{
      const data=window.Alpine?.$data?.(document.body);
      if(data&&typeof data.openServiceEdit==='function')return data;
    }catch{}
    try{
      for(const el of document.querySelectorAll('[x-data]')){
        const data=window.Alpine?.$data?.(el);
        if(data&&typeof data.openServiceEdit==='function')return data;
      }
    }catch{}
    return null;
  };

  const patchDailyTemplate=()=>{
    const section=[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='daily'"));
    if(!section)return;
    const template=[...section.querySelectorAll('template')].find(el=>(el.getAttribute('x-for')||'').includes('d.completedJobs'));
    if(!template)return;
    template.innerHTML=`<div class="px-4 py-3 border-b flex items-center justify-between gap-3" style="border-color:var(--line)" data-aqua-daily-row :data-aqua-job-id="j.id">
      <b class="min-w-0 truncate" x-text="dailySurname(j)"></b>
      <div class="flex items-center gap-2 shrink-0">
        <b class="text-emerald-500" x-text="money(j.received_amount)+' تومان'"></b>
        <button type="button" class="btn soft !py-1.5 !px-3 no-print" data-aqua-daily-edit>ویرایش</button>
      </div>
    </div>`;
  };

  const resolveDailyJob=button=>{
    const row=button.closest('[data-aqua-daily-row], [data-aqua-daily-completed-row], .px-4.py-3.border-b');
    let local=null;
    try{local=window.Alpine?.$data?.(row)}catch{}
    if(local?.j)return local.j;
    const id=row?.getAttribute?.('data-aqua-job-id')||row?.dataset?.aquaJobId;
    const app=appState();
    if(id&&app){
      return (app.jobs||[]).find(job=>String(job?.id)===String(id))||
             (app.dailyGroups||[]).flatMap(group=>group.completedJobs||[]).find(job=>String(job?.id)===String(id))||
             null;
    }
    return null;
  };

  document.addEventListener('click',event=>{
    const button=event.target?.closest?.('[data-aqua-daily-edit]');
    if(!button)return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const job=resolveDailyJob(button);
    const app=appState();
    if(!job||!app){
      app?.toast?.('سرویس برای ویرایش پیدا نشد','error');
      return;
    }
    app.openServiceEdit(job);
  },true);

  document.addEventListener('alpine:init',patchDailyTemplate,{once:true});
  document.addEventListener('alpine:initialized',()=>setTimeout(patchDailyTemplate,0),{once:true});

  const newLoader='/assets/aquagold-loading-v20260906b.jpg?aqua-loader-exact-2';
  const keepNewLoader=()=>{
    const image=document.querySelector('#aqua-boot-20260906 img');
    if(image&&image.getAttribute('src')!==newLoader)image.setAttribute('src',newLoader);
    document.querySelectorAll('link[rel="preload"][as="image"],link[rel="apple-touch-startup-image"]').forEach(link=>{
      const href=link.getAttribute('href')||'';
      if(/aquagold-loading-v(?:64|20260906|20260906b)\.jpg/.test(href))link.setAttribute('href',newLoader);
    });
  };
  keepNewLoader();
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',keepNewLoader,{once:true});
  const loaderObserver=new MutationObserver(keepNewLoader);
  loaderObserver.observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['src','href']});
})();