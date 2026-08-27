from pathlib import Path
import re

# Backend chat SQL + robust ElevenLabs TTS.
p=Path('aqua_ai.py'); s=p.read_text(encoding='utf-8')
if 'import time\n' not in s:
    s=s.replace('import re\n', 'import re\nimport time\n')
s=s.replace("select extract(hour from coalesce(visited_at,created_at) at time zone 'Asia/Tehran')::int hour,", "select extract(hour from coalesce(visited_at,created_at) at time zone 'Asia/Tehran')::int as hour_of_day,")
s=s.replace('sum(int(x["sales"]) for x in points)', 'sum(int(x["sales"]) for x in points)')
# normalize API field back to `hour` for current chart UI
old='''    points = [app_v3.row_json(row) for row in cur.fetchall()]\n    return points, sum(int(x["sales"]) for x in points), sum(int(x["received"]) for x in points)'''
new='''    points = [app_v3.row_json(row) for row in cur.fetchall()]\n    for point in points:\n        point["hour"] = point.pop("hour_of_day", point.get("hour"))\n    return points, sum(int(x["sales"]) for x in points), sum(int(x["received"]) for x in points)'''
if old not in s:
    raise SystemExit('today sales points marker missing')
s=s.replace(old,new)
old='''    req = urllib.request.Request(\n        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",\n        data=json.dumps({"text": text, "model_id": settings.get("tts_model") or "eleven_v3"}, ensure_ascii=False).encode(),\n        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},\n        method="POST",\n    )\n    try:\n        with urllib.request.urlopen(req, timeout=60) as response:\n            audio = response.read()\n    except urllib.error.HTTPError as exc:\n        return jsonify({"error": f"ساخت صدا ناموفق بود ({exc.code})"}), 502\n    return Response(audio, mimetype="audio/mpeg", headers={"Cache-Control": "no-store"})'''
new='''    requested_model = settings.get("tts_model") or "eleven_v3"\n    models = [requested_model]\n    if requested_model != "eleven_multilingual_v2":\n        models.append("eleven_multilingual_v2")\n    last_error = None\n    for model_id in models:\n        for attempt in range(3):\n            req = urllib.request.Request(\n                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",\n                data=json.dumps({"text": text, "model_id": model_id}, ensure_ascii=False).encode(),\n                headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},\n                method="POST",\n            )\n            try:\n                with urllib.request.urlopen(req, timeout=60) as response:\n                    audio = response.read()\n                    if audio:\n                        return Response(audio, mimetype="audio/mpeg", headers={"Cache-Control": "no-store", "X-Aqua-TTS-Model": model_id})\n                    last_error = "empty_audio"\n            except urllib.error.HTTPError as exc:\n                detail = exc.read().decode(errors="replace")[:500]\n                last_error = f"HTTP {exc.code}: {detail}"\n                app_v3.logger.warning("aqua_tts_failed model=%s attempt=%s status=%s detail=%s", model_id, attempt + 1, exc.code, detail)\n                if exc.code not in {408, 409, 422, 429, 500, 502, 503, 504}:\n                    break\n            except urllib.error.URLError as exc:\n                last_error = str(exc.reason)[:300]\n                app_v3.logger.warning("aqua_tts_network_failed model=%s attempt=%s detail=%s", model_id, attempt + 1, last_error)\n            if attempt < 2:\n                time.sleep(0.35 * (attempt + 1))\n    app_v3.logger.error("aqua_tts_exhausted detail=%s", last_error)\n    return jsonify({"error": "ساخت صدای آریا موقتاً ناموفق بود؛ دوباره تلاش کن"}), 502'''
if old not in s:
    raise SystemExit('aqua speak marker missing')
s=s.replace(old,new)
p.write_text(s,encoding='utf-8')

# Frontend voice flow + Safari-safe TTS concurrency.
p=Path('aqua-ai.js'); s=p.read_text(encoding='utf-8')
s=s.replace("aquaRecorder:null,aquaChunks:[]", "aquaRecorder:null,aquaChunks:[],aquaSpeaking:false,aquaAudio:null")
old="""rec.onstop=async()=>{this.aquaRecording=false;stream.getTracks().forEach(t=>t.stop());let form=new FormData();form.append('audio',new Blob(this.aquaChunks,{type:rec.mimeType||'audio/webm'}),'aqua.webm');this.aquaBusy=true;try{let h={},csrf=this.cookie('aquagold_csrf');if(csrf)h['X-CSRF-Token']=csrf;let response=await fetch('/api/aqua-ai/transcribe',{method:'POST',body:form,headers:h,credentials:'same-origin'}),d=await response.json();if(!response.ok)throw Error(d.error);this.aquaInput=d.text||'';if(this.aquaInput)await this.sendAqua()}catch(e){this.toast(e.message,'error')}finally{this.aquaBusy=false}};"""
new="""rec.onstop=async()=>{this.aquaRecording=false;stream.getTracks().forEach(t=>t.stop());let form=new FormData();form.append('audio',new Blob(this.aquaChunks,{type:rec.mimeType||'audio/webm'}),'aqua.webm');this.aquaBusy=true;try{let h={},csrf=this.cookie('aquagold_csrf');if(csrf)h['X-CSRF-Token']=csrf;let response=await fetch('/api/aqua-ai/transcribe',{method:'POST',body:form,headers:h,credentials:'same-origin'}),d=await response.json();if(!response.ok)throw Error(d.error);this.aquaInput=(d.text||'').trim();if(this.aquaInput)this.toast('صدای شما به متن تبدیل شد؛ برای ارسال دکمه ارسال را بزن','success')}catch(e){this.toast(e.message,'error')}finally{this.aquaBusy=false}};"""
if old not in s:
    raise SystemExit('record stop marker missing')
