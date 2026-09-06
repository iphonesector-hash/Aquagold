"""Final isolated-branch fixes for AquaGold QA.

Scope is deliberately narrow:
- recover from unavailable saved Groq models and force real web search for live queries;
- normalize the dashboard Jalali clock wording without touching auth/navigation;
- constrain dashboard operation cards so they cannot overflow on iPhone;
- expose a user-scoped Web Push test endpoint and a small settings panel.
"""
from __future__ import annotations

import json

from flask import Response, jsonify, request

import app_v3
import aqua_ai
import aqua_push_runtime


# ---------------------------------------------------------------------------
# Aqua AI: live web + stale/unavailable model recovery
# ---------------------------------------------------------------------------
_PREVIOUS_GROQ_ANSWER = aqua_ai._groq_answer
_MODEL_ERROR_MARKERS = (
    "model_not_found",
    "does not exist",
    "do not have access",
    "you do not have access",
    "model does not exist",
)
_LEGACY_OR_RESTRICTED_MODELS = {"llama-3.3-70b-versatile"}


def _groq_headers(settings):
    key = str((settings or {}).get("groq_api_key") or "").strip()
    if not key:
        raise RuntimeError("کلید Groq تنظیم نشده است؛ از تنظیمات هوش آکوا کلید را بررسی کن.")
    return {"Authorization": f"Bearer {key}"}


def _live_web_answer(settings, text):
    headers = _groq_headers(settings)
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    messages = [
        {
            "role": "system",
            "content": (
                "تو آریا، دستیار فارسی AquaGold هستی. این درخواست به اطلاعات لحظه‌ای وب نیاز دارد. "
                "حتماً جست‌وجوی واقعی وب انجام بده و هیچ قیمت یا خبر روزی را حدس نزن. "
                "برای بازار ایران نوع دارایی، واحد، زمان تقریبی و اختلاف منابع را کوتاه و روشن بگو. "
                "پاسخ فارسی، کوتاه و دقیق باشد."
            ),
        },
        {"role": "user", "content": str(text or "")[:1400]},
    ]
    attempts = [
        {
            "model": "groq/compound",
            "messages": messages,
            "temperature": 0.2,
            "compound_custom": {"tools": {"enabled_tools": ["web_search"]}},
        },
        {
            "model": "groq/compound-mini",
            "messages": messages,
            "temperature": 0.2,
            "compound_custom": {"tools": {"enabled_tools": ["web_search"]}},
        },
        {
            "model": "openai/gpt-oss-120b",
            "messages": messages,
            "temperature": 0.2,
            "max_completion_tokens": 1400,
            "tools": [{"type": "browser_search"}],
        },
    ]
    last_error = None
    for payload in attempts:
        try:
            data = aqua_ai._post_json(endpoint, payload, headers, timeout=60)
            answer = str(data["choices"][0]["message"]["content"] or "").strip()
            if answer:
                return answer
            raise RuntimeError("live search returned an empty answer")
        except (KeyError, IndexError, TypeError, RuntimeError) as exc:
            last_error = exc
            app_v3.logger.warning(
                "aqua_branch_live_search_failed model=%s detail=%s",
                payload.get("model"),
                str(exc)[:300],
            )
    raise RuntimeError("جست‌وجوی زنده آکوا پاسخ نداد؛ اتصال Groq یا دسترسی مدل‌های Web Search را بررسی کن.") from last_error


def _fixed_groq_answer(settings, text, history, context):
    effective = dict(settings or {})
    configured = str(effective.get("brain_model") or "").strip()
    if not configured or configured in _LEGACY_OR_RESTRICTED_MODELS:
        effective["brain_model"] = "groq/compound"

    if aqua_ai._needs_live_web_search(text):
        return _live_web_answer(effective, text)

    try:
        return _PREVIOUS_GROQ_ANSWER(effective, text, history, context)
    except RuntimeError as exc:
        detail = str(exc).lower()
        if not any(marker in detail for marker in _MODEL_ERROR_MARKERS):
            raise
        app_v3.logger.warning(
            "aqua_branch_model_recovery configured=%s detail=%s",
            configured,
            str(exc)[:300],
        )
        for fallback in ("groq/compound", "groq/compound-mini", "openai/gpt-oss-120b"):
            try:
                rescue = dict(effective)
                rescue["brain_model"] = fallback
                return _PREVIOUS_GROQ_ANSWER(rescue, text, history, context)
            except RuntimeError as retry_exc:
                last_error = retry_exc
                app_v3.logger.warning(
                    "aqua_branch_model_recovery_failed model=%s detail=%s",
                    fallback,
                    str(retry_exc)[:240],
                )
        raise RuntimeError("مدل ذخیره‌شده آکوا در دسترس نیست و مدل جایگزین هم پاسخ نداد.") from last_error


aqua_ai._groq_answer = _fixed_groq_answer


