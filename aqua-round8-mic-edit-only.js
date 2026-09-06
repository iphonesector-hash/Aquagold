(()=>{
  if(window.__aquaRound8MicEditOnly)return;
  window.__aquaRound8MicEditOnly=true;

  const clean=value=>String(value??'').trim();
  const isIOS=()=>/iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);

  const appState=()=>{
    try{
      const root=document.querySelector('[x-data]');
      const data=root&&window.Alpine?.$data?.(root);
      if(data&&typeof data.openServiceEdit==='function')return data;
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
      state.aquaRound8Run=Number(state.aquaRound8Run||0);
      state.aquaRound8StopRun=Number(state.aquaRound8StopRun||0);

      state.toggleAquaRecording=async function(){
        if(this.aquaRecording){
          const recorder=this.aquaRecorder;
          if(!recorder||recorder.state==='inactive'){
            this.aquaRecording=false;
            this.setAquaVoicePhase?.('idle');
            return;
          }
          this.aquaRound8StopRun=Number(this.aquaRound8Run||0);
          this.setAquaVoicePhase?.('stopping');
          try{recorder.requestData?.()}catch{}
          try{recorder.stop()}catch(error){
            this.aquaRecording=false;
            this.setAquaVoicePhase?.('idle');
            this.toast?.(error?.message||'توقف ضبط انجام نشد','error');
          }
          return;
        }

        const phase=this.aquaVoicePhase||'idle';
        if(phase!=='idle'||this.aquaTranscribing||this.aquaVoiceSending||this.aquaBusy||this.aquaVoiceSubmitActive||this.aquaSendLock||this.aquaSendPromise){
          this.toast?.('کار قبلی آریا هنوز کامل نشده…','info');
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
          const runId=Number(this.aquaRound8Run||0)+1;
          this.aquaRound8Run=runId;
          this.aquaRound8StopRun=0;
          const chunks=[];
          let started=false;
          let finalized=false;

          this.aquaRecorder=recorder;
          this.aquaStream=stream;
          this.aquaChunks=chunks;

          recorder.onstart=()=>{
            started=true;
            if(runId!==this.aquaRound8Run)return;
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

            if(runId!==this.aquaRound8Run)return;
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

              this.aquaInput=spoken;
              this.aquaTranscribing=false;
              this.aquaVoiceSubmitActive=true;
              this.setAquaVoicePhase?.('submitting');
              this.toast?.('صدات گرفته شد؛ دارم برای آریا می‌فرستم…','success');

              let sent=false;
              if(typeof this.submitAquaVoiceTranscript==='function')sent=await this.submitAquaVoiceTranscript(spoken,this.aquaVoiceSeq||runId);
              else if(typeof this.submitAquaText==='function')sent=await this.submitAquaText(spoken,'voice');
              this.aquaInput=sent?'':spoken;
            }catch(error){
              this.toast?.(error?.message||'ویس پردازش نشد','error');
            }finally{
              this.aquaTranscribing=false;
              this.aquaVoiceSubmitActive=false;
              this.aquaRecorder=null;
              this.aquaStream=null;
              this.setAquaVoicePhase?.('idle');
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
            if(runId!==this.aquaRound8Run||started||recorder.state==='inactive')return;
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

  document.addEventListener('click',event=>{
    const button=event.target?.closest?.('button');
    if(!button||!clean(button.textContent).includes('ویرایش'))return;
    const daily=button.closest?.('section[x-show*="page===\'daily\'"]');
    if(!daily)return;

    let row=button.parentElement;
    while(row&&row!==daily){
      try{
        const scope=window.Alpine?.$data?.(row);
        if(scope?.j){
          const app=appState();
          if(app){
            event.preventDefault();
            event.stopImmediatePropagation();
            app.openServiceEdit(scope.j);
          }
          return;
        }
      }catch{}
      row=row.parentElement;
    }
  },true);
})();
