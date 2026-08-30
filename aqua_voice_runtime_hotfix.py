"""Narrow runtime hotfix for Aqua voice on iPhone/PWA.

Fixes three isolated voice paths without changing the rest of AquaGold:
- stable iPhone MediaRecorder capture and deterministic voice auto-send;
- Groq Whisper STT with the same browser-like HTTP headers used by working Groq chat calls;
- iOS Persian speech that prefers the installed Dariush voice and stops when the app is hidden.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from flask import Response, jsonify, request

import app_v3
import aqua_ai


MAX_AUDIO = 8 * 1024 * 1024


def _provider_post(url, fields, filename, audio, mimetype, headers, timeout=60):
    boundary, body = aqua_ai._multipart(fields, filename, audio, mimetype)
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 AquaGold/7.2",
            "Content-Length": str(len(body)),
            **headers,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode())


@app_v3.roles_required("technician")
@app_v3.limiter.limit("10 per minute; 100 per day")
def aqua_transcribe_runtime():
    upload = request.files.get("audio")
    if not upload:
        return jsonify({"error": "فایل صوتی دریافت نشد"}), 400
    audio = upload.read(MAX_AUDIO + 1)
    if not audio:
        return jsonify({"error": "فایل صوتی خالی است"}), 400
    if len(audio) > MAX_AUDIO:
        return jsonify({"error": "صدا باید حداکثر ۸ مگابایت باشد"}), 413

    settings = aqua_ai._load_settings()
    filename = upload.filename or "aqua.webm"
    mimetype = upload.mimetype or "audio/webm"
    groq_key = settings.get("groq_api_key")
    eleven_key = settings.get("elevenlabs_api_key")
    provider_errors = []

    if groq_key:
        try:
            payload = _provider_post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                {
                    "model": "whisper-large-v3-turbo",
                    "language": "fa",
                    "response_format": "json",
                    "temperature": "0",
                },
                filename,
                audio,
                mimetype,
                {"Authorization": f"Bearer {groq_key}"},
            )
            text = str(payload.get("text") or "").strip()
            if text:
                app_v3.logger.info("aqua_stt_ok provider=groq bytes=%s mimetype=%s", len(audio), mimetype)
                return jsonify({"text": text, "provider": "groq"})
            provider_errors.append("groq_empty")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            provider_errors.append(f"groq_{exc.code}")
            app_v3.logger.warning("aqua_stt_groq_failed status=%s detail=%s", exc.code, detail)
        except Exception as exc:
            provider_errors.append("groq_network")
            app_v3.logger.warning("aqua_stt_groq_failed detail=%s", str(exc)[:500])

    if eleven_key:
        try:
            payload = _provider_post(
                "https://api.elevenlabs.io/v1/speech-to-text",
                {"model_id": settings.get("stt_model") or "scribe_v2", "language_code": "fas"},
                filename,
                audio,
                mimetype,
                {"xi-api-key": eleven_key},
            )
            text = str(payload.get("text") or "").strip()
            if text:
                app_v3.logger.info("aqua_stt_ok provider=elevenlabs bytes=%s mimetype=%s", len(audio), mimetype)
                return jsonify({"text": text, "provider": "elevenlabs"})
            provider_errors.append("eleven_empty")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            provider_errors.append(f"eleven_{exc.code}")
            app_v3.logger.warning("aqua_stt_eleven_failed status=%s detail=%s", exc.code, detail)
        except Exception as exc:
            provider_errors.append("eleven_network")
            app_v3.logger.warning("aqua_stt_eleven_failed detail=%s", str(exc)[:500])

    if not groq_key and not eleven_key:
        return jsonify({"error": "برای تبدیل ویس، کلید Groq یا ElevenLabs تنظیم نشده است"}), 409
    return jsonify({"error": "تبدیل ویس به متن انجام نشد", "providers": provider_errors}), 502


app_v3.app.view_functions["aqua_transcribe"] = aqua_transcribe_runtime


VOICE_HOTFIX_JS = r"""
(()=>{
 const previous=window.app;
 if(typeof previous!=='function')return;
 const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
 const addStyle=()=>{
  if(document.getElementById('aqua-voice-runtime-style'))return;
  const st=document.createElement('style');st.id='aqua-voice-runtime-style';
  st.textContent=`.aqua-composer{position:relative!important;grid-template-columns:54px minmax(0,1fr) auto!important;align-items:center!important}.aqua-composer>button:nth-child(2){position:absolute!important;right:74px!important;top:18px!important;width:42px!important;height:42px!important;z-index:3!important}.aqua-composer textarea{min-width:0!important}@media(max-width:850px){.aqua-composer{grid-template-columns:48px minmax(0,1fr) auto!important}.aqua-composer>button:nth-child(2){right:68px!important;top:15px!important;width:40px!important;height:40px!important}}`;
  document.head.appendChild(st);
 };
 addStyle();
 const getVoices=async()=>{
  if(!window.speechSynthesis)return[];
  let voices=window.speechSynthesis.getVoices?.()||[];
  if(voices.length)return voices;
  await new Promise(resolve=>{let done=false;const finish=()=>{if(done)return;done=true;resolve()};try{window.speechSynthesis.addEventListener('voiceschanged',finish,{once:true})}catch{}setTimeout(finish,900)});
  return window.speechSynthesis.getVoices?.()||[];
 };
 const pickPersianVoice=voices=>{
  const list=Array.isArray(voices)?voices:[];
  const dariush=list.find(v=>{const name=String(v?.name||'').toLowerCase(),uri=String(v?.voiceURI||'').toLowerCase();return name.includes('dariush')||uri.includes('dariush')||name.includes('داریوش')||uri.includes('داریوش')});
  if(dariush)return dariush;
  return list.find(v=>/^fa(?:-|_)/i.test(String(v?.lang||'')))||null;
 };
 window.app=function(){
  const s=previous();
  s.aquaVoiceRunId=Number(s.aquaVoiceRunId||0);
  s.aquaSpeechUtterance=null;

  s.stopAquaSpeech=function(){
   try{if(this.aquaPlayer){this.aquaPlayer.pause();this.aquaPlayer.removeAttribute('src');this.aquaPlayer.load()}}catch{}
   try{if(this.aquaAudio){this.aquaAudio.pause();this.aquaAudio=null}}catch{}
   try{if(this.aquaAudioSource){this.aquaAudioSource.stop();this.aquaAudioSource.disconnect();this.aquaAudioSource=null}}catch{}
   try{window.speechSynthesis?.cancel?.()}catch{}
   this.aquaSpeechUtterance=null;
   this.aquaSpeaking=false;
  };

  if(!s.aquaVoiceLifecycleBound){
   s.aquaVoiceLifecycleBound=true;
   const stopForBackground=()=>{try{s.stopAquaSpeech?.()}catch{}};
   document.addEventListener('visibilitychange',()=>{if(document.hidden)stopForBackground()});
   window.addEventListener('pagehide',stopForBackground);
   window.addEventListener('beforeunload',stopForBackground);
  }

  s.speakAqua=async function(text){
   text=String(text||'').trim();
   if(!text||this.aquaSpeaking||document.hidden)return false;
   this.stopAquaSpeech?.();
   let systemError=null;

   try{
    if(!window.speechSynthesis||!window.SpeechSynthesisUtterance)throw Error('صدای داخلی آیفون در دسترس نیست');
    const voices=await getVoices();
    if(document.hidden)return false;
    const voice=pickPersianVoice(voices);
    if(!voice)throw Error('صدای فارسی داخلی آیفون پیدا نشد');
    const utter=new SpeechSynthesisUtterance(text);
    utter.voice=voice;
    utter.lang=String(voice.lang||'fa-IR');
    utter.rate=.94;utter.pitch=1;utter.volume=1;
    this.aquaSpeechUtterance=utter;
    window.speechSynthesis.cancel();
    try{window.speechSynthesis.resume?.()}catch{}
    await new Promise((resolve,reject)=>{
     let started=false,finished=false;
     const done=(ok,err)=>{if(finished)return;finished=true;this.aquaSpeaking=false;this.aquaSpeechUtterance=null;ok?resolve():reject(err||Error('پخش صدای داخلی ناموفق بود'))};
     utter.onstart=()=>{started=true;this.aquaSpeaking=true};
     utter.onend=()=>done(true);
     utter.onerror=e=>done(false,Error(e?.error||'speech synthesis failed'));
     window.speechSynthesis.speak(utter);
     setTimeout(()=>{if(!started)done(false,Error('صدای داخلی آیفون شروع نشد'))},3500);
    });
    return true;
   }catch(e){
    systemError=e;
    this.aquaSpeaking=false;
    this.aquaSpeechUtterance=null;
    console.warn('Aqua Persian iOS voice unavailable; using server fallback',e);
   }

   if(document.hidden)return false;
   let url=null;
   try{
    const headers={'Content-Type':'application/json'},csrf=this.cookie?.('aquagold_csrf');if(csrf)headers['X-CSRF-Token']=csrf;
    const response=await fetch('/api/aqua-ai/speak',{method:'POST',headers,credentials:'same-origin',cache:'no-store',body:JSON.stringify({text})});
    if(!response.ok){let data={};try{data=await response.json()}catch{}throw Error(data.error||'صدای جایگزین آریا آماده نشد')}
    const blob=await response.blob();if(!blob.size)throw Error('فایل صدای خالی دریافت شد');
    if(document.hidden)return false;
    url=URL.createObjectURL(blob);
    let a=this.aquaPlayer;
    if(!a){a=new Audio();a.playsInline=true;a.preload='auto';this.aquaPlayer=a}
    a.pause();a.src=url;a.muted=false;a.volume=1;a.currentTime=0;a.load();
    await new Promise((resolve,reject)=>{
     let started=false,finished=false;
     const done=(ok,err)=>{if(finished)return;finished=true;this.aquaSpeaking=false;ok?resolve():reject(err||Error('پخش صدای جایگزین ناموفق بود'))};
     a.onplaying=()=>{started=true;this.aquaSpeaking=true};
     a.onended=()=>done(true);
     a.onerror=()=>done(false,Error('پخش صدای آریا روی آیفون ناموفق بود'));
     const p=a.play();if(p?.catch)p.catch(e=>done(false,e));
     setTimeout(()=>{if(!started&&a.paused)done(false,Error('پخش صدا شروع نشد'))},2500);
    });
    return true;
   }catch(serverError){
    console.warn('Aqua server TTS fallback failed',serverError);
    this.aquaSpeaking=false;
    if(!document.hidden)this.toast?.(systemError?.message||serverError?.message||'پخش صدای آریا ناموفق بود','error');
    return false;
   }finally{if(url)setTimeout(()=>URL.revokeObjectURL(url),1500)}
  };

  s.submitAquaVoiceTranscript=async function(spoken,runId){
   const text=String(spoken||'').trim();if(!text)return false;
   for(let i=0;i<12&&this.aquaBusy;i++)await sleep(150);
   if(runId!==this.aquaVoiceRunId||this.aquaBusy)return false;
   return await this.submitAquaText(text,'voice');
  };

  s.toggleAquaRecording=async function(){
   if(this.aquaRecording){
    try{if(this.aquaRecorder?.state&&this.aquaRecorder.state!=='inactive')this.aquaRecorder.stop()}catch(e){this.aquaRecording=false;this.toast?.(e?.message||'توقف ضبط انجام نشد','error')}
    return;
   }
   if(this.aquaTranscribing||this.aquaBusy||this.aquaVoiceSending||this.aquaVoiceSubmitActive)return;
   this.stopAquaSpeech?.();
   if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){this.toast?.('ضبط صدا روی این مرورگر پشتیبانی نمی‌شود','error');return}
   let stream=null;
   try{
    try{await this.primeAquaAudio?.()}catch{}
    stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    const rec=new MediaRecorder(stream);
    const runId=++this.aquaVoiceRunId;
    let finalized=false;
    this.aquaChunks=[];this.aquaRecorder=rec;this.aquaVoiceSending=false;this.aquaVoiceSubmitActive=false;
    rec.ondataavailable=e=>{if(e.data&&e.data.size)this.aquaChunks.push(e.data)};
    rec.onerror=e=>this.toast?.(e?.error?.message||'خطای ضبط صدا','error');
    rec.onstop=async()=>{
     if(finalized)return;finalized=true;
     this.aquaRecording=false;
     try{stream?.getTracks?.().forEach(t=>t.stop())}catch{}
     if(runId!==this.aquaVoiceRunId)return;
     const chunks=[...(this.aquaChunks||[])];this.aquaChunks=[];
     if(!chunks.length){this.toast?.('صدایی ثبت نشد؛ دوباره امتحان کن','error');return}
     const type=rec.mimeType||chunks[0]?.type||'audio/webm';
     const blob=new Blob(chunks,{type});
     if(blob.size<256){this.toast?.('ویس خیلی کوتاه بود؛ دوباره امتحان کن','error');return}
     const ext=type.includes('mp4')?'m4a':type.includes('ogg')?'ogg':type.includes('wav')?'wav':'webm';
     const form=new FormData();form.append('audio',blob,'aqua.'+ext);
     this.aquaTranscribing=true;this.aquaVoiceSending=true;
     try{
      const headers={},csrf=this.cookie?.('aquagold_csrf');if(csrf)headers['X-CSRF-Token']=csrf;
      const response=await fetch('/api/aqua-ai/transcribe',{method:'POST',body:form,headers,credentials:'same-origin',cache:'no-store'});
      let data={};try{data=await response.json()}catch{}
      if(!response.ok)throw Error(data.error||'تبدیل ویس به متن انجام نشد');
      const spoken=String(data.text||'').trim();if(!spoken)throw Error('حرفی از ویس تشخیص داده نشد');
      if(runId!==this.aquaVoiceRunId)return;
      this.aquaInput=spoken;
      this.aquaTranscribing=false;this.aquaVoiceSending=false;this.aquaVoiceSubmitActive=true;
      this.toast?.('گرفتمش؛ دارم برای آریا می‌فرستم…','success');
      const sent=await this.submitAquaVoiceTranscript(spoken,runId);
      this.aquaInput=sent?'':spoken;
      if(!sent)this.toast?.('متن ویس حفظ شد؛ ارسال خودکار انجام نشد','info');
     }catch(e){
      this.aquaVoiceSending=false;this.toast?.(e?.message||'ویس پردازش نشد','error');
     }finally{this.aquaTranscribing=false;this.aquaVoiceSending=false;this.aquaVoiceSubmitActive=false}
    };
    rec.start(250);this.aquaRecording=true;
    this.toast?.('آریا گوش می‌دهد؛ بعد از پایان صحبت دوباره میکروفن را بزن','info');
   }catch(e){
    try{stream?.getTracks?.().forEach(t=>t.stop())}catch{}
    this.aquaRecording=false;this.aquaTranscribing=false;this.aquaVoiceSending=false;this.aquaVoiceSubmitActive=false;
    this.toast?.(e?.message||'دسترسی میکروفن یا شروع ضبط انجام نشد','error');
   }
  };
  return s;
 };
})();
"""


@app_v3.app.get("/aqua-voice-runtime-hotfix.js")
def aqua_voice_runtime_js():
    return Response(VOICE_HOTFIX_JS, mimetype="application/javascript", headers={"Cache-Control": "no-store, max-age=0"})


@app_v3.app.after_request
def aqua_voice_runtime_cache_bust(response):
    try:
        path = request.path
        if path in {"/aqua-ai.js", "/aqua-ai.css", "/aqua-voice-runtime-hotfix.js"}:
            response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers.setdefault("Pragma", "no-cache")
    except Exception as exc:
        app_v3.logger.warning("aqua_voice_cache_bust_failed detail=%s", str(exc)[:200])
    return response