# ---------------------------------------------------------------------------
# User-scoped push test. Actual Bale pushes remain handled by aqua_push_runtime.
# ---------------------------------------------------------------------------
@app_v3.app.post("/api/push/test")
@app_v3.roles_required("technician")
def aqua_push_test():
    aqua_push_runtime._schema()
    user_id = request.current_user.get("user_id")
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            "select id,endpoint,p256dh,auth from push_subscriptions where active=true and user_id=%s",
            (user_id,),
        )
        rows = [dict(row) for row in cur.fetchall()]
    if not rows:
        return jsonify({"error": "برای این گوشی اشتراک Push فعالی ثبت نشده؛ اول اعلان را فعال کن."}), 409

    payload = json.dumps(
        {
            "title": "AquaGold",
            "body": "اعلان تست با موفقیت ارسال شد. اگر برنامه بسته باشد هم باید این پیام را ببینی.",
            "url": "/?open=dashboard",
            "tag": "aquagold-push-test",
        },
        ensure_ascii=False,
    )
    sent = failed = 0
    for sub in rows:
        try:
            aqua_push_runtime.webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=payload,
                vapid_private_key=aqua_push_runtime._private(),
                vapid_claims={"sub": aqua_push_runtime.SUBJECT},
                timeout=8,
            )
            sent += 1
            with app_v3.get_db() as db, db.cursor() as cur:
                cur.execute(
                    "update push_subscriptions set last_success_at=now(),last_error=null,updated_at=now() where id=%s",
                    (sub["id"],),
                )
        except aqua_push_runtime.WebPushException as exc:
            failed += 1
            status = getattr(getattr(exc, "response", None), "status_code", None)
            with app_v3.get_db() as db, db.cursor() as cur:
                if status in {404, 410}:
                    cur.execute(
                        "update push_subscriptions set active=false,last_error=%s,updated_at=now() where id=%s",
                        (f"expired:{status}", sub["id"]),
                    )
                else:
                    cur.execute(
                        "update push_subscriptions set last_error=%s,updated_at=now() where id=%s",
                        (str(exc)[:500], sub["id"]),
                    )
        except Exception as exc:
            failed += 1
            app_v3.logger.warning("aqua_push_test_failed detail=%s", str(exc)[:300])

    code = 200 if sent else 502
    return jsonify({"ok": sent > 0, "sent": sent, "failed": failed}), code


# ---------------------------------------------------------------------------
# Branch-only UI layer
# ---------------------------------------------------------------------------
PUSH_CARD = r'''
<div id="aqua-ios-push-card" class="card p-5" x-init="refreshPushStatus()">
  <div class="flex items-center justify-between gap-3 flex-wrap">
    <div>
      <h2 class="section-title">اعلان آیفون</h2>
      <p class="text-sm muted mt-1">دریافت Push حتی وقتی AquaGold بسته است.</p>
    </div>
    <span class="chip" :class="pushActive?'bg-emerald-500/10 text-emerald-300':'bg-slate-500/10 text-slate-300'" x-text="pushActive?'فعال روی این گوشی':'غیرفعال'"></span>
  </div>
  <div class="mt-3 rounded-2xl border border-cyan-300/15 bg-cyan-400/5 p-3 text-xs leading-6 text-cyan-50/80" x-text="aquaPushHint()"></div>
  <div class="grid sm:grid-cols-3 gap-2 mt-4">
    <button type="button" class="btn primary" @click="enableAquaPush()" :disabled="pushBusy" x-text="pushBusy?'لطفاً صبر کن…':'فعال‌سازی اعلان'"></button>
    <button type="button" class="btn soft" @click="testAquaPush()" :disabled="pushBusy||!pushActive">ارسال اعلان تست</button>
    <button type="button" class="btn" @click="disableAquaPush()" :disabled="pushBusy||!pushActive">غیرفعال‌سازی</button>
  </div>
</div>'''

