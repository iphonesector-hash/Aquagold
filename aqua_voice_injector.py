"""Canonical Aqua voice controller injected before Alpine starts.

The base Aqua module keeps a browser-neutral fallback.  This controller owns the
production iPhone/PWA lifecycle: microphone capture, exactly-once transcript
submission, send locking, and Persian system speech (preferring Dariush).
"""
from __future__ import annotations

import re

from flask import Response, request

import app_v3


VOICE_UI_JS = r"""
(()=>{
 const previous=window.app;if(typeof previous!=='function')return;
 const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
 const pickMime=()=>{for(const value of ['audio/mp4','audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus']){try{if(window.MediaRecorder?.isTypeSupported?.(value))return value}catch{}}return''};
 const splitSpeech=text=>{const clean=String(text||'').replace(/\s+/g,' ').trim();if(!clean)return[];const result=[];let current='';for(const sentence of clean.split(/(?<=[.!؟?!؛;،,])\s+/)){const next=(current+' '+sentence).trim();if(next.length<=170){current=next;continue}if(current)result.push(current);if(sentence.length<=170)current=sentence;else{for(let index=0;index<sentence.length;index+=160)result.push(sentence.slice(index,index+160));current=''}}if(current)result.push(current);return result};
 const choosePersianVoice=list=>{const voices=Array.isArray(list)?list:[],normalize=value=>String(value||'').toLowerCase();return voices.find(voice=>{const name=normalize(voice?.name),uri=normalize(voice?.voiceURI);return name.includes('dariush')||name.includes('darius')||uri.includes('dariush')||uri.includes('darius')||name.includes('داریوش')||uri.includes('داریوش')})||voices.find(voice=>/^fa(?:-|_)/i.test(String(voice?.lang||'')))||null};
 const style=document.createElement('style');style.id='aqua-voice-controller-style';style.textContent='.aqua-mic:disabled,.aqua-send:disabled{opacity:.55;cursor:wait;filter:saturate(.6)}.aqua-mic[data-phase="transcribing"],.aqua-mic[data-phase="submitting"]{animation:aquaVoiceWait 1s ease-in-out infinite}@keyframes aquaVoiceWait{50%{transform:scale(.94);opacity:.65}}';document.head.appendChild(style);

 window.app=function(){
  const s=previous();
  Object.assign(s,{
   aquaVoicePhase:'idle',aquaVoiceSeq:0,aquaVoiceCommittedRun:0,aquaSendLock:false,aquaSendPromise:null,
   aquaSpeechSeq:0,aquaSpeechUtterance:null,aquaSpeechPrimeUtterance:null,aquaSpeechPrimed:false,
   aquaDeviceVoices:[],aquaDeviceVoiceName:'',aquaVoiceListenerBound:false
  });
  if(s.aquaSettings)s.aquaSettings.auto_speak=true;

  s.refreshAquaDeviceVoices=function(){
   try{this.aquaDeviceVoices=window.speechSynthesis?.getVoices?.()||[]}catch{this.aquaDeviceVoices=[]}
   const voice=choosePersianVoice(this.aquaDeviceVoices);this.aquaDeviceVoiceName=voice?`${voice.name} • ${voice.lang||'fa-IR'}`:'صدای فارسی سیستم';return voice
  };

  s.primeAquaDeviceSpeech=function(){
   const synth=window.speechSynthesis,Utterance=window.SpeechSynthesisUtterance;if(!synth||!Utterance)return false;
   try{
    const voice=this.refreshAquaDeviceVoices();synth.resume?.();if(this.aquaSpeechPrimed)return true;
    const utterance=new Utterance('آ');utterance.lang='fa-IR';if(voice)utterance.voice=voice;utterance.rate=10;utterance.pitch=1;utterance.volume=.01;this.aquaSpeechPrimeUtterance=utterance;
    const finish=()=>{this.aquaSpeechPrimed=true;this.aquaSpeechPrimeUtterance=null};utterance.onstart=finish;utterance.onend=finish;utterance.onerror=finish;synth.speak(utterance);this.aquaSpeechPrimed=true;return true
   }catch(error){console.warn('Aqua speech prime failed',error);return false}
  };

  s.setAquaVoicePhase=function(phase){
   this.aquaVoicePhase=phase;this.aquaRecording=phase==='recording';this.aquaTranscribing=phase==='transcribing';this.aquaVoiceSending=phase==='submitting';this.aquaVoiceSubmitActive=phase==='submitting';
   const button=document.querySelector('.aqua-mic');if(button){button.dataset.phase=phase;button.disabled=['starting','stopping','transcribing','submitting'].includes(phase)}
  };

  s.stopAquaSpeech=function(){
   this.aquaSpeechSeq=Number(this.aquaSpeechSeq||0)+1;
   try{window.speechSynthesis?.cancel?.()}catch{}
   try{if(this.aquaPlayer){this.aquaPlayer.pause();this.aquaPlayer.removeAttribute('src');this.aquaPlayer.load()}}catch{}
   try{if(this.aquaAudio){this.aquaAudio.pause();this.aquaAudio=null}}catch{}
   try{if(this.aquaAudioSource){this.aquaAudioSource.stop();this.aquaAudioSource.disconnect();this.aquaAudioSource=null}}catch{}
   this.aquaSpeechUtterance=null;this.aquaSpeechPrimeUtterance=null;this.aquaSpeaking=false
  };

  s.speakAqua=async function(value){
   const text=String(value||'').trim(),synth=window.speechSynthesis,Utterance=window.SpeechSynthesisUtterance;if(!text||document.hidden)return false;
   if(!synth||!Utterance){this.toast?.('صدای فارسی این مرورگر در دسترس نیست','error');return false}
   this.stopAquaSpeech();const sequence=++this.aquaSpeechSeq,voice=this.refreshAquaDeviceVoices(),parts=splitSpeech(text);this.aquaSpeaking=true;
   const playPart=part=>new Promise((resolve,reject)=>{
    if(sequence!==this.aquaSpeechSeq||document.hidden){resolve(false);return}
    const utterance=new Utterance(part);utterance.lang='fa-IR';if(voice)utterance.voice=voice;utterance.rate=.93;utterance.pitch=1;utterance.volume=1;this.aquaSpeechUtterance=utterance;
    let started=false,finished=false,timer=null;const finish=(ok,error)=>{if(finished)return;finished=true;if(timer)clearTimeout(timer);this.aquaSpeechUtterance=null;ok?resolve(true):reject(error||Error('speech failed'))};
    utterance.onstart=()=>{started=true;this.aquaSpeaking=true};utterance.onend=()=>finish(true);utterance.onerror=event=>finish(false,Error(event?.error||'speech failed'));
    try{synth.resume?.();synth.speak(utterance);timer=setTimeout(()=>{if(!started)finish(false,Error('speech did not start'))},6500)}catch(error){finish(false,error)}
   });
   try{for(const part of parts){if(sequence!==this.aquaSpeechSeq||document.hidden)return false;await playPart(part);await sleep(25)}return true}
   catch(error){if(sequence===this.aquaSpeechSeq&&!document.hidden){console.warn('Aqua Persian system speech failed',error);this.toast?.('صدای داریوش شروع نشد؛ یک‌بار دکمه بلندگوی همان پیام را بزن','info')}return false}
   finally{if(sequence===this.aquaSpeechSeq){this.aquaSpeaking=false;this.aquaSpeechUtterance=null}}
  };

  s.submitAquaText=async function(value,source='text',voiceRunId=0){
   const text=String(value??'').trim();if(!text){this.toast?.('اول یک پیام بنویس','info');return false}
   if(this.aquaSendLock||this.aquaBusy||this.aquaSendPromise){this.toast?.('پیام قبلی هنوز در حال ارسال است','info');return false}
   this.aquaSendLock=true;if(source==='voice'&&voiceRunId)this.aquaVoiceCommittedRun=voiceRunId;
   const operation=(async()=>{
    this.aquaMessages.push({role:'user',content:text});this.aquaInput='';this.aquaBusy=true;this.aquaScroll();
    try{
     const history=this.aquaHistory();let response;
     try{response=await this.api('/aqua-ai/chat',{method:'POST',body:JSON.stringify({text,history})})}
     catch(error){const message=String(error?.message||error);if(!message.includes('429'))throw error;const seconds=Number((message.match(/try again in\s*([\d.]+)s/i)||[])[1]||2);this.toast?.('محدودیت لحظه‌ای Groq؛ خودکار دوباره امتحان می‌کنم…','info');await sleep(Math.min(8000,Math.max(1200,seconds*1000+350)));response=await this.api('/aqua-ai/chat',{method:'POST',body:JSON.stringify({text,history:[]})})}
     const message={role:'assistant',content:response.answer||'انجام شد',chart:response.chart,pending_action:response.pending_action,action:response.action,results:response.results};this.aquaMessages.push(message);this.aquaScroll();this.aquaBusy=false;
     if(this.aquaSettings?.auto_speak!==false&&!document.hidden&&this.aquaVoicePhase!=='recording')void this.speakAqua(message.content);return true
    }catch(error){let message=String(error?.message||'خطای ارتباط با آریا');if(message.includes('429'))message='محدودیت موقت Groq پر شده؛ چند ثانیه بعد دوباره امتحان کن.';this.aquaMessages.push({role:'assistant',content:message,error:true});if(!this.aquaInput)this.aquaInput=text;return false}
    finally{this.aquaBusy=false;this.aquaScroll()}
   })();
   this.aquaSendPromise=operation;
   try{return await operation}finally{if(this.aquaSendPromise===operation)this.aquaSendPromise=null;this.aquaSendLock=false}
  };

  s.sendAqua=function(value=null){
   const text=String(value??this.aquaInput).trim();if(!text){this.toast?.('اول یک پیام بنویس','info');return Promise.resolve(false)}
   if(this.aquaSendLock||this.aquaBusy||this.aquaSendPromise){this.toast?.('پیام قبلی هنوز در حال ارسال است','info');return Promise.resolve(false)}
   this.stopAquaSpeech();this.primeAquaDeviceSpeech();return this.submitAquaText(text,'text')
  };

  s.submitAquaVoiceTranscript=async function(spoken,runId){
   const text=String(spoken||'').trim();if(!text||runId!==this.aquaVoiceSeq||this.aquaVoiceCommittedRun===runId)return false;
   for(let attempt=0;attempt<12&&(this.aquaBusy||this.aquaSendLock||this.aquaSendPromise);attempt++)await sleep(150);
   if(runId!==this.aquaVoiceSeq||this.aquaBusy||this.aquaSendLock||this.aquaSendPromise)return false;
   return this.submitAquaText(text,'voice',runId)
  };

  s.toggleAquaRecording=async function(){
   const phase=this.aquaVoicePhase||'idle';
   if(phase==='recording'){this.setAquaVoicePhase('stopping');try{const recorder=this.aquaRecorder;if(recorder&&recorder.state!=='inactive'){try{recorder.requestData?.()}catch{}recorder.stop()}else this.setAquaVoicePhase('idle')}catch(error){this.setAquaVoicePhase('idle');this.toast?.(error?.message||'توقف ضبط انجام نشد','error')}return}
   if(phase!=='idle'){this.toast?.(phase==='transcribing'?'دارم صدات رو به متن تبدیل می‌کنم…':phase==='submitting'?'دارم همون پیام رو می‌فرستم…':'ضبط قبلی هنوز کامل نشده…','info');return}
   if(this.aquaBusy||this.aquaSendLock||this.aquaSendPromise){this.toast?.('آریا هنوز در حال پاسخ‌دادنه؛ یک لحظه صبر کن','info');return}
   if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){this.toast?.('ضبط صدا روی این مرورگر پشتیبانی نمی‌شود','error');return}
   this.stopAquaSpeech();this.primeAquaDeviceSpeech();this.setAquaVoicePhase('starting');let stream=null;
   try{
    stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    const mime=pickMime(),recorder=mime?new MediaRecorder(stream,{mimeType:mime}):new MediaRecorder(stream),runId=++this.aquaVoiceSeq,parts=[];let finalized=false;
    this.aquaRecorder=recorder;this.aquaStream=stream;recorder.ondataavailable=event=>{if(event.data?.size)parts.push(event.data)};recorder.onerror=event=>this.toast?.(event?.error?.message||'خطای ضبط صدا','error');
    recorder.onstop=async()=>{
     if(finalized)return;finalized=true;try{stream?.getTracks?.().forEach(track=>track.stop())}catch{}if(runId!==this.aquaVoiceSeq)return;this.setAquaVoicePhase('transcribing');
     try{
      if(!parts.length)throw Error('صدایی ثبت نشد؛ دوباره امتحان کن');const type=recorder.mimeType||mime||parts[0]?.type||'audio/webm',blob=new Blob(parts,{type});if(blob.size<256)throw Error('ویس خیلی کوتاه بود؛ دوباره امتحان کن');
      const extension=type.includes('mp4')?'m4a':type.includes('ogg')?'ogg':type.includes('wav')?'wav':'webm',form=new FormData();form.append('audio',blob,'aqua.'+extension);
      const headers={},csrf=this.cookie?.('aquagold_csrf');if(csrf)headers['X-CSRF-Token']=csrf;const response=await fetch('/api/aqua-ai/transcribe',{method:'POST',body:form,headers,credentials:'same-origin',cache:'no-store'});let data={};try{data=await response.json()}catch{}if(!response.ok)throw Error(data.error||'تبدیل ویس به متن انجام نشد');
      const spoken=String(data.text||'').trim();if(!spoken)throw Error('حرفی از ویس تشخیص داده نشد');if(runId!==this.aquaVoiceSeq)return;this.aquaInput=spoken;this.setAquaVoicePhase('submitting');this.toast?.('گرفتمش؛ دارم برای آریا می‌فرستم…','success');
      const sent=await this.submitAquaVoiceTranscript(spoken,runId);this.aquaInput=sent?'':spoken;if(!sent)this.toast?.('متن ویس در کادر ماند؛ دکمه ارسال را بزن','info')
     }catch(error){this.toast?.(error?.message||'ویس پردازش نشد','error')}
     finally{if(runId===this.aquaVoiceSeq){this.aquaRecorder=null;this.aquaStream=null;this.setAquaVoicePhase('idle')}}
    };
    recorder.start(250);this.setAquaVoicePhase('recording');this.toast?.('آریا گوش می‌ده؛ وقتی تموم شد فقط یک‌بار میکروفن رو بزن','info')
   }catch(error){try{stream?.getTracks?.().forEach(track=>track.stop())}catch{}this.aquaRecorder=null;this.aquaStream=null;this.setAquaVoicePhase('idle');this.toast?.(error?.message||'دسترسی میکروفن یا شروع ضبط انجام نشد','error')}
  };

  const mount=s.mountAquaAI?.bind(s);if(mount)s.mountAquaAI=function(){const result=mount();setTimeout(()=>this.setAquaVoicePhase(this.aquaVoicePhase||'idle'),100);return result};
  if(!s.aquaVoiceListenerBound&&window.speechSynthesis){s.aquaVoiceListenerBound=true;const refresh=()=>s.refreshAquaDeviceVoices();try{window.speechSynthesis.addEventListener('voiceschanged',refresh)}catch{}setTimeout(refresh,0)}
  if(!s.aquaVoiceLifecycleBound){s.aquaVoiceLifecycleBound=true;const stop=()=>{try{s.stopAquaSpeech?.()}catch{}};document.addEventListener('visibilitychange',()=>{if(document.hidden)stop()});window.addEventListener('pagehide',stop)}
  return s
 };
})();
"""


@app_v3.app.get("/aqua-voice-ui.js")
def aqua_voice_ui_js():
    return Response(
        VOICE_UI_JS,
        mimetype="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app_v3.app.after_request
def inject_aqua_voice_controller(response):
    try:
        if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
            response.direct_passthrough = False
            body = response.get_data(as_text=True)
            body = re.sub(
                r'<script src="/(?:aqua-voice-runtime-hotfix|aqua-ios-tts-patch|aqua-voice-ui(?:-clean)?)\.js\?v=[^"]+"></script>',
                "",
                body,
            )
            position = body.lower().find("</head>")
            if position >= 0:
                tag = '<script src="/aqua-voice-ui.js?v=20260831-stable1"></script>'
                body = body[:position] + tag + body[position:]
                response.set_data(body)
                response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_voice_controller_inject_failed detail=%s", str(exc)[:200])
    return response
