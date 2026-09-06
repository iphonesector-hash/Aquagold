"""Final branch-only field fixes for the September 6 AquaGold preview.

Scope:
- use the exact new Aqua Sector loading artwork with a new cache-busting URL;
- make first voice transcription prefer/recover Groq before the empty ElevenLabs quota;
- make current/news/political questions use a compact live-search path that avoids 413;
- inject the final daily-report edit-button reliability patch.
"""
from __future__ import annotations

import base64
import os
import re
import time
import urllib.error
from pathlib import Path

from flask import Response, jsonify, request

import app_v3
import aqua_ai
import aqua_voice_runtime_hotfix as voice_runtime


NEW_LOADING_URL = "/assets/aquagold-loading-v20260906b.jpg"
LEGACY_LOADING_URL = "/assets/aquagold-loading-v20260906.jpg"
_LOADING_FILE = Path(__file__).resolve().parent / "assets" / "aqua-loading-v20260906b.b64"
MAX_AUDIO = 8 * 1024 * 1024
_PREVIOUS_GROQ_ANSWER = aqua_ai._groq_answer
_PREVIOUS_NEEDS_LIVE = aqua_ai._needs_live_web_search

_FA_NORMALISE = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})
NEWS_WORDS = (
    "اخبار", "خبر", "خبرها", "سیاسی", "سیاست", "تحولات", "خبر فوری",
    "جنگ", "انتخابات", "دولت", "رئیس جمهور", "رئیس‌جمهور", "مجلس",
)
FRESH_WORDS = (
    "امروز", "الان", "فعلا", "فعلاً", "جدید", "جدیدترین", "آخرین",
    "تازه", "چه خبر", "این ساعت", "این لحظه", "لحظه‌ای",
)


def _norm(value):
    text = str(value or "").translate(_FA_NORMALISE).replace("\u200c", " ").lower()
    return re.sub(r"\s+", " ", text).strip()


def _needs_live_web_search(text):
    value = _norm(text)
    try:
        if _PREVIOUS_NEEDS_LIVE(text):
            return True
    except Exception:
        pass
    if "چه خبر" in value:
        return True
    return any(word in value for word in NEWS_WORDS) and any(word in value for word in FRESH_WORDS)


aqua_ai._needs_live_web_search = _needs_live_web_search


def _settings_with_recovery():
    settings = aqua_ai._load_settings()
    if not str(settings.get("groq_api_key") or "").strip():
        # On a fresh Vercel isolate the encrypted bootstrap can be consumed just
        # before the first voice/chat request. Re-read once before falling back.
        try:
            aqua_ai._consume_secret_bootstrap()
        except Exception:
            pass
        time.sleep(0.08)
        settings = aqua_ai._load_settings()
    if not str(settings.get("groq_api_key") or "").strip():
        settings["groq_api_key"] = os.getenv("GROQ_API_KEY", "")
    return settings


def _groq_headers(settings, *, version=None):
    key = str((settings or {}).get("groq_api_key") or "").strip()
    if not key:
        raise RuntimeError("کلید Groq تنظیم نشده است")
    headers = {"Authorization": f"Bearer {key}"}
    if version:
        headers["Groq-Model-Version"] = version
    return headers


def _compact_live_answer(settings, text):
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
    for model, timeout in (("groq/compound-mini", 18), ("groq/compound", 22)):
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
                _groq_headers(settings, version="2025-07-23"),
                timeout=timeout,
            )
            answer = str(data["choices"][0]["message"].get("content") or "").strip()
            if answer:
                return answer
        except (RuntimeError, KeyError, IndexError, TypeError) as exc:
            last_error = exc
            app_v3.logger.warning("aqua_round7_live_failed model=%s detail=%s", model, str(exc)[:320])
    raise RuntimeError("جست‌وجوی زنده آریا موقتاً پاسخ نداد؛ چند لحظه بعد دوباره امتحان کن.") from last_error


