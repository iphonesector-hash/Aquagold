"""Authenticated Aria address intent wired to the existing map adapter."""

import re

from flask import jsonify, request

import app_routing
import app_v3
from aqua_map_address import normalize_persian_address


_ORIGINAL_CHAT = app_v3.app.view_functions.get("aqua_chat")
_ADDRESS_VERBS = ("پیدا کن", "نشون بده", "نشان بده", "روی نقشه", "باز کن", "مسیر")
_CONTEXT_WORDS = ("اطرافش", "اونجا", "همین آدرس", "این آدرس", "این نقطه")


def extract_address_intent(value):
    text = normalize_persian_address(value)
    if any(word in text for word in _CONTEXT_WORDS):
        return {"context": True, "address": ""}
    if not any(word in text for word in _ADDRESS_VERBS):
        return None
    cleaned = re.sub(r"(?:آریا|لطفا|لطفاً|رو|را|برام|برای من)", " ", text)
    cleaned = re.sub(r"(?:روی نقشه\s*)?(?:نشون بده|نشان بده|پیدا کن|باز کن)", " ", cleaned)
    cleaned = re.sub(r"^(?:برو به|مسیر)\s*", "", cleaned)
    return {"context": False, "address": re.sub(r"\s+", " ", cleaned).strip()}


def _is_contextually_specific(query):
    # A bare street/alley name plus number is ambiguous across Iran.
    locality = ("تهران", "کرج", "مرزداران", "صادقیه", "آریاشهر", "شهر", "استان")
    return any(token in query for token in locality) and len(query.split()) >= 2


@app_v3.roles_required("technician")
@app_v3.limiter.limit("20 per minute; 200 per day")
def aria_map_chat():
    payload = request.get_json(silent=True) or {}
    intent = extract_address_intent(payload.get("text"))
    if intent is None:
        return _ORIGINAL_CHAT()
    if intent["context"]:
        return jsonify({"answer": "اول یک آدرس را پیدا و از بین نتیجه‌ها انتخاب کن؛ بعد بگو مشتری‌های اطرافش را نشان بدهم.", "needs_location_context": True})
    query = intent["address"]
    if len(query) < 3:
        return jsonify({"answer": "اسم محله یا خیابون اصلی رو هم بگو.", "results": []})
    try:
        results = app_routing.geocode_provider(query, 3)
    except Exception:
        app_v3.logger.exception("aria_map_geocoding_failed")
        return jsonify({"answer": "فعلاً ارتباط با سرویس نقشه برقرار نشد. دوباره امتحان کن."}), 503
    if not results:
        return jsonify({"answer": "این آدرس رو دقیق پیدا نکردم. اسم محله یا خیابون اصلی رو هم بگو.", "results": []})
    if len(results) != 1 or not _is_contextually_specific(query):
        return jsonify({"answer": "چند جای مشابه پیدا کردم. کدومش منظورت بود؟", "query": query,
                        "multiple_results": True, "results": results})
    selected = results[0]
    return jsonify({"answer": "پیداش کردم. برای نمایش، نتیجه را باز کن.", "query": query,
                    "results": results, "action": {"type": "show_address_on_map", "location": selected}})


if _ORIGINAL_CHAT is not None:
    app_v3.app.view_functions["aqua_chat"] = aria_map_chat


@app_v3.app.get("/aqua-aria-map.js")
def aria_map_js():
    return app_v3.send_from_directory(".", "aqua-aria-map.js", mimetype="application/javascript", max_age=0)


@app_v3.app.after_request
def inject_aria_map(response):
    if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        if "/aqua-aria-map.js" not in body:
            body = body.replace("</head>", '<style>.aq-aria-marker{background:transparent;border:0}.aq-aria-marker span{display:grid;place-items:center;width:38px;height:38px;border:3px solid white;border-radius:14px;background:#7c3aed;color:white;box-shadow:0 8px 24px #0008}.bottom-nav{padding-bottom:max(8px,env(safe-area-inset-bottom));background:var(--surface-2)}#ariaMapCard{margin-bottom:max(0px,env(safe-area-inset-bottom))}</style></head>', 1)
            body = body.replace("</body>", '<script src="/aqua-aria-map.js?v=20260914-1"></script></body>', 1)
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
    return response
