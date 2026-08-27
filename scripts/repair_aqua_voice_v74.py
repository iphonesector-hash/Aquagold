from pathlib import Path

js_path = Path('aqua-ai.js')
js = js_path.read_text()
js = js.replace("aquaSpeaking:false,aquaAudio:null,aquaMounted:false", "aquaSpeaking:false,aquaAudio:null,aquaAudioContext:null,aquaMounted:false")
js = js.replace("s.aquaHistory=function(){return this.aquaMessages.filter(x=>!x.pending_action).slice(-8).map(x=>({role:x.role,content:x.content}))};", "s.aquaHistory=function(){return this.aquaMessages.filter(x=>!x.pending_action&&!x.error).slice(-4).map(x=>({role:x.role,content:String(x.content||'').slice(0,900)}))};")
js = js.replace("if(this.aquaSettings.auto_speak)this.speakAqua(m.content)", "await this.speakAqua(m.content)")
old = "this.aquaInput=(d.text||'').trim();if(this.aquaInput)this.toast('صدای شما به متن تبدیل شد؛ برای ارسال دکمه ارسال را بزن','success')}catch(e){this.toast(e.message,'error')}finally{this.aquaBusy=false}"
new = "let spoken=(d.text||'').trim();this.aquaInput=spoken;this.aquaBusy=false;if(spoken){this.toast('صدا تبدیل شد؛ در حال ارسال…','success');await this.sendAqua(spoken)}}catch(e){this.toast(e.message,'error')}finally{this.aquaBusy=false}"
if old not in js:
    raise SystemExit('recording block not found')
js = js.replace(old, new)
old = "s.toggleAquaRecording=async function(){if(this.aquaRecording){this.aquaRecorder?.stop();return}if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)return this.toast('ضبط صدا پشتیبانی نمی‌شود','error');try{let stream=await navigator.mediaDevices.getUserMedia({audio:true}),rec=new MediaRecorder(stream);"
new = "s.toggleAquaRecording=async function(){if(this.aquaRecording){this.aquaRecorder?.stop();return}if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)return this.toast('ضبط صدا پشتیبانی نمی‌شود','error');try{try{let AC=window.AudioContext||window.webkitAudioContext;if(AC){if(!this.aquaAudioContext)this.aquaAudioContext=new AC();if(this.aquaAudioContext.state==='suspended')await this.aquaAudioContext.resume()}}catch{}let stream=await navigator.mediaDevices.getUserMedia({audio:true}),rec=new MediaRecorder(stream);"
if old not in js:
    raise SystemExit('toggle block not found')
js = js.replace(old, new)
old = "let u=URL.createObjectURL(blob),a=new Audio(u);this.aquaAudio=a;await new Promise((resolve,reject)=>{a.onended=resolve;a.onerror=()=>reject(Error('پخش صدا در مرورگر ناموفق بود'));let p=a.play();if(p?.catch)p.catch(reject)});URL.revokeObjectURL(u);this.aquaAudio=null"
new = "let played=false;if(this.aquaAudioContext){try{if(this.aquaAudioContext.state==='suspended')await this.aquaAudioContext.resume();let buf=await blob.arrayBuffer(),decoded=await this.aquaAudioContext.decodeAudioData(buf.slice(0)),src=this.aquaAudioContext.createBufferSource();src.buffer=decoded;src.connect(this.aquaAudioContext.destination);await new Promise(resolve=>{src.onended=resolve;src.start(0)});played=true}catch(e){console.warn('WebAudio playback failed',e)}}if(!played){let u=URL.createObjectURL(blob),a=new Audio(u);this.aquaAudio=a;await new Promise((resolve,reject)=>{a.onended=resolve;a.onerror=()=>reject(Error('پخش صدا در مرورگر ناموفق بود'));let p=a.play();if(p?.catch)p.catch(reject)});URL.revokeObjectURL(u);this.aquaAudio=null}"
if old not in js:
    raise SystemExit('playback block not found')
js_path.write_text(js)

py_path = Path('aqua_ai.py')
py = py_path.read_text()
old = "retry_messages = [\n            {\"role\": \"system\", \"content\": system_text[:1200]},\n            {\"role\": \"user\", \"content\": str(text)[:1200]},\n        ]\n        data = _post_json(endpoint, {\"model\": settings.get(\"brain_model\") or \"groq/compound\", \"messages\": retry_messages, \"temperature\": 0.2}, headers)"
new = "retry_messages = [\n            {\"role\": \"system\", \"content\": system_text[:900]},\n            {\"role\": \"user\", \"content\": str(text)[:900]},\n        ]\n        # Compound can overflow internally on live-search/tool queries even with a tiny input.\n        # Retry on compound-mini first, then a plain chat model so the user always gets a response.\n        try:\n            data = _post_json(endpoint, {\"model\": \"groq/compound-mini\", \"messages\": retry_messages, \"temperature\": 0.2}, headers)\n        except RuntimeError:\n            data = _post_json(endpoint, {\"model\": \"llama-3.3-70b-versatile\", \"messages\": retry_messages, \"temperature\": 0.2}, headers)"
if old not in py:
    raise SystemExit('groq retry block not found')
py = py.replace(old, new)
py_path.write_text(py)

index_path = Path('index.html')
index = index_path.read_text()
index = index.replace('/aqua-ai.js?v=20260827-v71', '/aqua-ai.js?v=20260827-v74')
index_path.write_text(index)

print('patched Aqua voice conversation v7.4')
