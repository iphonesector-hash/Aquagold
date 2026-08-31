"""Single deterministic Aqua voice UI controller for iPhone/PWA."""
from __future__ import annotations

import re

from flask import Response, request

import app_v3


VOICE_UI_JS = r"""
(()=>{
 const previous=window.app;if(typeof previous!=='function')return;
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const pickMime=()=>{for(const m of ['audio/mp4','audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus']){try{if(window.MediaRecorder?.isTypeSupported?.(m))return m}catch{}}return''};
 const voices=async()=>{if(!speechSynthesis)return[];let v=speechSynthesis.getVoices?.()||[];if(v.length)return v;await new Promise(r=>{let d=false,f=()=>{if(d)return;d=true;r()};try{speechSynthesis.addEventListener('voiceschanged',f,{once:true})}catch{}setTimeout(f,1000)});return speechSynthesis.getVoices?.()||[]};
 const faVoice=v=>{const n=x=>String(x||'').toLowerCase();return v.find(x=>n(x.name).includes('dariush')||n(x.voiceURI).includes('dariush')||n(x.name).includes('داریوش')||n(x.voiceURI).includes('داریوش'))||v.find(x=>/^fa(?:-|_)/i.test(String(x.lang||'')))||null};
 const chunks=t=>{t=String(t||'').replace(/\s+/g,' ').trim();if(!t)return[];let out=[],cur='';for(const p of t.split(/(?<=[.!؟?!؛;،,])\s+/)){if((cur+' '+p).trim().length<=180){cur=(cur+' '+p).trim();continue}if(cur)out.push(cur);if(p.length<=180)cur=p;else{for(let i=0;i<p.length;i+=170)out.push(p.slice(i,i+170));cur=''}}if(cur)out.push(cur);return out};
 const style=document.createElement('style');style.textContent='.aqua-stop{display:none!important}.aqua-mic:disabled{opacity:.55;cursor:wait;filter:saturate(.6)}.aqua-mic[data-phase="transcribing"],.aqua-mic[data-phase="submitting"]{animation:aquaVoiceWait 1s ease-in-out infinite}@keyframes aquaVoiceWait{50%{transform:scale(.94);opacity:.65}}';document.head.appendChild(style);

 window.app=function(){
  const s=previous();
  s.aquaVoicePhase='idle';s.aquaVoiceSeq=0;s.aquaVoiceCommittedRun=0;s.aquaSendLock=false;s.aquaSpeechSeq=0;s.aquaSpeechUtterance=null;s.aquaDeviceVoiceName='';

  s.setAquaVoicePhase=function(p){
   this.aquaVoicePhase=p;this.aquaRecording=p==='recording';this.aquaTranscribing=p==='transcribing';this.aquaVoiceSending=p==='submitting';this.aquaVoiceSubmitActive=p==='submitting';
   const b=document.querySelector('.aqua-mic');if(b){b.dataset.phase=p;b.disabled=['starting','stopping','transcribing','submitting'].includes(p)}
  };

  s.stopAquaSpeech=function(){
   this.aquaSpeechSeq=Number(this.aquaSpeechSeq||0)+1;
   try{speechSynthesis?.cancel?.()}catch{}
   try{if(this.aquaPlayer){this.aquaPlayer.pause();this.aquaPlayer.removeAttribute('src');this.aquaPlayer.load()}}catch{}
   try{if(this.aquaAudioSource){this.aquaAudioSource.stop();this.aquaAudioSource.disconnect();this.aquaAudioSource=null}}catch{}
   this.aquaSpeechUtterance=null;this.aquaSpeaking=false
  };

  s.speakAqua=async function(text){
   text=String(text||'').trim();if(!text||document.hidden)return false;if(this.aquaSpeaking){this.stopAquaSpeech();return false}
   this.stopAquaSpeech();const seq=++this.aquaSpeechSeq;
   try{
    if(!window.speechSynthesis||!window.SpeechSynthesisUtterance)throw Error('speech unavailable');
    const list=await voices(),voice=faVoice(list);this.aquaDeviceVoiceName=voice?`${voice.name} • ${voice.lang||'fa-IR'}`:'Persian system voice';
    if(seq!==this.aquaSpeechSeq||document.hidden)return false;
    for(const part of chunks(text)){
     if(seq!==this.aquaSpeechSeq||document.hidden)return false;
     const u=new SpeechSynthesisUtterance(part);u.lang='fa-IR';if(voice)u.voice=voice;u.rate=.93;u.pitch=1;u.volume=1;this.aquaSpeechUtterance=u;
     await new Promise((resolve,reject)=>{let started=false,done=false;const end=(ok,e)=>{if(done)return;done=true;this.aquaSpeechUtterance=null;ok?resolve():reject(e||Error('speech failed'))};u.onstart=()=>{started=true;this.aquaSpeaking=true};u.onend=()=>end(true);u.onerror=e=>end(false,Error(e?.error||'speech failed'));try{speechSynthesis.resume?.()}catch{}speechSynthesis.speak(u);setTimeout(()=>{if(!started)end(false,Error('speech did not start'))},5000)});
     await sleep(30)
    }
    return true
   }catch(e){console.warn('Aqua iOS speech failed',e);if(seq===this.aquaSpeechSeq&&!document.hidden)this.toast?.('صدای فارسی آیفون شروع نشد','info');return false}
   finally{if(seq===this.aquaSpeechSeq){this.aquaSpeaking=false;this.aquaSpeechUtterance=null}}
  };

  s.submitAquaText=async function(value,source='text'){
   const text=String(value??'').trim();if(!text||this.aquaSendLock||this.aquaBusy)return false;
   this.aquaSendLock=true;this.stopAquaSpeech?.();try{await this.primeAquaAudio?.()}catch{}
   this.aquaMessages.push({role:'user',content:text});this.aquaInput='';this.aquaBusy=true;this.aquaScroll();
   try{
    const history=this.aquaHistory();let r;
    try{r=await this.api('/aqua-ai/chat',{method:'POST',body:JSON.stringify({text,history})})}
    catch(e){const msg=String(e?.message||e);if(!msg.includes('429'))throw e;const sec=Number((msg.match(/try again in\s*([\d.]+)s/i)||[])[1]||2);this.toast?.('محدودیت لحظه‌ای Groq؛ خودکار دوباره امتحان می‌کنم…','info');await sleep(Math.min(8000,Math.max(1200,sec*1000+350)));r=await this.api('/aqua-ai/chat',{method:'POST',body:JSON.stringify({text,history:[]})})}
    const m={role:'assistant',content:r.answer||'انجام شد',chart:r.chart,pending_action:r.pending_action,action:r.action,results:r.results};this.aquaMessages.push(m);this.aquaScroll();this.aquaBusy=false;
    if(!document.hidden)setTimeout(()=>{if(!document.hidden&&this.aquaVoicePhase!=='recording')this.speakAqua(m.content)},80);
    return true
   }catch(e){let msg=String(e?.message||'خطای ارتباط با آریا');if(msg.includes('429'))msg='محدودیت موقت Groq پر شده؛ چند ثانیه بعد دوباره امتحان کن.';this.aquaMessages.push({role:'assistant',content:msg,error:true});if(source==='voice')this.aquaInput=text;return false}
   finally{this.aquaBusy=false;this.aquaSendLock=false;this.aquaScroll()}
  };

  s.sendAqua=async function(value=null){if(this.aquaSendLock||this.aquaBusy)return false;return this.submitAquaText(String(value??this.aquaInput).trim(),'text')};

  s.toggleAquaRecording=async function(){
   const phase=this.aquaVoicePhase||'idle';
   if(phase==='recording'){this.setAquaVoicePhase('stopping');try{const r=this.aquaRecorder;if(r&&r.state!=='inactive')r.stop();else this.setAquaVoicePhase('idle')}catch(e){this.setAquaVoicePhase('idle');this.toast?.(e?.message||'توقف ضبط انجام نشد','error')}return}
   if(phase!=='idle'){this.toast?.(phase==='transcribing'?'دارم صدات رو به متن تبدیل می‌کنم…':phase==='submitting'?'دارم همون پیام رو می‌فرستم…':'ضبط قبلی هنوز کامل نشده…','info');return}
   if(this.aquaBusy||this.aquaSendLock){this.toast?.('آریا هنوز در حال پاسخ‌دادنه؛ یک لحظه صبر کن','info');return}
   if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){this.toast?.('ضبط صدا روی این مرورگر پشتیبانی نمی‌شود','error');return}
   this.stopAquaSpeech?.();this.setAquaVoicePhase('starting');let stream=null;
   try{
    try{await this.primeAquaAudio?.()}catch{}
    stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    const mime=pickMime(),rec=mime?new MediaRecorder(stream,{mimeType:mime}):new MediaRecorder(stream),runId=++this.aquaVoiceSeq,parts=[];let final=false;
    this.aquaRecorder=rec;this.aquaStream=stream;
    rec.ondataavailable=e=>{if(e.data?.size)parts.push(e.data)};
    rec.onerror=e=>this.toast?.(e?.error?.message||'خطای ضبط صدا','error');
    rec.onstop=async()=>{
     if(final)return;final=true;try{stream?.getTracks?.().forEach(t=>t.stop())}catch{}if(runId!==this.aquaVoiceSeq)return;this.setAquaVoicePhase('transcribing');
     try{
      if(!parts.length)throw Error('صدایی ثبت نشد؛ دوباره امتحان کن');
      const type=rec.mimeType||mime||parts[0]?.type||'audio/webm',blob=new Blob(parts,{type});if(blob.size<256)throw Error('ویس خیلی کوتاه بود؛ دوباره امتحان کن');
      const ext=type.includes('mp4')?'m4a':type.includes('ogg')?'ogg':type.includes('wav')?'wav':'webm',form=new FormData();form.append('audio',blob,'aqua.'+ext);
      const headers={},csrf=this.cookie?.('aquagold_csrf');if(csrf)headers['X-CSRF-Token']=csrf;
      const response=await fetch('/api/aqua-ai/transcribe',{method:'POST',body:form,headers,credentials:'same-origin',cache:'no-store'});let data={};try{data=await response.json()}catch{}if(!response.ok)throw Error(data.error||'تبدیل ویس به متن انجام نشد');
      const spoken=String(data.text||'').trim();if(!spoken)throw Error('حرفی از ویس تشخیص داده نشد');if(runId!==this.aquaVoiceSeq)return;
      this.aquaInput=spoken;this.setAquaVoicePhase('submitting');if(this.aquaVoiceCommittedRun===runId)return;this.aquaVoiceCommittedRun=runId;
      const sent=await this.submitAquaText(spoken,'voice');this.aquaInput=sent?'':spoken;if(!sent)this.toast?.('متن ویس در کادر موند و خودکار دوباره ارسال نمی‌شه','info')
     }catch(e){this.toast?.(e?.message||'ویس پردازش نشد','error')}
     finally{if(runId===this.aquaVoiceSeq){this.aquaRecorder=null;this.aquaStream=null;this.setAquaVoicePhase('idle')}}
    };
    rec.start(250);this.setAquaVoicePhase('recording');this.toast?.('آریا گوش می‌ده؛ وقتی تموم شد فقط یک‌بار میکروفن رو بزن','info')
   }catch(e){try{stream?.getTracks?.().forEach(t=>t.stop())}catch{}this.aquaRecorder=null;this.aquaStream=null;this.setAquaVoicePhase('idle');this.toast?.(e?.message||'دسترسی میکروفن یا شروع ضبط انجام نشد','error')}
  };

  const mount=s.mountAquaAI?.bind(s);if(mount)s.mountAquaAI=function(){const r=mount();setTimeout(()=>this.setAquaVoicePhase(this.aquaVoicePhase||'idle'),100);return r};
  if(!s.aquaVoiceLifecycleBound){s.aquaVoiceLifecycleBound=true;const stop=()=>{try{s.stopAquaSpeech?.()}catch{}};document.addEventListener('visibilitychange',()=>{if(document.hidden)stop()});window.addEventListener('pagehide',stop)}
  return s
 };
})();
"""


@app_v3.app.get("/aqua-voice-ui-clean.js")
def aqua_voice_ui_clean_js():
    return Response(VOICE_UI_JS, mimetype="application/javascript", headers={"Cache-Control": "no-store, max-age=0"})


@app_v3.app.after_request
def inject_aqua_voice_clean(response):
    try:
        if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
            response.direct_passthrough = False
            body = response.get_data(as_text=True)
            body = re.sub(r'<script src="/(?:aqua-voice-runtime-hotfix|aqua-ios-tts-patch|aqua-voice-ui-clean)\.js\?v=[^"]+"></script>', "", body)
            pos = body.lower().find("</head>")
            if pos >= 0:
                body = body[:pos] + '<script src="/aqua-voice-ui-clean.js?v=20260831-clean2"></script>' + body[pos:]
                response.set_data(body)
                response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_voice_clean_inject_failed detail=%s", str(exc)[:200])
    return response
