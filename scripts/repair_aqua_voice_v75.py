from pathlib import Path

js = Path('aqua-ai.js')
s = js.read_text()

old = "aquaSpeaking:false,aquaAudio:null,aquaAudioContext:null,aquaMounted:false"
new = "aquaSpeaking:false,aquaAudio:null,aquaAudioContext:null,aquaAudioKeeper:null,aquaTranscribing:false,aquaMounted:false"
assert old in s
s = s.replace(old, new, 1)

old = "s.toggleAquaRecording=async function(){if(this.aquaRecording){this.aquaRecorder?.stop();return}if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)return this.toast('ضبط صدا پشتیبانی نمی‌شود','error');try{try{let AC=window.AudioContext||window.webkitAudioContext;if(AC){if(!this.aquaAudioContext)this.aquaAudioContext=new AC();if(this.aquaAudioContext.state==='suspended')await this.aquaAudioContext.resume()}}catch{}let stream=await navigator.mediaDevices.getUserMedia({audio:true}),rec=new MediaRecorder(stream);this.aquaChunks=[];this.aquaRecorder=rec;rec.ondataavailable=e=>{if(e.data.size)this.aquaChunks.push(e.data)};rec.onstop=async()=>{this.aquaRecording=false;stream.getTracks().forEach(t=>t.stop());let form=new FormData();form.append('audio',new Blob(this.aquaChunks,{type:rec.mimeType||'audio/webm'}),'aqua.webm');this.aquaBusy=true;try{let h={},csrf=this.cookie('aquagold_csrf');if(csrf)h['X-CSRF-Token']=csrf;let response=await fetch('/api/aqua-ai/transcribe',{method:'POST',body:form,headers:h,credentials:'same-origin'}),d=await response.json();if(!response.ok)throw Error(d.error);let spoken=(d.text||'').trim();this.aquaInput=spoken;this.aquaBusy=false;if(spoken){this.toast('صدا تبدیل شد؛ در حال ارسال…','success');await this.sendAqua(spoken)}}catch(e){this.toast(e.message,'error')}finally{this.aquaBusy=false}};rec.start();this.aquaRecording=true;this.toast('آکوا گوش می‌دهد؛ برای پایان دوباره میکروفون را بزن','info')}catch{this.toast('اجازه میکروفون داده نشد','error')}};"
new = "s.toggleAquaRecording=async function(){if(this.aquaRecording){this.aquaRecorder?.stop();return}if(this.aquaTranscribing)return;if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)return this.toast('ضبط صدا پشتیبانی نمی‌شود','error');try{try{let AC=window.AudioContext||window.webkitAudioContext;if(AC){if(!this.aquaAudioContext)this.aquaAudioContext=new AC();if(this.aquaAudioContext.state==='suspended')await this.aquaAudioContext.resume();if(!this.aquaAudioKeeper){let gain=this.aquaAudioContext.createGain(),osc=this.aquaAudioContext.createOscillator();gain.gain.value=0;osc.connect(gain);gain.connect(this.aquaAudioContext.destination);osc.start();this.aquaAudioKeeper={osc,gain}}}}catch(e){console.warn('Aqua audio prime failed',e)}let stream=await navigator.mediaDevices.getUserMedia({audio:true}),rec=new MediaRecorder(stream);this.aquaChunks=[];this.aquaRecorder=rec;rec.ondataavailable=e=>{if(e.data.size)this.aquaChunks.push(e.data)};rec.onstop=async()=>{this.aquaRecording=false;stream.getTracks().forEach(t=>t.stop());let form=new FormData();form.append('audio',new Blob(this.aquaChunks,{type:rec.mimeType||'audio/webm'}),'aqua.webm');this.aquaTranscribing=true;try{let h={},csrf=this.cookie('aquagold_csrf');if(csrf)h['X-CSRF-Token']=csrf;let response=await fetch('/api/aqua-ai/transcribe',{method:'POST',body:form,headers:h,credentials:'same-origin'}),d=await response.json();if(!response.ok)throw Error(d.error);let spoken=(d.text||'').trim();this.aquaInput=spoken;if(spoken){this.toast('صدا تبدیل شد؛ در حال ارسال…','success');this.aquaTranscribing=false;await this.sendAqua(spoken)}}catch(e){this.toast(e.message,'error')}finally{this.aquaTranscribing=false}};rec.start();this.aquaRecording=true;this.toast('آکوا گوش می‌دهد؛ برای پایان دوباره میکروفون را بزن','info')}catch{this.toast('اجازه میکروفون داده نشد','error')}};"
assert old in s
s = s.replace(old, new, 1)

js.write_text(s)

enh = Path('ui-v4-enhancements.js')
e = enh.read_text()
old = '<div class="aq-float no-print"><button type="button" @click="openGlobalSearch"'
new = '<div class="aq-float no-print" x-show="page!==\'aqua-ai\'"><button type="button" @click="openGlobalSearch"'
assert old in e
e = e.replace(old, new, 1)
enh.write_text(e)

idx = Path('index.html')
i = idx.read_text()
i = i.replace('/aqua-ai.js?v=20260827-v72', '/aqua-ai.js?v=20260827-v75')
i = i.replace('/ui-v4-enhancements.js?v=20260827-v69', '/ui-v4-enhancements.js?v=20260827-v75')
idx.write_text(i)