BRANCH_UI_JS = r'''
(()=>{
 const previous=window.app;
 if(typeof previous==='function'){
  window.app=function(){
   const state=previous();
   state.aquaPushHint=function(){
    const ios=/iPhone|iPad|iPod/i.test(navigator.userAgent);
    const standalone=(window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches)||navigator.standalone===true;
    if(ios&&!standalone)return 'برای Push پس‌زمینه در آیفون، AquaGold را در Safari باز کن، Share را بزن و Add to Home Screen را انتخاب کن؛ سپس برنامه را از آیکون Home Screen باز کن و «فعال‌سازی اعلان» را بزن.';
    if(ios)return 'نسخه Home Screen شناسایی شد. بعد از فعال‌سازی، اعلان‌های Push حتی وقتی برنامه بسته است توسط iOS نمایش داده می‌شوند.';
    return 'بعد از فعال‌سازی، مرورگر این دستگاه می‌تواند Pushهای AquaGold را در پس‌زمینه دریافت کند.';
   };
   state.testAquaPush=async function(){
    const tell=(message,type='info')=>this.toast?this.toast(message,type):alert(message);
    if(!navigator.onLine)return tell('برای تست اعلان باید اینترنت وصل باشد','error');
    if(!this.pushActive)return tell('اول اعلان این گوشی را فعال کن','error');
    if(this.pushBusy)return;
    this.pushBusy=true;
    try{
     const result=await this.api('/push/test',{method:'POST',body:'{}'});
     if(Number(result?.sent||0)>0)tell('اعلان تست ارسال شد؛ AquaGold را ببند و Notification Center را هم بررسی کن','success');
     else tell('اعلان تست ارسال نشد','error');
    }catch(error){tell(error?.message||'ارسال اعلان تست انجام نشد','error')}
    finally{this.pushBusy=false}
   };
   return state;
  };
 }

 const faClockParts=(calendar,now)=>{
  const options={timeZone:'Asia/Tehran',weekday:'long',day:'numeric',month:'long',year:'numeric'};
  const map={};
  new Intl.DateTimeFormat(`fa-IR-u-ca-${calendar}`,options).formatToParts(now).forEach(part=>{if(part.type!=='literal')map[part.type]=part.value});
  const weekday=String(map.weekday||'').replace(/\u200c/g,' ');
  return [weekday,map.day,map.month,map.year].filter(Boolean).join(' ');
 };
 const fixClock=()=>{
  const jalali=document.getElementById('aqua-jalali-clock');
  const gregorian=document.getElementById('aqua-gregorian-clock');
  if(!jalali)return;
  const now=new Date();
  const time=new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit',hour12:false}).format(now);
  const wanted=`${faClockParts('persian',now)} ساعت ${time}`;
  if(jalali.textContent!==wanted)jalali.textContent=wanted;
  if(gregorian){
   const g=`میلادی: ${faClockParts('gregory',now)} ساعت ${time}`;
   if(gregorian.textContent!==g)gregorian.textContent=g;
  }
 };
 const mountFixes=()=>{
  const style=document.createElement('style');
  style.id='aqua-branch-final-layout';
  style.textContent=`
   .aqua-ops{width:100%!important;max-width:100%!important;grid-template-columns:minmax(0,1.4fr) minmax(0,.6fr)!important;align-items:start!important}
   .aqua-ops>*{min-width:0!important;max-width:100%!important}
   .aqua-ops .card,.aqua-ops .space-y-4{min-width:0!important;max-width:100%!important}
   .aqua-alert{grid-template-columns:40px minmax(0,1fr) auto!important;min-width:0!important;max-width:100%!important}
   .aqua-alert>*{min-width:0!important}
   .aqua-quickbar-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
   .aqua-mini-action{min-width:0!important;max-width:100%!important;overflow:hidden!important}
   .aqua-mini-action span:last-child{min-width:0!important;overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important}
   .aqua-ops>.card>.flex:first-child,.aqua-alerts>.flex:first-child,.aqua-quickbar>.flex:first-child{flex-wrap:wrap!important;row-gap:8px!important}
   #aqua-ios-push-card{overflow:hidden!important}
   @media(max-width:1023px){.aqua-ops{grid-template-columns:minmax(0,1fr)!important}}
   @media(max-width:520px){.aqua-ops{gap:12px!important}.aqua-alerts,.aqua-quickbar{padding:15px!important}.aqua-alert{grid-template-columns:36px minmax(0,1fr) auto!important}.aqua-quickbar-grid{gap:7px!important}}
  `;
  if(!document.getElementById(style.id))document.head.appendChild(style);
  fixClock();
  const clocks=[document.getElementById('aqua-jalali-clock'),document.getElementById('aqua-gregorian-clock')].filter(Boolean);
  if(clocks.length){
   const observer=new MutationObserver(()=>fixClock());
   clocks.forEach(node=>observer.observe(node,{childList:true,characterData:true,subtree:true}));
  }
  setInterval(fixClock,10000);
 };
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mountFixes,{once:true});else mountFixes();
})();
'''


@app_v3.app.get("/aqua-branch-final.js")
def aqua_branch_final_js():
    return Response(BRANCH_UI_JS, mimetype="application/javascript", headers={"Cache-Control": "no-store, max-age=0"})


@app_v3.app.after_request
def inject_aqua_branch_final(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        settings_open = '<section x-show="page===\'settings\'" class="max-w-3xl mx-auto space-y-4">'
        if 'id="aqua-ios-push-card"' not in body and settings_open in body:
            body = body.replace(settings_open, settings_open + PUSH_CARD, 1)
        if '/aqua-branch-final.js?' not in body:
            pos = body.lower().find("</head>")
            if pos >= 0:
                tag = '<script src="/aqua-branch-final.js?v=20260901-1"></script>'
                body = body[:pos] + tag + body[pos:]
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_branch_final_inject_failed detail=%s", str(exc)[:300])
    return response
