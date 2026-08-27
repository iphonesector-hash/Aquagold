/* Aria v8: deterministic iPhone voice capture, transcript recovery and direct voice-to-chat. */
(()=>{
const previous=window.app;
if(typeof previous!=='function')return;
const pickMime=()=>{const list=['audio/mp4','audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus'];for(const m of list){try{if(window.MediaRecorder?.isTypeSupported?.(m))return m}catch{}}return''};
window.app=function(){
 const s=previous();
 Object.assign(s,{aquaVoiceState:'idle',aquaLastTranscript:'',aquaVoiceError:'',aquaVoiceSequence:0});
 const oldStop=s.stopAquaSpeech?.bind(s);
 s.stopAquaSpeech=function(){this.aquaVoiceSequence=(this.aquaVoiceSequence||0)+1;try{oldStop?.()}catch{}if(!this.aquaRecording&&!this.aquaTranscribing&&!this.aquaBusy)this.aquaVoiceState='idle'};
 s.sendAquaVoiceText=async function(value){
  const text=String(value||'').trim();if(!text)return false;
  this.stopAquaSpeech?.();
  const seq=++this.aquaVoiceSequence;
  this.aquaLastTranscript=text;this.aquaInput=text;this.aquaVoiceError='';
  this.aquaMessages.push({role:'user',content:text});this.aquaInput='';this.aquaBusy=true;this.aquaVoiceSending=true;this.aquaVoiceState='thinking';this.aquaScroll?.();
  try{
   const history=this.aquaHistory?.()||[];
   const r=await this.api('/aqua-ai/chat',{method:'POST',body:JSON.stringify({text,history})});
   if(seq!==this.aquaVoiceSequence)return false;
   const m={role:'assistant',content:r.answer||'انجام شد',chart:r.chart,pending_action:r.pending_action,action:r.action,results:r.results};
   this.aquaMessages.push(m);this.aquaBusy=false;this.aquaVoiceSending=false;this.aquaVoiceState='speaking';this.aquaScroll?.();
   setTimeout(async()=>{if(seq!==this.aquaVoiceSequence)return;try{await this.speakAqua?.(m.content)}finally{if(seq===this.aquaVoiceSequence&&!this.aquaRecording&&!this.aquaTranscribing)this.aquaVoiceState='idle'}},20);
   return true;
  }catch(e){
   if(seq===this.aquaVoiceSequence){this.aquaInput=text;this.aquaVoiceError=e?.message||'ارسال ویس انجام نشد';this.aquaMessages.push({role:'assistant',content:this.aquaVoiceError,error:true});}
   return false;
  }finally{
   if(seq===this.aquaVoiceSequence){this.aquaBusy=false;this.aquaVoiceSending=false;if(this.aquaVoiceState==='thinking')this.aquaVoiceState='idle'}
   this.aquaScroll?.();
  }
 };
 s.toggleAquaRecording=async function(){
  if(this.aquaRecording){
   this.aquaVoiceState='stopping';
   try{this.aquaRecorder?.requestData?.()}catch{}
   try{this.aquaRecorder?.stop()}catch(e){this.aquaRecording=false;this.aquaVoiceState='idle';this.toast?.(e?.message||'توقف ضبط انجام نشد','error')}
   return;
  }
  if(this.aquaTranscribing||this.aquaVoiceSending||this.aquaBusy)return;
  this.stopAquaSpeech?.();
  if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){this.toast?.('ضبط صدا روی این مرورگر پشتیبانی نمی‌شود','error');return}
  let stream=null;
  try{
   await this.primeAquaAudio?.();
   stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
   const mime=pickMime();
   const rec=mime?new MediaRecorder(stream,{mimeType:mime}):new MediaRecorder(stream);
   this.aquaChunks=[];this.aquaRecorder=rec;this.aquaVoiceState='recording';this.aquaVoiceError='';
   rec.ondataavailable=e=>{if(e.data&&e.data.size>0)this.aquaChunks.push(e.data)};
   rec.onerror=e=>{this.aquaVoiceError=e?.error?.message||'خطای ضبط صدا';this.toast?.(this.aquaVoiceError,'error')};
   rec.onstop=async()=>{
    this.aquaRecording=false;
    try{stream?.getTracks?.().forEach(t=>t.stop())}catch{}
    const chunks=[...(this.aquaChunks||[])];this.aquaChunks=[];
    if(!chunks.length){this.aquaVoiceState='idle';this.toast?.('صدایی ثبت نشد؛ دوباره امتحان کن','error');return}
    const type=rec.mimeType||mime||chunks[0]?.type||'audio/webm';
    const blob=new Blob(chunks,{type});
    if(blob.size<256){this.aquaVoiceState='idle';this.toast?.('فایل صدا خیلی کوتاه بود؛ دوباره امتحان کن','error');return}
    this.aquaTranscribing=true;this.aquaVoiceState='transcribing';
    try{
     const form=new FormData();
     const ext=type.includes('mp4')?'m4a':type.includes('ogg')?'ogg':'webm';
     form.append('audio',blob,'aria.'+ext);
     const headers={},csrf=this.cookie?.('aquagold_csrf');if(csrf)headers['X-CSRF-Token']=csrf;
     const response=await fetch('/api/aqua-ai/transcribe',{method:'POST',body:form,headers,credentials:'same-origin',cache:'no-store'});
     let d={};try{d=await response.json()}catch{}
     if(!response.ok)throw Error(d.error||'تبدیل صدا به متن انجام نشد');
     const spoken=String(d.text||'').trim();if(!spoken)throw Error('حرفی از صدا تشخیص داده نشد');
     this.aquaLastTranscript=spoken;this.aquaInput=spoken;this.aquaTranscribing=false;this.aquaVoiceState='ready';
     this.toast?.('گرفتمش؛ دارم می‌فرستم…','success');
     const sent=await this.sendAquaVoiceText(spoken);
     if(!sent){this.aquaInput=spoken;this.aquaVoiceState='ready';this.toast?.('متنت حفظ شد؛ ارسال خودکار انجام نشد','info')}
    }catch(e){
     this.aquaVoiceError=e?.message||'ویس پردازش نشد';
     this.aquaVoiceState='idle';this.aquaVoiceSending=false;this.toast?.(this.aquaVoiceError,'error');
    }finally{this.aquaTranscribing=false}
   };
   rec.start(250);
   this.aquaRecording=true;this.aquaVoiceState='recording';
   this.toast?.('آریا گوش می‌ده؛ وقتی تموم شد دوباره میکروفن رو بزن','info');
  }catch(e){
   try{stream?.getTracks?.().forEach(t=>t.stop())}catch{}
   this.aquaRecording=false;this.aquaTranscribing=false;this.aquaVoiceSending=false;this.aquaVoiceState='idle';
   this.toast?.(e?.message||'دسترسی میکروفن یا شروع ضبط انجام نشد','error');
  }
 };
 return s;
};
})();
