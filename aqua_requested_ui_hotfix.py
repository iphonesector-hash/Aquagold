"""Narrow UI adjustments requested for AquaGold dashboard and Smart Intake."""
from __future__ import annotations

import re

from flask import request

import app_v3


VOICE_SHORTCUT_RE = re.compile(
    r'<button\s+x-show="speechSupported"[^>]*@click="startVoiceIntake"[^>]*>.*?</button>',
    re.S,
)
SMART_ROWS_RE = re.compile(
    r'<div class="grid sm:grid-cols-2 gap-2"><template x-for="r in smartRows"[^>]*>.*?</template></div>',
    re.S,
)
DAILY_JOB_RE = re.compile(
    r'<template x-for="j in d\.jobs" :key="j\.id"><div class="p-4 border-b grid md:grid-cols-\[1fr_auto\] gap-2".*?</div></div></template>',
    re.S,
)

DASHBOARD_SUB = (
    '<p class="aqua-hero-sub">مدیریت یکپارچه مشتری، سرویس، فروش و گزارش مالی؛ سریع، دقیق و همیشه در دسترس.</p>'
)
DASHBOARD_CLOCK = r'''
      <div id="aqua-dashboard-clock" class="mt-4 mx-auto max-w-xl rounded-2xl border border-cyan-300/20 bg-slate-950/30 px-4 py-3 backdrop-blur-sm">
        <div id="aqua-jalali-clock" class="text-sm md:text-base font-black text-cyan-50"></div>
        <div id="aqua-gregorian-clock" class="text-xs mt-1 text-cyan-100/70"></div>
      </div>'''

SMART_EDITOR = r'''
<div>
  <div class="flex items-center justify-between gap-2 mb-3">
    <div><b class="text-sm">ویرایش دستی قبل از ثبت نهایی</b><div class="text-xs muted mt-1">هر موردی اشتباه است همین‌جا اصلاح کن؛ ثبت نهایی از همین اطلاعات ویرایش‌شده انجام می‌شود.</div></div>
    <span class="chip bg-violet-500/10 text-violet-300" x-text="parserLabel(smartParsed.parser)"></span>
  </div>
  <div class="grid sm:grid-cols-2 gap-3">
    <label class="text-xs muted">نام<input x-model="smartParsed.first_name" class="field mt-1" placeholder="نام"></label>
    <label class="text-xs muted">نام خانوادگی<input x-model="smartParsed.last_name" class="field mt-1" placeholder="نام خانوادگی"></label>
    <label class="text-xs muted">شماره اول<input :value="(smartParsed.phones||[])[0]||''" @input="smartParsed.phones=smartParsed.phones||[];smartParsed.phones[0]=$event.target.value" class="field mt-1" inputmode="tel" placeholder="09..."></label>
    <label class="text-xs muted">شماره دوم<input :value="(smartParsed.phones||[])[1]||''" @input="smartParsed.phones=smartParsed.phones||[];smartParsed.phones[1]=$event.target.value" class="field mt-1" inputmode="tel" placeholder="اختیاری"></label>
    <label class="text-xs muted sm:col-span-2">آدرس<input x-model="smartParsed.address" class="field mt-1" placeholder="آدرس"></label>
    <label class="text-xs muted">نوع سرویس<select x-model="smartParsed.service_type" class="field mt-1"><option value="">انتخاب نوع سرویس</option><option value="ساید">ساید</option><option value="فیلتر دستگاه">فیلتر دستگاه</option><option value="نصب">نصب</option><option value="سرویس">سرویس</option><option value="دیگر">دیگر</option></select></label>
    <label class="text-xs muted">ویزیتور<input x-model="smartParsed.visitor_code" class="field mt-1" placeholder="کد/نام ویزیتور"></label>
    <label class="text-xs muted">زمان سرویس<input x-model="smartParsed.time_text" class="field mt-1" placeholder="مثلاً امروز ساعت ۱۲"></label>
    <label class="text-xs muted">مبلغ (تومان)<input x-model="smartParsed.amount" class="field mt-1" inputmode="numeric" placeholder="مبلغ"></label>
    <label class="text-xs muted">روش پرداخت<select x-model="smartParsed.payment_method" class="field mt-1"><option value="">انتخاب روش پرداخت</option><option value="cash">نقد</option><option value="transfer">کارت‌به‌کارت</option><option value="card">کارتخوان</option><option value="cheque">چک</option><option value="credit">نسیه</option><option value="other">سایر</option></select></label>
    <label class="text-xs muted">یادداشت<input x-model="smartParsed.notes" class="field mt-1" placeholder="یادداشت"></label>
    <label class="text-xs muted sm:col-span-2">شرح<textarea x-model="smartParsed.description" class="field mt-1 min-h-24" placeholder="شرح سرویس"></textarea></label>
  </div>
</div>'''

