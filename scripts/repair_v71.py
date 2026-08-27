from pathlib import Path
import re

# Bale done -> Smart Intake
p=Path('bale-ui.js'); s=p.read_text(encoding='utf-8')
s=s.replace("baleCompleteJob:null,baleCompleteAmount:'',baleCancelJob:null", "baleCompleteJob:null,baleCompleteAmount:'',baleSmartJob:null,baleCancelJob:null")
old="  s.openBaleComplete=function(job){this.baleCompleteJob=job;this.baleCompleteAmount='';setTimeout(()=>document.getElementById('baleAmountInput')?.focus(),80)};"
new="  s.sendBaleToSmart=async function(job){this.baleSmartJob=job;this.smartText=String(job?.raw_text||'').trim();this.smartParsed=null;this.smartGps={};this.smartSuggestions=[];this.smartCustomerId=job?.customer_id||'';await this.go('smart');setTimeout(()=>this.analyzeSmart?.(),80);this.toast?.('متن کار بله وارد ثبت هوشمند شد؛ GPS و اطلاعات را بررسی و ثبت نهایی کن','success')};"
if old not in s:
    raise SystemExit('openBaleComplete marker not found')
s=s.replace(old,new)
s=s.replace('@click="openBaleComplete(j)">✓ انجام شد</button>', '@click="sendBaleToSmart(j)">✓ انجام شد → ثبت هوشمند</button>')
hook="  const oldGo=s.go?.bind(s);"
wrapper="""  const oldSmartRegister=s.registerSmart?.bind(s);
  s.registerSmart=async function(){
   const pending=this.baleSmartJob;
   await oldSmartRegister?.();
   if(pending && !this.smartText && !this.smartParsed){
    try{await this.api('/bale/jobs/'+pending.id+'/finalize',{method:'POST',body:'{}'});this.baleSmartJob=null;await Promise.all([this.loadBaleCounts?.(),this.loadBaleJobs?.('new')]);this.toast?.('کار بله از طریق ثبت هوشمند وارد سرویس‌های اصلی شد','success')}catch(e){this.toast?.(e.message||'سرویس ثبت شد ولی اتصال کار بله کامل نشد','error')}
   }
  };
"""
if 'const oldSmartRegister=s.registerSmart?.bind(s);' not in s:
    if hook not in s:
        raise SystemExit('oldGo hook missing')
    s=s.replace(hook,wrapper+hook)
p.write_text(s,encoding='utf-8')

# Backend link endpoint
p=Path('bale_bridge.py'); s=p.read_text(encoding='utf-8')
marker='@app_v3.app.post("/api/bale/jobs/<job_id>/cancel")'
endpoint='''@app_v3.app.post("/api/bale/jobs/<job_id>/finalize")
@app_v3.roles_required("technician")
def bale_job_finalize(job_id):
    with app_v3.get_db() as db, db.cursor() as cur:
        job = _get_locked_job(cur, job_id)
        cur.execute(
            """select id,customer_id,received_amount from service_visits
               where raw_chat_input=%s and registered_by=%s
                 and created_at>=now()-interval '20 minutes'
               order by created_at desc limit 1""",
            (job.get("raw_text"), str(request.current_user.get("user_id"))),
        )
        service = cur.fetchone()
        if not service:
            raise ValidationError("ثبت هوشمند این کار پیدا نشد؛ ابتدا ثبت نهایی را انجام بده")
        cur.execute(
            """update bale_jobs set status='completed',customer_id=%s,service_visit_id=%s,
               received_amount=%s,completed_at=now(),updated_at=now() where id=%s::uuid""",
            (service["customer_id"], service["id"], service["received_amount"], job_id),
        )
        app_v3.audit(cur, "bale_job", job_id, "smart_finalize", before={"status": job["status"]}, after={"service_visit_id": str(service["id"])})
    settings = _load_settings()
    _send_chat(settings, job["chat_id"], "✅ کار از طریق ثبت هوشمند AquaGold انجام و وارد سرویس‌های اصلی شد", job["message_id"])
    return jsonify({"ok": True, "service_visit_id": str(service["id"]), "customer_id": str(service["customer_id"])})


'''
if 'def bale_job_finalize(job_id):' not in s:
    if marker not in s:
        raise SystemExit('cancel endpoint marker missing')
    s=s.replace(marker,endpoint+marker)
p.write_text(s,encoding='utf-8')

