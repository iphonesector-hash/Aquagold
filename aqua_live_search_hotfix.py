"""Surgical live-search repair for current market/news questions."""
from __future__ import annotations

from datetime import datetime, timezone

import app_v3
import aqua_ai


_original_groq_answer = aqua_ai._groq_answer


def _browser_search_answer(settings, text):
    key = str(settings.get("groq_api_key") or "").strip()
    if not key:
        raise RuntimeError("Groq API key is not configured")

    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    # latest keeps Compound on the current built-in web-search implementation.
    headers = {"Authorization": f"Bearer {key}", "Groq-Model-Version": "latest"}
    now_utc = datetime.now(timezone.utc).isoformat(timespec="minutes")
    messages = [
        {
            "role": "system",
            "content": (
                "تو آریا، دستیار فارسی AquaGold هستی. این درخواست به اطلاعات لحظه‌ای وب نیاز دارد. "
                "با web_search جست‌وجوی واقعی انجام بده و فقط اطلاعات تأییدشده از نتایج زنده را بگو. "
                "اگر سؤال درباره اخبار امروز است، مهم‌ترین خبرهای همان روز را کوتاه و بی‌طرف جمع‌بندی کن. "
                "برای قیمت‌های بازار ایران، نوع دارایی و واحد را شفاف بنویس. قیمت یا خبر روز را حدس نزن. "
                f"زمان مرجع UTC: {now_utc}. پاسخ فارسی، کوتاه و دقیق باشد."
            ),
        },
        {"role": "user", "content": str(text or "")[:1000]},
    ]

    # Mini first: one web search is enough for normal news/price questions and
    # avoids consuming most of Vercel's 60s function window before fallback.
    attempts = (
        ("groq/compound-mini", 22),
        ("groq/compound", 28),
    )
    last_error = None
    for model, timeout in attempts:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "compound_custom": {"tools": {"enabled_tools": ["web_search"]}},
        }
        try:
            data = aqua_ai._post_json(endpoint, payload, headers, timeout=timeout)
            answer = str(data["choices"][0]["message"]["content"] or "").strip()
            if answer:
                return answer
            raise RuntimeError("live search returned an empty answer")
        except (KeyError, IndexError, TypeError, RuntimeError) as exc:
            last_error = exc
            app_v3.logger.warning("aqua_browser_search_failed model=%s detail=%s", model, str(exc)[:260])

    # A live query must never be fabricated. Return a clean temporary failure
    # only after both real web-search systems have failed.
    raise last_error or RuntimeError("live browser search unavailable")


def _groq_answer_with_browser_search(settings, text, history, context):
    if not aqua_ai._needs_live_web_search(text):
        return _original_groq_answer(settings, text, history, context)
    try:
        return _browser_search_answer(settings, text)
    except Exception as exc:
        app_v3.logger.warning("aqua_live_search_final_failure detail=%s", str(exc)[:300])
        return "جست‌وجوی زنده آریا الان از هر دو مسیر وب پاسخ نگرفت؛ چند لحظه بعد دوباره امتحان کن."


aqua_ai._groq_answer = _groq_answer_with_browser_search
