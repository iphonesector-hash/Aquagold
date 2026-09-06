"""Preserve explicit Groq settings while keeping Round 7 runtime recovery.

Round 7 must recover provider secrets on a fresh Vercel isolate, but it must not
replace a caller's already-valid settings/model. This final wrapper also keeps
the first Compound Mini web-search attempt bounded for fast mobile responses.
"""
from __future__ import annotations

import re

import app_v3
import aqua_ai
import aqua_round7_fix as round7


def _fast_live_answer(settings, text):
    user_text = re.sub(r"\s+", " ", str(text or "")).strip()[:500]
    messages = [{
        "role": "user",
        "content": (
            "با web_search اطلاعات زنده و امروز این درخواست را بررسی کن. پاسخ کوتاه و فارسی باشد، "
            "رویدادهای مهم را با زمان/تاریخ روشن بگو و چیزی را حدس نزن. اگر موضوع سیاسی یا خبری است، "
            "فقط خبرهای تأییدشدنی و تازه را جمع‌بندی کن. درخواست: " + user_text
        ),
    }]
    last_error = None
    for model, timeout in (("groq/compound-mini", 9), ("groq/compound", 18)):
        try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.1,
                "compound_custom": {"tools": {"enabled_tools": ["web_search"]}},
            }
            data = aqua_ai._post_json(
                "https://api.groq.com/openai/v1/chat/completions",
                payload,
                round7._groq_headers(settings, version="2025-07-23"),
                timeout=timeout,
            )
            answer = str(data["choices"][0]["message"].get("content") or "").strip()
            if answer:
                return answer
        except (RuntimeError, KeyError, IndexError, TypeError) as exc:
            last_error = exc
            app_v3.logger.warning("aqua_round7_fast_live_failed model=%s detail=%s", model, str(exc)[:320])
    raise RuntimeError("جست‌وجوی زنده آریا موقتاً پاسخ نداد؛ چند لحظه بعد دوباره امتحان کن.") from last_error


def _groq_answer_with_explicit_settings(settings, text, history, context):
    current = dict(settings or {})
    if not str(current.get("groq_api_key") or "").strip():
        recovered = round7._settings_with_recovery()
        # Runtime-recovered secrets/defaults fill only missing fields; explicit
        # caller choices such as brain_model remain authoritative.
        merged = dict(recovered or {})
        merged.update({key: value for key, value in current.items() if value not in (None, "")})
        current = merged

    if round7._needs_live_web_search(text):
        return _fast_live_answer(current, text)

    try:
        return round7._PREVIOUS_GROQ_ANSWER(current, text, history, context)
    except RuntimeError as exc:
        detail = str(exc).lower()
        if "413" not in detail and "request_too_large" not in detail and "request entity too" not in detail:
            app_v3.logger.warning("aqua_round7_guard_previous_failed detail=%s", str(exc)[:320])
        return round7._compact_normal_answer(current, text, history, context)


aqua_ai._groq_answer = _groq_answer_with_explicit_settings
