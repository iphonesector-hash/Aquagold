import json
import logging
import os
import urllib.error
import urllib.request

from smart_intake import parse_intake

SYSTEM_PROMPT = """تو موتور استخراج اطلاعات CRM خدمات تصفیه آب AquaGold هستی.
از متن فارسی کاربر فقط اطلاعات موجود را استخراج کن و چیزی حدس نزن.
خروجی فقط JSON معتبر باشد با کلیدهای زیر:
first_name, last_name, phones, address, visitor_code, service_type, description,
time_text, amount, payment_method, items, notes.
phones آرایه رشته‌ها باشد. items آرایه‌ای از آبجکت‌های {name, quantity, notes} باشد.
مبالغ را به عدد صحیح تومان تبدیل کن. اگر موردی وجود ندارد null یا آرایه خالی برگردان.
نام خانوادگی یکسان به معنی یک مشتری نیست؛ هرگز درباره هویت مشتری تصمیم نگیر.
"""

LOGGER = logging.getLogger("aquagold")
DEFAULT_MODEL = "openai/gpt-oss-120b"
FALLBACK_MODEL = "openai/gpt-oss-20b"
DEPRECATED_MODELS = {
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
}


def _merge(local, ai):
    out = dict(local or {})
    for key, value in (ai or {}).items():
        if value not in (None, "", [], {}):
            out[key] = value
    out["parser"] = "ai"
    return out


def _configured_groq_key():
    """Reuse the same Groq key that Aqua AI uses in Settings."""
    key = os.getenv("GROQ_API_KEY", "").strip()
    if key:
        return key
    try:
        # Lazy import avoids the startup cycle app -> ai_intake -> aqua_ai.
        import aqua_ai

        return str(aqua_ai._load_settings().get("groq_api_key") or "").strip()
    except Exception as exc:
        LOGGER.warning("smart_intake_key_lookup_failed: %s", str(exc)[:180])
        return ""


def _model_candidates():
    preferred = str(os.getenv("GROQ_MODEL") or "").strip()
    # Groq shut these models down for Free/Developer accounts on 2026-08-16.
    if not preferred or preferred in DEPRECATED_MODELS:
        preferred = DEFAULT_MODEL
    result = []
    for model in (preferred, DEFAULT_MODEL, FALLBACK_MODEL):
        if model and model not in result:
            result.append(model)
    return result


def _request_ai(key, model, text):
    payload = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AquaGold/SmartIntake",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("Groq returned a non-object JSON payload")
    return parsed


def parse_with_ai(text):
    local = parse_intake(text)
    key = _configured_groq_key()
    if not key:
        local["parser"] = "local"
        return local

    last_error = None
    for model in _model_candidates():
        try:
            return _merge(local, _request_ai(key, model, text))
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                detail = ""
            last_error = f"HTTP {exc.code}: {detail}"
            LOGGER.warning("smart_intake_groq_failed model=%s detail=%s", model, last_error[:500])
        except Exception as exc:
            last_error = str(exc)
            LOGGER.warning("smart_intake_groq_failed model=%s detail=%s", model, last_error[:500])

    LOGGER.warning("smart_intake_local_fallback after provider failure: %s", (last_error or "unknown")[:500])
    local["parser"] = "local-fallback"
    return local
