"""Small iOS/PWA TTS patch layered after the Aqua voice runtime hotfix.

Safari may expose system Persian speech without listing the installed voice name in
speechSynthesis.getVoices(). In that case, using lang='fa-IR' with no explicit
voice lets iOS choose the configured Persian system voice (e.g. Dariush).
"""
from flask import Response

import app_v3


IOS_TTS_PATCH_JS = r"""
(()=>{
 const previous=window.app;
 if(typeof previous!=='function')return;
 const waitVoices=async()=>{
  if(!window.speechSynthesis)return[];
  let v=window.speechSynthesis.getVoices?.()||[];
  if(v.length)return v;
  await new Promise(resolve=>{
   let done=false;
   const finish=()=>{if(done)return;done=true;resolve()};
   try{window.speechSynthesis.addEventListener('voiceschanged',finish,{once:true})}catch{}
   setTimeout(finish,700);
  });
  return window.speechSynthesis.getVoices?.()||[];
 };
 const chooseFa=voices=>{
  const list=Array.isArray(voices)?voices:[];
  const norm=x=>String(x||'').toLowerCase();
  return list.find(v=>norm(v.name).includes('dariush')||norm(v.voiceURI).includes('dariush')||norm(v.name).includes('داریوش')||norm(v.voiceURI).includes('داریوش'))
      ||list.find(v=>/^fa(?:-|_)/i.test(String(v.lang||'')))
      ||null;
 };
 window.app=function(){
  const s=previous();
  s.speakAqua=async function(text){
   text=String(text||'').trim();
   if(!text||document.hidden)return false;
   this.stopAquaSpeech?.();
   try{
    if(!window.speechSynthesis||!window.SpeechSynthesisUtterance)throw Error('speechSynthesis unavailable');
    const voices=await waitVoices();
    if(document.hidden)return false;
    const voice=chooseFa(voices);
    const utter=new SpeechSynthesisUtterance(text);
    utter.lang='fa-IR';
    if(voice)utter.voice=voice;
    utter.rate=.93;utter.pitch=1;utter.volume=1;
    this.aquaSpeechUtterance=utter;
    window.speechSynthesis.cancel();
    try{window.speechSynthesis.resume?.()}catch{}
    await new Promise((resolve,reject)=>{
     let started=false,done=false;
     const finish=(ok,e)=>{if(done)return;done=true;this.aquaSpeaking=false;this.aquaSpeechUtterance=null;ok?resolve():reject(e||Error('speech failed'))};
     utter.onstart=()=>{started=true;this.aquaSpeaking=true};
     utter.onend=()=>finish(true);
     utter.onerror=e=>finish(false,Error(e?.error||'speech synthesis failed'));
     window.speechSynthesis.speak(utter);
     setTimeout(()=>{if(!started)finish(false,Error('iOS Persian speech did not start'))},5000);
    });
    return true;
   }catch(e){
    console.warn('Aqua iOS Persian TTS patch failed',e);
    this.aquaSpeaking=false;
    this.aquaSpeechUtterance=null;
    this.toast?.('صدای فارسی آیفون شروع نشد؛ یک‌بار روی دکمه بلندگو یا میکروفن بزن و دوباره تست کن','info');
    return false;
   }
  };
  return s;
 };
})();
"""


@app_v3.app.get('/aqua-ios-tts-patch.js')
def aqua_ios_tts_patch_js():
    return Response(IOS_TTS_PATCH_JS, mimetype='application/javascript', headers={'Cache-Control':'no-store, max-age=0'})
