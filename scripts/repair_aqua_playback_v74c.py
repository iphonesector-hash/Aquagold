from pathlib import Path
import re
p=Path('aqua-ai.js')
s=p.read_text()
new="""s.speakAqua=async function(text){if(this.aquaSpeaking)return;this.aquaSpeaking=true;try{let h={'Content-Type':'application/json'},csrf=this.cookie('aquagold_csrf');if(csrf)h['X-CSRF-Token']=csrf;let r=await fetch('/api/aqua-ai/speak',{method:'POST',headers:h,credentials:'same-origin',body:JSON.stringify({text})});if(!r.ok){let d={};try{d=await r.json()}catch{}throw Error(d.error||'صدای آریا آماده نشد')}let blob=await r.blob();if(!blob.size)throw Error('فایل صدای خالی دریافت شد');let played=false;if(this.aquaAudioContext){try{if(this.aquaAudioContext.state==='suspended')await this.aquaAudioContext.resume();let buf=await blob.arrayBuffer(),decoded=await this.aquaAudioContext.decodeAudioData(buf.slice(0)),src=this.aquaAudioContext.createBufferSource();src.buffer=decoded;src.connect(this.aquaAudioContext.destination);await new Promise(resolve=>{src.onended=resolve;src.start(0)});played=true}catch(e){console.warn('Aqua WebAudio failed',e)}}if(!played){let u=URL.createObjectURL(blob),a=new Audio(u);a.playsInline=true;this.aquaAudio=a;await new Promise((resolve,reject)=>{a.onended=resolve;a.onerror=()=>reject(Error('پخش صدا در مرورگر ناموفق بود'));let q=a.play();if(q?.catch)q.catch(reject)});URL.revokeObjectURL(u);this.aquaAudio=null}}catch(e){console.warn('Aqua TTS playback failed',e);this.toast?.(e.message||'پخش صدای آریا ناموفق بود','error')}finally{this.aquaSpeaking=false}};"""
s2,n=re.subn(r"s\.speakAqua=async function\(text\)\{.*?\};\ns\.mountAquaAI=",new+'\ns.mountAquaAI=',s,flags=re.S)
if n!=1: raise SystemExit(f'speak replacement count={n}')
p.write_text(s2)
print('Safari playback patched')
