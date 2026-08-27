from pathlib import Path
import re

js_path=Path('aqua-ai.js')
js=js_path.read_text(encoding='utf-8')

js=js.replace("const hello=()=>({role:'assistant',content:'سلام، من هوش مصنوعی آکوا هستم. مشتری را روی نقشه پیدا می‌کنم، ثبت مشتری را آماده می‌کنم، گزارش فروش می‌سازم و در وب جست‌وجو می‌کنم.'});",
              "const hello=()=>({role:'assistant',content:'سلام، من آریام 😄 رفیق خودمونیِ تو توی AquaGold. هرچی لازم داری راحت بگو؛ از مشتری و مسیر و گزارش گرفته تا کارهای روزمره، باهم جمعش می‌کنیم.'});")
js=js.replace("aquaAudioContext:null,aquaAudioKeeper:null,aquaTranscribing:false,aquaMounted:false",
              "aquaAudioContext:null,aquaAudioKeeper:null,aquaPlayer:null,aquaTranscribing:false,aquaVoiceSending:false,aquaMounted:false")

send_pat=re.compile(r"s\.sendAqua=async function\(value=null\)\{.*?\};\n", re.S)
send_new="""s.submitAquaText=async function(value,source='text'){let text=String(value??'').trim();if(!text)return false;if(this.aquaBusy){if(source==='voice')this.toast?.('آریا هنوز در حال جواب دادن است؛ یک لحظه صبر کن','info');return false}this.aquaMessages.push({role:'user',content:text});this.aquaInput='';this.aquaBusy=true;this.aquaScroll();try{let history=this.aquaHistory(),r=await this.api('/aqua-ai/chat',{method:'POST',body:JSON.stringify({text,history})}),m={role:'assistant',content:r.answer||'انجام شد',chart:r.chart,pending_action:r.pending_action,action:r.action,results:r.results};this.aquaMessages.push(m);this.aquaScroll();await this.speakAqua(m.content);return true}catch(e){this.aquaMessages.push({role:'assistant',content:e.message,error:true});return false}finally{this.aquaBusy=false;this.aquaVoiceSending=false;this.aquaScroll()}};\ns.sendAqua=async function(value=null){let text=String(value??this.aquaInput).trim();return this.submitAquaText(text,'text')};\n"""
js,n=send_pat.subn(send_new,js,count=1)
if n!=1: raise SystemExit('sendAqua block not found')

rec_pat=re.compile(r"s\.toggleAquaRecording=async function\(\)\{.*?\};\n", re.S)
rec_new="""s.primeAquaAudio=async function(){try{if(!this.aquaPlayer){let a=new Audio();a.playsInline=true;a.preload='auto';a.src='data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQQAAAAA';a.volume=.001;this.aquaPlayer=a}let p=this.aquaPlayer.play();if(p?.then)await p;this.aquaPlayer.pause();this.aquaPlayer.currentTime=0;this.aquaPlayer.volume=1}catch(e){console.warn('Aqua audio element prime failed',e)}try{let AC=window.AudioContext||window.webkitAudioContext;if(AC){if(!this.aquaAudioContext)this.aquaAudioContext=new AC();if(this.aquaAudioContext.state==='suspended')await this.aquaAudioContext.resume();if(!this.aquaAudioKeeper){let gain=this.aquaAudioContext.createGain(),osc=this.aquaAudioContext.createOscillator();gain.gain.value=.000001;osc.frequency.value=40;osc.connect(gain);gain.connect(this.aquaAudioContext.destination);osc.start();this.aquaAudioKeeper={osc,gain}}}}catch(e){console.warn('Aqua WebAudio prime failed',e)}};\ns.toggleAquaRecording=async function(){if(this.aquaRecording){this.aquaRecorder?.stop();return}if(this.aquaTranscribing||this.aquaVoiceSending||this.aquaBusy)return;if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)return this.toast('ضبط صدا پشتیبانی نمی‌شود','error');try{await this.primeAquaAudio();let stream=await navigator.mediaDevices.getUserMedia({audio:true}),rec=new MediaRecorder(stream);this.aquaChunks=[];this.aquaRecorder=rec;rec.ondataavailable=e=>{if(e.data.size)this.aquaChunks.push(e.data)};rec.onstop=async()=>{this.aquaRecording=false;stream.getTracks().forEach(t=>t.stop());let form=new FormData();form.append('audio',new Blob(this.aquaChunks,{type:rec.mimeType||'audio/webm'}),'aqua.webm');this.aquaTranscribing=true;try{let h={},csrf=this.cookie('aquagold_csrf');if(csrf)h['X-CSRF-Token']=csrf;let response=await fetch('/api/aqua-ai/transcribe',{method:'POST',body:form,headers:h,credentials:'same-origin'}),d=await response.json();if(!response.ok)throw Error(d.error);let spoken=String(d.text||'').trim();if(!spoken)throw Error('صدایی برای ارسال تشخیص داده نشد');this.aquaInput='';this.aquaTranscribing=false;this.aquaVoiceSending=true;this.toast('گرفتمش؛ دارم برای آریا می‌فرستم…','success');await this.submitAquaText(spoken,'voice')}catch(e){this.aquaVoiceSending=false;this.aquaInput='';this.toast(e.message,'error')}finally{this.aquaTranscribing=false}};rec.start();this.aquaRecording=true;this.toast('آریا گوش می‌ده؛ وقتی حرفت تموم شد دوباره میکروفن رو بزن','info')}catch(e){this.toast('اجازه میکروفون داده نشد','error')}};\n"""
js,n=rec_pat.subn(rec_new,js,count=1)
if n!=1: raise SystemExit('record block not found')