s=s.replace(old,new)
old="""s.speakAqua=async function(text){try{let h={'Content-Type':'application/json'},csrf=this.cookie('aquagold_csrf');if(csrf)h['X-CSRF-Token']=csrf;let r=await fetch('/api/aqua-ai/speak',{method:'POST',headers:h,credentials:'same-origin',body:JSON.stringify({text})});if(!r.ok)throw Error();let u=URL.createObjectURL(await r.blob()),a=new Audio(u);a.onended=()=>URL.revokeObjectURL(u);await a.play()}catch{if(window.speechSynthesis){speechSynthesis.cancel();let u=new SpeechSynthesisUtterance(text);u.lang='fa-IR';speechSynthesis.speak(u)}else this.toast('خروجی صوتی تنظیم نشده','error')}};"""
new="""s.speakAqua=async function(text){if(this.aquaSpeaking)return this.toast?.('آریا در حال صحبت است','info');this.aquaSpeaking=true;try{if(this.aquaAudio){try{this.aquaAudio.pause()}catch{}this.aquaAudio=null}let h={'Content-Type':'application/json'},csrf=this.cookie('aquagold_csrf');if(csrf)h['X-CSRF-Token']=csrf;let r=await fetch('/api/aqua-ai/speak',{method:'POST',headers:h,credentials:'same-origin',body:JSON.stringify({text})});if(!r.ok){let d={};try{d=await r.json()}catch{}throw Error(d.error||'صدای آریا آماده نشد')}let blob=await r.blob();if(!blob.size)throw Error('فایل صدای خالی دریافت شد');let u=URL.createObjectURL(blob),a=new Audio(u);this.aquaAudio=a;await new Promise((resolve,reject)=>{a.onended=resolve;a.onerror=()=>reject(Error('پخش صدا در مرورگر ناموفق بود'));let p=a.play();if(p?.catch)p.catch(reject)});URL.revokeObjectURL(u);this.aquaAudio=null}catch(e){console.warn('Aqua TTS fallback',e);if(window.speechSynthesis){speechSynthesis.cancel();let u=new SpeechSynthesisUtterance(text);u.lang='fa-IR';u.rate=.95;speechSynthesis.speak(u);this.toast?.('ElevenLabs موقتاً در دسترس نبود؛ از صدای فارسی دستگاه استفاده شد','info')}else this.toast?.(e.message||'خروجی صوتی تنظیم نشده','error')}finally{this.aquaSpeaking=false}};"""
if old not in s:
    raise SystemExit('speak frontend marker missing')
s=s.replace(old,new)
p.write_text(s,encoding='utf-8')

# Version/cache bust while preserving login shell version convention.
p=Path('index.html'); s=p.read_text(encoding='utf-8')
for asset in ['aqua-ai.js','ui-v4-finalize.js']:
    s=re.sub(r'(/'+re.escape(asset)+r')\?v=[^"\']+',r'\1?v=20260827-v72',s)
p.write_text(s,encoding='utf-8')

# Focused regressions.
Path('tests/test_aqua_voice_v72.py').write_text('''from pathlib import Path\nR=Path(__file__).resolve().parents[1]\ndef src(n): return (R/n).read_text(encoding="utf-8")\ndef test_today_sales_alias_is_postgres_safe():\n a=src("aqua_ai.py"); assert "::int as hour_of_day" in a and 'point["hour"] = point.pop("hour_of_day"' in a\ndef test_tts_has_retry_and_persian_fallback_model():\n a=src("aqua_ai.py"); assert "eleven_multilingual_v2" in a and "aqua_tts_failed" in a and "range(3)" in a\ndef test_voice_transcription_does_not_deadlock_send():\n j=src("aqua-ai.js"); assert "صدای شما به متن تبدیل شد" in j and "if(this.aquaInput)await this.sendAqua()" not in j\ndef test_safari_tts_is_single_flight():\n j=src("aqua-ai.js"); assert "aquaSpeaking" in j and "آریا در حال صحبت است" in j and "this.aquaAudio" in j\ndef test_v72_cache_bust():\n i=src("index.html"); assert "/aqua-ai.js?v=20260827-v72" in i\n''',encoding='utf-8')
