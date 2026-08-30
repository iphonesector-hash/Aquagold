"""Narrow Groq 429 fallback for Aqua chat."""
import json

import app_v3
import aqua_ai


_original_groq_answer = aqua_ai._groq_answer


def _compact_fallback(settings, text, context):
    key = settings.get("groq_api_key")
    if not key:
        return "کلید Groq تنظیم نشده است."
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}"}
    compact = {
        "customers": int((context or {}).get("customers") or 0),
        "products": int((context or {}).get("products") or 0),
        "today_sales": int((context or {}).get("today_sales") or 0),
        "today_received": int((context or {}).get("today_received") or 0),
    }
    messages = [
        {
            "role": "system",
            "content": "تو آریا، دستیار فارسی AquaGold هستی. فارسی تهرانی، طبیعی، کوتاه و دقیق جواب بده. وضعیت برنامه: " + json.dumps(compact, ensure_ascii=False),
        },
        {"role": "user", "content": str(text or "")[:1000]},
    ]
    last_error = None
    # Different model buckets avoid exposing Compound's underlying GPT-OSS-120B
    # TPM exhaustion to the user.
    for model in ("openai/gpt-oss-20b", "llama-3.1-8b-instant"):
        try:
            data = aqua_ai._post_json(endpoint, {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 700}, headers, timeout=45)
            return data["choices"][0]["message"]["content"]
        except RuntimeError as exc:
            last_error = exc
            app_v3.logger.warning("aqua_groq_fallback_failed model=%s detail=%s", model, str(exc)[:220])
    raise last_error or RuntimeError("Groq fallback unavailable")


def _groq_answer_with_rate_fallback(settings, text, history, context):
    try:
        return _original_groq_answer(settings, text, history, context)
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "429" not in msg and "rate_limit" not in msg and "rate limit" not in msg:
            raise
        try:
            return _compact_fallback(settings, text, context)
        except RuntimeError:
            # Never leak provider JSON/rate-limit internals into the chat bubble.
            return "ترافیک سرویس هوش مصنوعی موقتاً بالاست؛ چند ثانیه بعد دوباره امتحان کن."


aqua_ai._groq_answer = _groq_answer_with_rate_fallback
