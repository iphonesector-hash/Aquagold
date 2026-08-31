"""Surgical live-search repair for current market questions.

Only live web queries are redirected to GPT-OSS browser_search. Normal Aqua chat,
voice, CRM actions and all other behavior keep using the existing runtime.
"""
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
    headers = {"Authorization": f"Bearer {key}"}
    now_utc = datetime.now(timezone.utc).isoformat(timespec="minutes")
    messages = [
        {
            "role": "system",
            "content": (
                "تو آریا، دستیار فارسی AquaGold هستی. این درخواست حتماً به اطلاعات لحظه‌ای وب نیاز دارد. "
                "با browser_search جست‌وجوی واقعی انجام بده و فقط اطلاعاتی را بگو که از نتایج زنده تأیید شده‌اند. "
                "برای قیمت‌های بازار ایران، نوع دارایی و واحد را شفاف بنویس؛ مثلاً دلار بازار آزاد به تومان و طلای ۱۸ عیار به تومان برای هر گرم. "
                "اگر کاربر نوع طلا یا ارز را مشخص نکرده، رایج‌ترین مورد را اعلام کن و نام دقیقش را بنویس. "
                "قیمت را حدس نزن و اگر منابع اختلاف دارند بازه یا منبع/زمان را کوتاه توضیح بده. "
                f"زمان مرجع UTC: {now_utc}. پاسخ فارسی، کوتاه و دقیق باشد."
            ),
        },
        {"role": "user", "content": str(text or "")[:1200]},
    ]

    last_error = None
    for model in ("openai/gpt-oss-120b", "openai/gpt-oss-20b"):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "max_completion_tokens": 1200,
            "tool_choice": "required",
            "tools": [{"type": "browser_search"}],
        }
        try:
            data = aqua_ai._post_json(endpoint, payload, headers, timeout=60)
            answer = str(data["choices"][0]["message"]["content"] or "").strip()
            if answer:
                return answer
            raise RuntimeError("browser_search returned an empty answer")
        except (KeyError, IndexError, TypeError, RuntimeError) as exc:
            last_error = exc
            app_v3.logger.warning(
                "aqua_browser_search_failed model=%s detail=%s",
                model,
                str(exc)[:260],
            )

    raise last_error or RuntimeError("live browser search unavailable")


def _groq_answer_with_browser_search(settings, text, history, context):
    if not aqua_ai._needs_live_web_search(text):
        return _original_groq_answer(settings, text, history, context)
    try:
        return _browser_search_answer(settings, text)
    except RuntimeError as exc:
        app_v3.logger.warning("aqua_live_search_final_failure detail=%s", str(exc)[:300])
        return "اطلاعات لحظه‌ای الان قابل تأیید نیست؛ چند لحظه بعد دوباره امتحان کن."


aqua_ai._groq_answer = _groq_answer_with_browser_search