DAILY_JOB = r'''<template x-for="j in d.jobs" :key="j.id"><div class="p-4 border-b flex items-center justify-between gap-3" style="border-color:var(--line)"><div class="min-w-0"><b x-text="j.name"></b><div class="text-xs muted mt-1" x-text="j.description||j.service_type||'سرویس'"></div></div><div class="flex items-center gap-2 shrink-0"><b x-text="money(j.received_amount)+' تومان'"></b><button type="button" @click="openServiceEdit(j)" class="btn soft !py-1.5 !px-3 no-print">ویرایش</button></div></div></template>'''

UI_SCRIPT = r'''
(()=>{
  const updateClock=()=>{
    const jalali=document.getElementById('aqua-jalali-clock');
    const gregorian=document.getElementById('aqua-gregorian-clock');
    if(!jalali||!gregorian)return;
    const now=new Date();
    const dateOptions={timeZone:'Asia/Tehran',weekday:'long',day:'numeric',month:'long',year:'numeric'};
    const time=new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit',hour12:false}).format(now);
    const jalaliDate=new Intl.DateTimeFormat('fa-IR-u-ca-persian',dateOptions).format(now).replace(/[،,]\s*$/,'');
    const gregorianDate=new Intl.DateTimeFormat('fa-IR-u-ca-gregory',dateOptions).format(now).replace(/[،,]\s*$/,'');
    jalali.textContent=`${jalaliDate} ساعت ${time}`;
    gregorian.textContent=`میلادی: ${gregorianDate} ساعت ${time}`;
  };
  const removeBottomUtilities=()=>{
    document.querySelectorAll('.bottom-nav button').forEach(button=>{
      const label=[button.getAttribute('aria-label'),button.getAttribute('title'),button.textContent].filter(Boolean).join(' ');
      if(/جست|اعلان|نوتیف|search|notification/i.test(label))button.remove();
    });
  };
  const forceFreshLoader=()=>{
    const image=document.querySelector('#aqua-boot-20260906 img');
    if(image&&!image.src.includes('aqua-loader-exact-3'))image.src='/assets/aquagold-loading-v20260906b.jpg?aqua-loader-exact-3';
  };
  updateClock();removeBottomUtilities();forceFreshLoader();
  setInterval(updateClock,30000);
  const observer=new MutationObserver(()=>{removeBottomUtilities();forceFreshLoader()});
  observer.observe(document.documentElement,{childList:true,subtree:true});
})();
'''


def _patch_voice_script(body: str) -> str:
    # iOS can consume the first user gesture while unlocking audio. Prime the
    # audio context before requesting the microphone so the very first tap can
    # continue directly into MediaRecorder after permission is granted.
    needle = "const mediaPromise=navigator.mediaDevices.getUserMedia({audio:true}).then(value=>{"
    if needle in body and "aqua-first-tap-prime" not in body:
        body = body.replace(
            needle,
            "/* aqua-first-tap-prime */try{await this.primeAquaAudio?.()}catch{}\n        const mediaPromise=navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}}).then(value=>{",
            1,
        )
        body = body.replace("\n        try{await this.primeAquaAudio?.()}catch{}\n        const mime=pickMime();", "\n        const mime=pickMime();", 1)
    return body


@app_v3.app.after_request
def apply_requested_ui_hotfix(response):
    try:
        if request.path == "/aqua-round6-user-fixes.js" and response.mimetype == "application/javascript":
            response.direct_passthrough = False
            body = _patch_voice_script(response.get_data(as_text=True))
            response.set_data(body)
            response.headers["Cache-Control"] = "no-store, max-age=0"
            return response

        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        body = VOICE_SHORTCUT_RE.sub("", body, count=1)
        if 'id="aqua-dashboard-clock"' not in body and DASHBOARD_SUB in body:
            body = body.replace(DASHBOARD_SUB, DASHBOARD_SUB + DASHBOARD_CLOCK, 1)
        body = SMART_ROWS_RE.sub(SMART_EDITOR, body, count=1)
        body = DAILY_JOB_RE.sub(DAILY_JOB, body, count=1)
        if 'id="aqua-requested-ui-hotfix"' not in body:
            body = body.replace("</body>", f'<script id="aqua-requested-ui-hotfix">{UI_SCRIPT}</script></body>', 1)
        response.set_data(body)
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_requested_ui_hotfix_failed: %s", exc)
    return response