# AI settings feedback
p=Path('aqua-ai.js'); s=p.read_text(encoding='utf-8')
s=s.replace("aquaKeys:{groq_api_key:'',elevenlabs_api_key:''}", "aquaKeys:{groq_api_key:'',elevenlabs_api_key:''},aquaSettingsSaved:false")
old="s.saveAquaSettings=async function(){try{let p={...this.aquaSettings};for(let k of ['groq_api_key','elevenlabs_api_key'])if(this.aquaKeys[k])p[k]=this.aquaKeys[k];this.aquaSettings=await this.api('/aqua-ai/settings',{method:'PATCH',body:JSON.stringify(p)});this.aquaKeys={groq_api_key:'',elevenlabs_api_key:''};this.toast('کلیدهای آکوا ذخیره شد','success')}catch(e){this.toast(e.message,'error')}};"
new="s.saveAquaSettings=async function(){try{let p={...this.aquaSettings};for(let k of ['groq_api_key','elevenlabs_api_key'])if(this.aquaKeys[k])p[k]=this.aquaKeys[k];let saved=await this.api('/aqua-ai/settings',{method:'PATCH',body:JSON.stringify(p)});this.aquaSettings={...this.aquaSettings,...saved};this.aquaKeys={groq_api_key:'',elevenlabs_api_key:''};this.aquaSettingsSaved=true;setTimeout(()=>this.aquaSettingsSaved=false,4000);this.toast('تنظیمات آکوا با موفقیت ذخیره شد','success')}catch(e){this.aquaSettingsSaved=false;this.toast(e.message,'error')}};"
if old not in s:
    raise SystemExit('saveAquaSettings marker not found')
s=s.replace(old,new)
s=s.replace('<button @click="saveAquaSettings" class="btn primary w-full mt-4">ذخیره تنظیمات آکوا</button>', '<button @click="saveAquaSettings" class="btn primary w-full mt-4">ذخیره تنظیمات آکوا</button><div x-show="aquaSettingsSaved" class="mt-3 rounded-2xl p-3 bg-emerald-500/10 text-emerald-500 text-sm font-bold">✓ تنظیمات روی سرور ذخیره شد. خالی شدن فیلد کلیدها طبیعی است؛ برای امنیت مقدار کامل دوباره نمایش داده نمی‌شود.</div>')
p.write_text(s,encoding='utf-8')

# One-time DB bootstrap consumer for secrets
p=Path('aqua_ai.py'); s=p.read_text(encoding='utf-8')
marker='def _public_settings(settings):'
consumer='''def _consume_secret_bootstrap():
    try:
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("select value from app_settings where key='aqua_ai_bootstrap' for update")
            row = cur.fetchone()
            payload = dict((row or {}).get("value") or {})
            if not payload:
                return False
            current = _load_settings(cur)
            for key in SECRET_FIELDS:
                encoded = str(payload.get(key) or "")
                if encoded:
                    current[key] = base64.b64decode(encoded.encode()).decode()
            if payload.get("voice_id"):
                current["voice_id"] = str(payload["voice_id"])
            stored = {key: current[key] for key in SAFE_FIELDS}
            for key in SECRET_FIELDS:
                stored[f"{key}_cipher"] = _encrypt(current.get(key, "")) if current.get(key) else ""
            cur.execute("insert into app_settings(key,value,updated_at) values('aqua_ai',%s,now()) on conflict(key) do update set value=excluded.value,updated_at=now()", (app_v3.Jsonb(stored),))
            cur.execute("delete from app_settings where key='aqua_ai_bootstrap'")
        return True
    except Exception as exc:
        app_v3.logger.warning("aqua_ai_bootstrap_failed: %s", exc)
        return False


'''
if 'def _consume_secret_bootstrap():' not in s:
    if marker not in s:
        raise SystemExit('public settings marker missing')
    s=s.replace(marker,consumer+marker)
call='def configuration_status():'
if '_consume_secret_bootstrap()\n\ndef configuration_status' not in s:
    s=s.replace(call,'_consume_secret_bootstrap()\n\n'+call)
p.write_text(s,encoding='utf-8')

# Version/cache bust
p=Path('index.html'); s=p.read_text(encoding='utf-8')
s=re.sub(r'<title>AquaGold CRM v[^<]+</title>','<title>AquaGold CRM v7.1</title>',s)
s=re.sub(r'نسخه v\d+(?:\.\d+)?','نسخه v7.1',s)
for asset in ['bale-ui.js','aqua-ai.js','ui-v4-finalize.js']:
    s=re.sub(r'(/'+re.escape(asset)+r')\?v=[^"\']+',r'\1?v=20260827-v71',s)
p.write_text(s,encoding='utf-8')

Path('tests/test_bale_smart_v71.py').write_text('''from pathlib import Path\nR=Path(__file__).resolve().parents[1]\ndef src(n): return (R/n).read_text(encoding="utf-8")\ndef test_bale_done_routes_to_smart():\n b=src("bale-ui.js"); assert "sendBaleToSmart" in b and "انجام شد → ثبت هوشمند" in b and "oldSmartRegister" in b\ndef test_bale_finalize_links_existing_smart_service():\n b=src("bale_bridge.py"); assert "/api/bale/jobs/<job_id>/finalize" in b and "raw_chat_input=%s" in b and "smart_finalize" in b\ndef test_ai_settings_saved_feedback():\n a=src("aqua-ai.js"); assert "aquaSettingsSaved" in a and "خالی شدن فیلد کلیدها طبیعی است" in a\ndef test_v71_assets():\n i=src("index.html"); assert "AquaGold CRM v7.1" in i and "/bale-ui.js?v=20260827-v71" in i and "/aqua-ai.js?v=20260827-v71" in i\n''',encoding='utf-8')
