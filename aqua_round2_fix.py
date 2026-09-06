"""Second isolated AquaGold QA layer.

Narrow scope:
- remove the retired Llama fallback while preserving a healthy configured chat model;
- recognise Persian live-search wording/typos such as «دولار» and internet capability questions;
- route live requests through Groq Compound Web Search with a bounded retry;
- inject the branch-only UI repair script for Bale inbox, red map pins, fixed charts and iPhone Push access.
"""
from __future__ import annotations

import json
import re
import time

from flask import request

import app_v3
import aqua_ai


FA_NORMALISE = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})
LIVE_ASSETS = (
    "دلار", "دولار", "دالر", "طلا", "طلای", "سکه", "ارز", "یورو", "درهم",
    "بیت کوین", "بیت‌کوین", "بورس", "تتر", "نفت", "قیمت",
)
LIVE_MARKERS = (
    "قیمت", "نرخ", "امروز", "الان", "لحظه", "لحظه ای", "لحظه‌ای", "جدیدترین",
    "آخرین", "چند", "چنده", "چقدره", "جستجو", "جست و جو", "جست‌وجو", "سرچ",
    "در وب", "وب", "آنلاین", "اینترنت", "خبر",
)
LIVE_WEATHER = (
    "آب و هوا", "آب‌وهوا", "هواشناسی", "وضعیت هوا", "دمای هوا", "هوای امروز", "آب و هوای",
)
LIVE_NEWS = (
    "خبرها", "اخبار", "آخرین خبر", "خبر فوری",
)
CAPABILITY_MARKERS = (
    "به اینترنت دسترسی داری", "اینترنت داری", "به وب دسترسی داری", "وب داری",
    "میتونی سرچ کنی", "می تونی سرچ کنی", "میتونی جستجو کنی", "می تونی جستجو کنی",
)
RETIRED_MODELS = {"llama-3.3-70b-versatile"}
MODEL_ERROR_MARKERS = ("model_not_found", "does not exist", "do not have access", "you do not have access")


def _norm(value):
    text = str(value or "").translate(FA_NORMALISE).replace("\u200c", " ").lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("دولار", "دلار").replace("دالر", "دلار")


def _capability_question(text):
    value = _norm(text)
    return any(marker in value for marker in CAPABILITY_MARKERS)


def _is_weather_query(text):
    value = _norm(text)
    if any(topic in value for topic in LIVE_WEATHER) or "اب و هوا" in value:
        return True
    if re.search(r"هوای\s+\S+", value):
        return True
    return "هوا" in value and any(city in value for city in ("تهران", "امروز", "الان"))


def _needs_live_web_search(text):
    value = _norm(text)
    if _capability_question(value):
        return False
    explicit = any(marker in value for marker in ("جستجو", "جست و جو", "جست‌وجو", "سرچ", "در وب", "آنلاین", "اینترنت"))
    market = any(asset in value for asset in LIVE_ASSETS) and any(marker in value for marker in LIVE_MARKERS)
    weather = _is_weather_query(value)
    news = any(topic in value for topic in LIVE_NEWS)
    return explicit or market or weather or news


aqua_ai._needs_live_web_search = _needs_live_web_search


def _headers(settings):
    key = str((settings or {}).get("groq_api_key") or "").strip()
    if not key:
        raise RuntimeError("کلید Groq تنظیم نشده است؛ از تنظیمات هوش آکوا آن را بررسی کن.")
    return {"Authorization": f"Bearer {key}", "Groq-Model-Version": "latest"}


def _context_summary(context):
    data = context or {}
    return {
        "customers": int(data.get("customers") or 0),
        "products": int(data.get("products") or 0),
        "services": int(data.get("services") or 0),
        "today_services": int(data.get("today_services") or 0),
        "today_sales": int(data.get("today_sales") or 0),
        "today_received": int(data.get("today_received") or 0),
    }


