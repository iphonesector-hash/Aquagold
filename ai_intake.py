import json

from smart_intake import parse_intake

SYSTEM_PROMPT = """تو موتور استخراج اطلاعات CRM خدمات AquaGold هستی.
متن معمولاً از بله می‌آید و الگوی غالب این است:
1) خط اول روز/تاریخ/بازه ساعت است.
2) خط بعد نوع کار است: ساید/یخچال/فیلتر/دستگاه/نصب/تعمیر.
3) اولین نامی که کنار شماره موبایل آمده نام خانوادگی مشتری است.
4) خطوط بعد از مشتری تا قبل از خط آخر، آدرس هستند؛ حتی اگر کلمه «آدرس» ندارند.
5) آخرین نام مستقل (گاهی همراه یک عدد، مثل «سما ۳») ویزیتور است.
قالب ممکن است کمی جابه‌جا شود، پس از معنی خطوط هم استفاده کن.
چیزی را که در متن نیست حدس نزن. خروجی فقط JSON معتبر با کلیدهای:
first_name,last_name,phones,address,visitor_code,service_type,description,time_text,amount,payment_method,items,notes.
phones آرایه رشته باشد و items آرایه آبجکت {name,quantity,notes}. مبلغ تومان و عدد صحیح باشد.
"""


def _present(value):
    return value not in (None, "", [], {})


def _merge(local, ai):
    out = dict(ai or {})
    for key, value in (local or {}).items():
        if key in {"last_name", "phones", "address", "visitor_code", "service_type", "time_text", "raw_text"} and _present(value):
            out[key] = value
        elif key not in out or not _present(out.get(key)):
            out[key] = value
    out.setdefault("phones", [])
    out["parser"] = "hybrid-v8"
    return out


def parse_with_ai(text):
    local = parse_intake(text)
    try:
        import aqua_ai
        settings = aqua_ai._load_settings()
        key = settings.get("groq_api_key")
    except Exception:
        key = None
    if not key:
        local["parser"] = "local-v8"
        return local

    payload = {
        "model": "openai/gpt-oss-120b",
        "temperature": 0.05,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": str(text)[:5000]},
        ],
    }
    try:
        body = aqua_ai._post_json(
            "https://api.groq.com/openai/v1/chat/completions",
            payload,
            {"Authorization": f"Bearer {key}"},
            timeout=30,
        )
        content = body["choices"][0]["message"]["content"]
        return _merge(local, json.loads(content))
    except Exception:
        local["parser"] = "local-fallback-v8"
        return local
