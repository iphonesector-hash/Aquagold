(()=>{
  if(window.__aquaRound8MicEditOnly)return;
  window.__aquaRound8MicEditOnly=true;

  const clean=value=>String(value??'').trim();
  const isIOS=()=>/iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);

  const appState=()=>{
    try{
      const data=window.Alpine?.$data?.(document.body);
      if(data&&typeof data.openServiceEdit==='function')return data;
    }catch{}
    try{
      for(const root of document.querySelectorAll('[x-data]')){
        const data=window.Alpine?.$data?.(root);
        if(data&&typeof data.openServiceEdit==='function')return data;
      }
    }catch{}
    return null;
  };

  const stopPlaybackForMic=async state=>{
    try{state.stopAquaSpeech?.()}catch{}
    try{
      const keeper=state.aquaAudioKeeper;
      keeper?.osc?.stop?.();
      keeper?.osc?.disconnect?.();
      keeper?.gain?.disconnect?.();
      state.aquaAudioKeeper=null;
    }catch{}
    try{
      if(state.aquaAudioContext?.state==='running')await state.aquaAudioContext.suspend?.();
    }catch{}
    try{window.speechSynthesis?.cancel?.()}catch{}
  };

  const previous=window.app;
  if(typeof previous==='function'){
    window.app=function(){
      const state=previous();
      state.aquaRound8StopRun=Number(state.aquaRound8StopRun||0);

      state.toggleAquaRecording=async function(){
        const phase=this.aquaVoicePhase||(this.aquaRecording?'recording':'idle');

        if(phase==='recording'||this.aquaRecording){
          const recorder=this.aquaRecorder;
          if(!recorder||recorder.state==='inactive'){
            this.aquaRecording=false;
            this.setAquaVoicePhase?.('idle');
            return;
          }
          this.aquaRound8StopRun=Number(this.aquaVoiceSeq||0);
          this.setAquaVoicePhase?.('stopping');
          try{recorder.requestData?.()}catch{}
          try{recorder.stop()}catch(error){
            this.aquaRecording=false;
            this.setAquaVoicePhase?.('idle');
            this.toast?.(error?.message||'توقف ضبط انجام نشد','error');
          }
          return;
        }

        if(phase!=='idle'||this.aquaTranscribing||this.aquaVoiceSending||this.aquaBusy||this.aquaVoiceSubmitActive||this.aquaSendLock||this.aquaSendPromise){
          this.toast?.(
            phase==='transcribing'?'دارم صدات رو به متن تبدیل می‌کنم…':
            phase==='submitting'?'دارم همون پیام رو برای آریا می‌فرستم…':
            'کار قبلی آریا هنوز کامل نشده…',
            'info'
          );
          return;
        }
        if(!window.isSecureContext){
          this.toast?.('میکروفن فقط روی HTTPS کار می‌کند','error');
          return;
        }
        if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){
          this.toast?.('ضبط صدا روی این مرورگر پشتیبانی نمی‌شود','error');
          return;
        }

        await stopPlaybackForMic(this);
        this.setAquaVoicePhase?.('starting');
        this.aquaRecording=false;
        this.toast?.('در حال فعال‌کردن میکروفن…','info');

        let stream=null;
        try{
          stream=await navigator.mediaDevices.getUserMedia({audio:true});
          const track=stream?.getAudioTracks?.()[0];
          if(!track||track.readyState!=='live')throw new Error('میکروفن فعال نشد');

          const recorder=new MediaRecorder(stream);
          // Use the canonical Voice Controller sequence. submitAquaVoiceTranscript
          // rejects any run whose id does not equal aquaVoiceSeq.
          const runId=Number(this.aquaVoiceSeq||0)+1;
          this.aquaVoiceSeq=runId;
          this.aquaRound8StopRun=0;
          const chunks=[];
          let started=false;
          let finalized=false;

          this.aquaRecorder=recorder;
          this.aquaStream=stream;
          this.aquaChunks=chunks;

          recorder.onstart=()=>{
            started=true;
            if(runId!==this.aquaVoiceSeq)return;
            this.aquaRecording=true;
            this.setAquaVoicePhase?.('recording');
            this.toast?.('آریا گوش می‌ده؛ برای پایان دوباره میکروفن رو بزن','success');
          };

          recorder.ondataavailable=event=>{
            if(event.data?.size)chunks.push(event.data);
          };

          recorder.onerror=event=>{
            this.toast?.(event?.error?.message||'خطای ضبط صدا','error');
          };

          recorder.onstop=async()=>{
            if(finalized)return;
            finalized=true;
            const intentional=Number(this.aquaRound8StopRun||0)===runId;
            this.aquaRecording=false;
            try{stream?.getTracks?.().forEach(item=>item.stop())}catch{}

            if(runId!==this.aquaVoiceSeq)return;
            if(!intentional){
              this.aquaRecorder=null;
              this.aquaStream=null;
              this.setAquaVoicePhase?.('idle');
              this.toast?.(started?'ضبط توسط iPhone ناگهانی قطع شد؛ دوباره امتحان کن':'میکروفن شروع نشد؛ دوباره امتحان کن','error');
              return;
            }

            this.aquaTranscribing=true;
            this.setAquaVoicePhase?.('transcribing');
            try{
              if(!chunks.length)throw new Error('صدایی ثبت نشد؛ دوباره امتحان کن');
              const type=recorder.mimeType||chunks[0]?.type||(isIOS()?'audio/mp4':'audio/webm');
              const blob=new Blob(chunks,{type});
              if(blob.size<256)throw new Error('ویس خیلی کوتاه بود؛ دوباره امتحان کن');

              const ext=type.includes('mp4')?'m4a':type.includes('ogg')?'ogg':'webm';
              const form=new FormData();
              form.append('audio',blob,'aqua.'+ext);
              const headers={};
              const csrf=this.cookie?.('aquagold_csrf');
              if(csrf)headers['X-CSRF-Token']=csrf;

              const response=await fetch('/api/aqua-ai/transcribe',{
                method:'POST',body:form,headers,credentials:'same-origin',cache:'no-store'
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
              this.toast?.('صدات گرفته شد؛ دارم برای آریا می‌فرستم…','success');

              let sent=false;
              // Call the canonical exactly-once submitter with the exact same run id.
              if(typeof this.submitAquaVoiceTranscript==='function'){
                sent=await this.submitAquaVoiceTranscript(spoken,runId);
              }else if(typeof this.submitAquaText==='function'){
                sent=await this.submitAquaText(spoken,'voice',runId);
              }
              this.aquaInput=sent?'':spoken;
              if(!sent)this.toast?.('ارسال خودکار انجام نشد؛ متن در کادر ماند','error');
            }catch(error){
              this.toast?.(error?.message||'ویس پردازش نشد','error');
            }finally{
              if(runId===this.aquaVoiceSeq){
                this.aquaTranscribing=false;
                this.aquaVoiceSubmitActive=false;
                this.aquaVoiceSending=false;
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

          // Let Safari choose its native container and avoid timeslice on iOS.
          if(isIOS())recorder.start();
          else recorder.start(250);

          setTimeout(()=>{
            if(runId!==this.aquaVoiceSeq||started||recorder.state==='inactive')return;
            this.aquaRecording=true;
            this.setAquaVoicePhase?.('recording');
          },500);
        }catch(error){
          try{stream?.getTracks?.().forEach(track=>track.stop())}catch{}
          this.aquaRecorder=null;
          this.aquaStream=null;
          this.aquaRecording=false;
          this.setAquaVoicePhase?.('idle');
          const name=String(error?.name||'');
          if(name==='NotAllowedError'||name==='SecurityError')this.toast?.('اجازه میکروفن بسته است؛ Microphone سایت را روی Allow بگذار','error');
          else this.toast?.(error?.message||'شروع ضبط صدا انجام نشد','error');
        }
      };
      return state;
    };
  }

  const patchDailyTemplate=()=>{
    const section=[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='daily'"));
    if(!section)return;
    const template=[...section.querySelectorAll('template')].find(el=>{
      const expr=el.getAttribute('x-for')||'';
      return expr.includes('j in d.jobs');
    });
    if(!template||template.dataset.aquaRound8Daily==='1')return;
    template.dataset.aquaRound8Daily='1';
    template.innerHTML=`<div class="p-4 border-b flex items-center justify-between gap-3" style="border-color:var(--line)" data-aqua-daily-row :data-aqua-job-id="j.id">
      <div class="min-w-0">
        <b x-text="j.name"></b>
        <div class="text-xs muted mt-1" x-text="j.description||j.service_type||'سرویس'"></div>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <b x-text="money(j.received_amount)+' تومان'"></b>
        <button type="button" class="btn soft !py-1.5 !px-3 no-print" data-aqua-daily-edit :data-aqua-job-id="j.id">ویرایش</button>
      </div>
    </div>`;
  };

  patchDailyTemplate();
  document.addEventListener('alpine:init',patchDailyTemplate,{once:true});

  document.addEventListener('click',event=>{
    const button=event.target?.closest?.('[data-aqua-daily-edit]');
    if(!button)return;
    const id=button.getAttribute('data-aqua-job-id')||button.closest('[data-aqua-daily-row]')?.getAttribute('data-aqua-job-id');
    if(!id)return;
    const app=appState();
    if(!app)return;

    let job=(Array.isArray(app.jobs)?app.jobs:[]).find(item=>String(item?.id)===String(id));
    if(!job){
      let groups=[];
      try{
        if(Array.isArray(app.dailyGroups))groups=app.dailyGroups;
        else if(typeof app.dailyGroups==='function')groups=app.dailyGroups()||[];
      }catch{}
      job=groups.flatMap(group=>Array.isArray(group?.jobs)?group.jobs:[]).find(item=>String(item?.id)===String(id));
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    if(!job){
      app.toast?.('سرویس برای ویرایش پیدا نشد','error');
      return;
    }
    app.openServiceEdit(job);
  },true);
})();