def _messages(text, history, context, *, live=False):
    system = (
        "تو آریا، دستیار فارسی AquaGold هستی. فارسی تهرانی، کوتاه، طبیعی و دقیق جواب بده. "
        "تو در AquaGold برای اطلاعات لحظه‌ای به جست‌وجوی واقعی وب از طریق Groq Compound دسترسی داری؛ هرگز نگو اینترنت یا وب در دسترس نیست. "
        "اگر سؤال به اطلاعات روز یا قیمت لحظه‌ای مربوط است فقط پس از جست‌وجوی واقعی جواب بده و چیزی را حدس نزن. "
        "تغییر اطلاعات CRM را بدون تأیید کاربر انجام‌شده فرض نکن. "
        "وضعیت برنامه: " + json.dumps(_context_summary(context), ensure_ascii=False)
    )
    if live:
        system += (
            " این درخواست حتماً لحظه‌ای است: از web_search استفاده کن. برای بازار ایران نوع دارایی، واحد، زمان و در صورت اختلاف منابع بازه را روشن بگو."
        )
    messages = [{"role": "system", "content": system}]
    for item in (history or [])[-3:]:
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()[:650]
        if content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": str(text or "")[:1400]})
    return messages


def _groq_call(settings, model, messages, *, live=False, timeout=24):
    payload = {"model": model, "messages": messages, "temperature": 0.2}
    if live:
        payload["compound_custom"] = {"tools": {"enabled_tools": ["web_search"]}}
    data = aqua_ai._post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        payload,
        _headers(settings),
        timeout=timeout,
    )
    message = data["choices"][0]["message"]
    answer = str(message.get("content") or "").strip()
    if not answer:
        raise RuntimeError("پاسخ آریا خالی بود")
    return answer


def _is_model_error(exc):
    detail = str(exc).lower()
    return any(marker in detail for marker in MODEL_ERROR_MARKERS)


def _fast_groq_answer(settings, text, history, context):
    started = time.monotonic()
    try:
        if _capability_question(text):
            if not str((settings or {}).get("groq_api_key") or "").strip():
                return "کلید Groq تنظیم نشده، پس جست‌وجوی وب فعلاً فعال نیست."
            return "آره. من داخل AquaGold برای اطلاعات لحظه‌ای به Web Search واقعی وصل می‌شم؛ مثلاً قیمت دلار، طلا، خبر یا اطلاعات روز رو از وب جست‌وجو می‌کنم."

        live = _needs_live_web_search(text) or _is_weather_query(text)
        messages = _messages(text, history, context, live=live)
        if live:
            # Keep the established, tested route: full Compound first for the most
            # capable search synthesis, then a bounded Compound Mini retry.
            attempts = (("groq/compound", 20), ("groq/compound-mini", 20))
        else:
            configured = str((settings or {}).get("brain_model") or "").strip()
            primary = "groq/compound-mini" if not configured or configured in RETIRED_MODELS else configured
            attempts = ((primary, 20),)
            if primary not in {"groq/compound-mini", "groq/compound"}:
                attempts += (("groq/compound-mini", 20),)
            if "groq/compound" not in {model for model, _ in attempts}:
                attempts += (("groq/compound", 24),)

        last_error = None
        for index, (model, timeout) in enumerate(attempts):
            try:
                return _groq_call(settings, model, messages, live=live, timeout=timeout)
            except (RuntimeError, KeyError, IndexError, TypeError) as exc:
                last_error = exc
                app_v3.logger.warning(
                    "aqua_round2_model_failed model=%s live=%s detail=%s",
                    model,
                    live,
                    str(exc)[:300],
                )
                # For normal chat, only abandon a configured model immediately when
                # it is actually unavailable. Other transient errors still get one
                # current Compound fallback, never the retired Llama model.
                if not live and index == 0 and not _is_model_error(exc) and len(attempts) == 1:
                    break

        if live or _is_weather_query(text):
            raise RuntimeError("الان نتونستم اطلاعات زنده را از وب بگیرم؛ چند لحظه بعد دوباره بپرس. هیچ حدسی نزدم.") from last_error
        raise RuntimeError("سرویس آریا پاسخ نداد؛ چند لحظه بعد دوباره امتحان کن.") from last_error
    finally:
        app_v3.logger.info("aqua_round2_answer_ms=%d", int((time.monotonic() - started) * 1000))


aqua_ai._groq_answer = _fast_groq_answer


@app_v3.app.get("/aqua-round2.js")
def aqua_round2_js():
    return app_v3.send_from_directory(".", "aqua-round2.js", mimetype="application/javascript", max_age=0)


@app_v3.app.after_request
def inject_aqua_round2(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        if '/aqua-round2.js?' not in body:
            body = body.replace(
                "</body>",
                '<script src="/aqua-round2.js?v=20260901-3"></script></body>',
                1,
            )
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_round2_inject_failed detail=%s", str(exc)[:300])
    return response