def _compact_normal_answer(settings, text, history, context):
    system = (
        "تو آریا، دستیار فارسی AquaGold هستی. فارسی طبیعی و کوتاه جواب بده. "
        "اگر سؤال به اطلاعات لحظه‌ای مربوط نیست، بدون ابزار وب پاسخ بده. "
        "وضعیت مختصر برنامه: مشتری‌ها=%s، سرویس‌ها=%s، دریافتی امروز=%s."
        % (int((context or {}).get("customers") or 0), int((context or {}).get("services") or 0), int((context or {}).get("today_received") or 0))
    )
    messages = [{"role": "system", "content": system}]
    for item in (history or [])[-2:]:
        role = item.get("role")
        content = str(item.get("content") or "").strip()[:450]
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": str(text or "")[:1000]})

    configured = str((settings or {}).get("brain_model") or "").strip()
    attempts = []
    if configured and configured not in {"groq/compound", "llama-3.3-70b-versatile"}:
        attempts.append(configured)
    attempts.extend(["groq/compound-mini", "openai/gpt-oss-120b", "groq/compound"])
    seen = set()
    last_error = None
    for model in attempts:
        if model in seen:
            continue
        seen.add(model)
        try:
            payload = {"model": model, "messages": messages, "temperature": 0.2}
            data = aqua_ai._post_json(
                "https://api.groq.com/openai/v1/chat/completions",
                payload,
                _groq_headers(settings),
                timeout=20,
            )
            answer = str(data["choices"][0]["message"].get("content") or "").strip()
            if answer:
                return answer
        except (RuntimeError, KeyError, IndexError, TypeError) as exc:
            last_error = exc
            app_v3.logger.warning("aqua_round7_chat_failed model=%s detail=%s", model, str(exc)[:320])
    raise RuntimeError("سرویس آریا پاسخ نداد؛ چند لحظه بعد دوباره امتحان کن.") from last_error


def _round7_groq_answer(settings, text, history, context):
    settings = _settings_with_recovery()
    if _needs_live_web_search(text):
        return _compact_live_answer(settings, text)
    try:
        return _PREVIOUS_GROQ_ANSWER(settings, text, history, context)
    except RuntimeError as exc:
        detail = str(exc).lower()
        if "413" not in detail and "request_too_large" not in detail and "request entity too" not in detail:
            # One compact current-model recovery also covers transient configured-model failures.
            app_v3.logger.warning("aqua_round7_previous_failed detail=%s", str(exc)[:320])
        return _compact_normal_answer(settings, text, history, context)


aqua_ai._groq_answer = _round7_groq_answer


@app_v3.roles_required("technician")
@app_v3.limiter.limit("10 per minute; 100 per day")
def aqua_transcribe_round7():
    upload = request.files.get("audio")
    if not upload:
        return jsonify({"error": "فایل صوتی دریافت نشد"}), 400
    audio = upload.read(MAX_AUDIO + 1)
    if not audio:
        return jsonify({"error": "فایل صوتی خالی است"}), 400
    if len(audio) > MAX_AUDIO:
        return jsonify({"error": "صدا باید حداکثر ۸ مگابایت باشد"}), 413

    filename = upload.filename or "aqua.m4a"
    mimetype = upload.mimetype or "audio/mp4"
    settings = _settings_with_recovery()
    groq_key = str(settings.get("groq_api_key") or "").strip()
    eleven_key = str(settings.get("elevenlabs_api_key") or "").strip()
    errors = []

    if groq_key:
        for attempt in range(2):
            try:
                payload = voice_runtime._provider_post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    {"model": "whisper-large-v3-turbo", "language": "fa", "response_format": "json", "temperature": "0"},
                    filename,
                    audio,
                    mimetype,
                    {"Authorization": f"Bearer {groq_key}"},
                    timeout=60,
                )
                spoken = str(payload.get("text") or "").strip()
                if spoken:
                    app_v3.logger.info("aqua_round7_stt_ok provider=groq attempt=%s bytes=%s", attempt + 1, len(audio))
                    return jsonify({"text": spoken, "provider": "groq"})
                errors.append("groq_empty")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:400]
                errors.append(f"groq_{exc.code}")
                app_v3.logger.warning("aqua_round7_stt_groq_failed attempt=%s status=%s detail=%s", attempt + 1, exc.code, detail)
            except Exception as exc:
                errors.append("groq_network")
                app_v3.logger.warning("aqua_round7_stt_groq_failed attempt=%s detail=%s", attempt + 1, str(exc)[:400])
            if attempt == 0:
                time.sleep(0.22)

    # Keep ElevenLabs as a true fallback only after Groq recovery/retry. The
    # current account may have zero credits, so it must never steal the first attempt.
    if eleven_key:
        try:
            payload = voice_runtime._provider_post(
                "https://api.elevenlabs.io/v1/speech-to-text",
                {"model_id": settings.get("stt_model") or "scribe_v2", "language_code": "fas"},
                filename,
                audio,
                mimetype,
                {"xi-api-key": eleven_key},
                timeout=60,
            )
            spoken = str(payload.get("text") or "").strip()
            if spoken:
                return jsonify({"text": spoken, "provider": "elevenlabs"})
        except Exception as exc:
            errors.append("eleven_failed")
            app_v3.logger.warning("aqua_round7_stt_eleven_failed detail=%s", str(exc)[:320])

    if not groq_key and not eleven_key:
        return jsonify({"error": "کلید Groq یا ElevenLabs برای تبدیل ویس تنظیم نشده است"}), 409
    return jsonify({"error": "تبدیل ویس انجام نشد؛ دوباره میکروفن را بزن", "providers": errors}), 502