speak_pat=re.compile(r"s\.speakAqua=async function\(text\)\{.*?\};\n", re.S)
speak_new="""s.speakAqua=async function(text){if(this.aquaSpeaking||!String(text||'').trim())return;this.aquaSpeaking=true;let url=null;try{let h={'Content-Type':'application/json'},csrf=this.cookie('aquagold_csrf');if(csrf)h['X-CSRF-Token']=csrf;let r=await fetch('/api/aqua-ai/speak',{method:'POST',headers:h,credentials:'same-origin',body:JSON.stringify({text})});if(!r.ok){let d={};try{d=await r.json()}catch{}throw Error(d.error||'صدای آریا آماده نشد')}let blob=await r.blob();if(!blob.size)throw Error('فایل صدای خالی دریافت شد');url=URL.createObjectURL(blob);let played=false;if(this.aquaPlayer){try{let a=this.aquaPlayer;a.pause();a.src=url;a.muted=false;a.volume=1;a.currentTime=0;a.load();await new Promise((resolve,reject)=>{a.onended=resolve;a.onerror=()=>reject(Error('پخش صدای آریا روی آیفون ناموفق بود'));let p=a.play();if(p?.catch)p.catch(reject)});played=true}catch(e){console.warn('Aqua unlocked audio player failed',e)}}if(!played&&this.aquaAudioContext){try{if(this.aquaAudioContext.state==='suspended')await this.aquaAudioContext.resume();let buf=await blob.arrayBuffer(),decoded=await this.aquaAudioContext.decodeAudioData(buf.slice(0)),src=this.aquaAudioContext.createBufferSource();src.buffer=decoded;src.connect(this.aquaAudioContext.destination);await new Promise(resolve=>{src.onended=resolve;src.start(0)});played=true}catch(e){console.warn('Aqua WebAudio fallback failed',e)}}if(!played)throw Error('Safari اجازه پخش خودکار صدا را نداد')}catch(e){console.warn('Aqua TTS playback failed',e);this.toast?.(e.message||'پخش صدای آریا ناموفق بود','error')}finally{if(url)setTimeout(()=>URL.revokeObjectURL(url),1000);this.aquaSpeaking=false}};\n"""
js,n=speak_pat.subn(speak_new,js,count=1)
if n!=1: raise SystemExit('speak block not found')

js_path.write_text(js,encoding='utf-8')

py_path=Path('aqua_ai.py')
py=py_path.read_text(encoding='utf-8')
old='system_text = "تو آریا، دستیار فارسی و تهرانی AquaGold هستی. کوتاه، دقیق و عملی جواب بده. تغییر دیتابیس را بدون تأیید کاربر انجام‌شده فرض نکن. وضعیت فعلی: " + json.dumps(compact_context, ensure_ascii=False)'
new='system_text = "تو آریا هستی؛ دستیار فارسی AquaGold و رفیق صمیمی کاربر. فارسی تهرانی، گرم، طبیعی و خودمونی حرف بزن؛ مثل یک دوست باهوش و قابل‌اعتماد، نه کارمند اداری. جواب‌ها روان و کوتاه باشند، گاهی از واژه‌های طبیعی مثل «آره»، «ببین»، «اوکی»، «حتماً» استفاده کن ولی لوس، مصنوعی یا بیش‌ازحد شوخ نباش. اگر موضوع جدی/مالی است دقیق بمان. تغییر دیتابیس را بدون تأیید کاربر انجام‌شده فرض نکن. وضعیت فعلی: " + json.dumps(compact_context, ensure_ascii=False)'
if old not in py: raise SystemExit('system prompt not found')
py=py.replace(old,new)
py_path.write_text(py,encoding='utf-8')

# bump script URL to defeat any retained tab/resource state
idx=Path('index.html')
html=idx.read_text(encoding='utf-8')
html=re.sub(r'/aqua-ai\.js\?v=[^\"\']+', '/aqua-ai.js?v=20260827-v76', html)
idx.write_text(html,encoding='utf-8')
