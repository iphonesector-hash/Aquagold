"""Narrow runtime hotfix for Aqua voice on iPhone/PWA.

Keeps the existing Aqua UI intact while restoring the simple MediaRecorder flow,
using Groq Whisper when ElevenLabs STT is unavailable, and cache-busting only
the voice hotfix asset.
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
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", **headers},
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

    # Groq Whisper is independent from ElevenLabs character credits and supports
    # mp4/m4a/webm/ogg, which makes it a stable first choice for iPhone captures.
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
                return jsonify({"text": text, "provider": "groq"})
            provider_errors.append("groq_empty")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            provider_errors.append(f"groq_{exc.code}")
            app_v3.logger.warning("aqua_stt_groq_failed status=%s detail=%s", exc.code, detail)
        except Exception as exc:
            provider_errors.append("groq_network")
            app_v3.logger.warning("aqua_stt_groq_failed detail=%s", str(exc)[:300])

    # Keep ElevenLabs as a secondary provider when credits are available again.
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
                return jsonify({"text": text, "provider": "elevenlabs"})
            provider_errors.append("eleven_empty")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            provider_errors.append(f"eleven_{exc.code}")
            app_v3.logger.warning("aqua_stt_eleven_failed status=%s detail=%s", exc.code, detail)
        except Exception as exc:
            provider_errors.append("eleven_network")
            app_v3.logger.warning("aqua_stt_eleven_failed detail=%s", str(exc)[:300])

    if not groq_key and not eleven_key:
        return jsonify({"error": "برای تبدیل ویس، کلید Groq یا ElevenLabs تنظیم نشده است"}), 409
    return jsonify({"error": "تبدیل ویس به متن موقتاً در دسترس نیست", "providers": provider_errors}), 502


# Reuse the existing Flask URL rule while replacing only its view function.
app_v3.app.view_functions["aqua_transcribe"] = aqua_transcribe_runtime


VOICE_HOTFIX_JS = r"""
(()=>{
 const previous=window.app;
 if(typeof previous!=='function')return;
 const addStyle=()=>{
  if(document.getElementById('aqua-voice-runtime-style'))return;
  const st=document.createElement('style');st.id='aqua-voice-runtime-style';
  st.textContent=`.aqua-composer{position:relative!important;grid-template-columns:54px minmax(0,1fr) auto!important;align-items:center!important}.aqua-composer>button:nth-child(2){position:absolute!important;right:74px!important;top:18px!important;width:42px!important;height:42px!important;z-index:3!important}.aqua-composer textarea{min-width:0!important}@media(max-width:850px){.aqua-composer{grid-template-columns:48px minmax(0,1fr) auto!important}.aqua-composer>button:nth-child(2){right:68px!important;top:15px!important;width:40px!important;height:40px!important}}`;
  document.head.appendChild(st);
 };
 addStyle();
 window.app=function(){
  const s=previous();
  s.toggleAquaRecording=async function(){
   if(this.aquaRecording){
    try{this.aquaRecorder?.stop()}catch(e){this.aquaRecording=false;this.toast?.(e?.message||'توقف ضبط انجام نشد','error')}
    return;
   }
   if(this.aquaTranscribing||this.aquaBusy)return;
   this.stopAquaSpeech?.();
   if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){this.toast?.('ضبط صدا روی این مرورگر پشتیبانی نمی‌شود','error');return}
   let stream=null;
   try{
    stream=await navigator.mediaDevices.getUserMedia({audio:true});
    const rec=new MediaRecorder(stream);
    this.aquaChunks=[];this.aquaRecorder=rec;this.aquaVoiceSending=false;this.aquaVoiceSubmitActive=false;
    rec.ondataavailable=e=>{if(e.data&&e.data.size)this.aquaChunks.push(e.data)};
    rec.onerror=e=>this.toast?.(e?.error?.message||'خطای ضبط صدا','error');
    rec.onstop=async()=>{
     this.aquaRecording=false;
     try{stream?.getTracks?.().forEach(t=>t.stop())}catch{}
     const chunks=[...(this.aquaChunks||[])];this.aquaChunks=[];
     if(!chunks.length){this.toast?.('صدایی ثبت نشد؛ دوباره امتحان کن','error');return}
     const type=rec.mimeType||chunks[0]?.type||'audio/webm';
     const blob=new Blob(chunks,{type});
     const ext=type.includes('mp4')?'m4a':type.includes('ogg')?'ogg':type.includes('wav')?'wav':'webm';
     const form=new FormData();form.append('audio',blob,'aqua.'+ext);
     this.aquaTranscribing=true;this.aquaVoiceSending=true;
     try{
      const headers={},csrf=this.cookie?.('aquagold_csrf');if(csrf)headers['X-CSRF-Token']=csrf;
      const response=await fetch('/api/aqua-ai/transcribe',{method:'POST',body:form,headers,credentials:'same-origin',cache:'no-store'});
      let data={};try{data=await response.json()}catch{}
      if(!response.ok)throw Error(data.error||'تبدیل ویس به متن انجام نشد');
      const spoken=String(data.text||'').trim();if(!spoken)throw Error('حرفی از ویس تشخیص داده نشد');
      this.aquaTranscribing=false;this.aquaVoiceSending=false;
      const sent=await this.submitAquaText(spoken,'voice');
      this.aquaInput=sent?'':spoken;
      if(!sent)this.toast?.('متن ویس حفظ شد؛ ارسال خودکار انجام نشد','info');
     }catch(e){
      this.aquaVoiceSending=false;this.toast?.(e?.message||'ویس پردازش نشد','error');
     }finally{this.aquaTranscribing=false;this.aquaVoiceSending=false;this.aquaVoiceSubmitActive=false}
    };
    rec.start();this.aquaRecording=true;
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
        if path in {"/", "/index.html"} and response.mimetype == "text/html":
            body = response.get_data(as_text=True)
            marker = '<script src="/aqua-ai.js?v=20260827-v76"></script>'
            injection = marker + '<script src="/aqua-voice-runtime-hotfix.js?v=20260831-voice1"></script>'
            if marker in body and "aqua-voice-runtime-hotfix.js" not in body:
                body = body.replace(marker, injection, 1)
                response.set_data(body)
                response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_voice_cache_bust_failed detail=%s", str(exc)[:200])
    return response
