import json
import os
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


def _merge(local, ai):
    out = dict(local or {})
    for key, value in (ai or {}).items():
        if value not in (None, "", [], {}):
            out[key] = value
    out["parser"] = "ai"
    return out


def parse_with_ai(text):
    local = parse_intake(text)
    key = os.getenv("GROQ_API_KEY")
    if not key:
        local["parser"] = "local"
        return local

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    payload = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        ai = json.loads(content)
        return _merge(local, ai)
    except Exception:
        local["parser"] = "local-fallback"
        return local