# Replace the existing endpoint after every older voice layer has loaded.
app_v3.app.view_functions["aqua_transcribe"] = aqua_transcribe_round7


@app_v3.app.get(NEW_LOADING_URL)
def aqua_round7_loading_image():
    payload = base64.b64decode(_LOADING_FILE.read_text(encoding="ascii"))
    return Response(payload, mimetype="image/jpeg", headers={"Cache-Control": "no-store, max-age=0"})


@app_v3.app.get("/aqua-round7-user-fixes.js")
def aqua_round7_user_fixes_js():
    return app_v3.send_from_directory(".", "aqua-round7-user-fixes.js", mimetype="application/javascript", max_age=0)


BOOT_HEAD = (
    f'<link rel="preload" as="image" href="{NEW_LOADING_URL}?v=2">'
    f'<link rel="apple-touch-startup-image" href="{NEW_LOADING_URL}?v=2">'
    # The legacy URL marker deliberately prevents the older injector from adding its cached artwork.
    f'<!-- legacy-loader-disabled:{LEGACY_LOADING_URL} -->'
    '<style>body[x-cloak]{display:block!important;overflow:hidden}</style>'
)

BOOT_HTML = f'''
<div id="aqua-boot-20260906" aria-label="در حال بارگذاری AquaGold" style="position:fixed;inset:0;z-index:2147483000;background:#010817;display:grid;place-items:center;overflow:hidden;transition:opacity .35s ease;opacity:1">
  <img src="{NEW_LOADING_URL}?v=2" alt="Aqua sector" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center;user-select:none;-webkit-user-drag:none">
  <div style="position:absolute;left:12%;right:12%;bottom:max(42px,calc(env(safe-area-inset-bottom) + 26px));height:3px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden"><i style="display:block;width:42%;height:100%;border-radius:inherit;background:linear-gradient(90deg,#0789e8,#2be8ff);animation:aquaBootSweep7 1.2s ease-in-out infinite alternate"></i></div>
</div>
<style>@keyframes aquaBootSweep7{{from{{transform:translateX(0)}}to{{transform:translateX(138%)}}}}</style>
<script>(()=>{{const id='aqua-boot-20260906';const hide=()=>{{const el=document.getElementById(id);if(!el)return;el.style.opacity='0';el.style.pointerEvents='none';setTimeout(()=>el.remove(),420)}};const watch=()=>{{const body=document.body;if(!body)return;if(!body.hasAttribute('x-cloak'))return hide();const o=new MutationObserver(()=>{{if(!body.hasAttribute('x-cloak')){{o.disconnect();hide()}}}});o.observe(body,{{attributes:true,attributeFilter:['x-cloak']}})}};if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',watch,{{once:true}});else watch();document.addEventListener('alpine:initialized',()=>setTimeout(hide,180),{{once:true}});setTimeout(hide,12000)}})();</script>
'''


@app_v3.app.after_request
def inject_aqua_round7(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response
        response.direct_passthrough = False
        body = response.get_data(as_text=True)

        # Strip any loader from a previously composed response, then install the
        # new cache-busted one while retaining the marker older injectors test for.
        if NEW_LOADING_URL not in body:
            body = body.replace("</head>", BOOT_HEAD + "</head>", 1)
        if 'id="aqua-boot-20260906"' not in body:
            body = body.replace(
                '<body x-data="app()" x-init="init()" x-cloak>',
                '<body x-data="app()" x-init="init()" x-cloak>' + BOOT_HTML,
                1,
            )
        if "/aqua-round7-user-fixes.js?" not in body:
            body = body.replace("</body>", '<script src="/aqua-round7-user-fixes.js?v=20260906-2"></script></body>', 1)

        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_round7_inject_failed detail=%s", str(exc)[:320])
    return response
