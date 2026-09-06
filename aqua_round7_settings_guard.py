"""Preserve explicit Groq settings while keeping Round 7 runtime recovery.

This wrapper keeps live web requests small enough for the account TPM limit,
retries Compound Mini once when Groq returns a short 429 backoff, and only then
uses a tightly capped Compound fallback.
"""
from __future__ import annotations

import re
import time

import app_v3
import aqua_ai
import aqua_round7_fix as round7


_WEB_REQUEST_MARKERS = (
    "بگرد", "سرچ", "جستجو", "جست‌وجو", "جست و جو", "در وب", "روی وب",
    "اینترنت", "در اینترنت", "از اینترنت", "وب سرچ", "web search",
)


def _wants_live_web(text):
    try:
        if round7._needs_live_web_search(text):
            return True
    except Exception:
        pass
    value = re.sub(r"\s+", " ", str(text or "").replace("\u200c", " ").lower()).strip()
    return any(marker in value for marker in _WEB_REQUEST_MARKERS)


def _retry_after_seconds(error):
    text = str(error or "")
    match = re.search(r"try again in\s*([\d.]+)s", text, re.I)
    if not match:
        return None
    try:
        return max(0.0, min(float(match.group(1)), 5.0))
    except (TypeError, ValueError):
        return None


def _live_payload(model, messages):
    return {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        # Prevent Compound from reserving a huge default completion budget that
        # can trip the Groq TPM limit before web search is allowed to run.
        "max_completion_tokens": 700,
        "compound_custom": {"tools": {"enabled_tools": ["web_search"]}},
    }


def _run_live(settings, model, messages, timeout):
    data = aqua_ai._post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        _live_payload(model, messages),
        round7._groq_headers(settings, version="2025-07-23"),
        timeout=timeout,
    )
    answer = str(data["choices"][0]["message"].get("content") or "").strip()
    if not answer:
        raise RuntimeError("live search returned an empty answer")
    return answer


def _fast_live_answer(settings, text):
    user_text = re.sub(r"\s+", " ", str(text or "")).strip()[:420]
    messages = [{
        "role": "user",
        "content": (
            "با web_search اطلاعات زنده این درخواست را بررسی کن. پاسخ فارسی، کوتاه و دقیق باشد. "
            "برای خبر، قیمت، هوا یا اطلاعات امروز چیزی را حدس نزن و نتیجه جست‌وجوی واقعی را بگو. "
            "درخواست: " + user_text
        ),
    }]
    last_error = None

    # Compound Mini needs only one tool call for ordinary current-information
    # questions and has substantially lower latency/usage than full Compound.
    for attempt in range(2):
        try:
            return _run_live(settings, "groq/compound-mini", messages, 10)
        except (RuntimeError, KeyError, IndexError, TypeError) as exc:
            last_error = exc
            app_v3.logger.warning(
                "aqua_round8_live_mini_failed attempt=%s detail=%s",
                attempt + 1,
                str(exc)[:320],
            )
            delay = _retry_after_seconds(exc)
            if attempt == 0 and delay is not None:
                time.sleep(delay + 0.15)
                continue
            break

    try:
        return _run_live(settings, "groq/compound", messages, 18)
    except (RuntimeError, KeyError, IndexError, TypeError) as exc:
        last_error = exc
        app_v3.logger.warning("aqua_round8_live_compound_failed detail=%s", str(exc)[:320])

    raise RuntimeError("جست‌وجوی زنده آریا موقتاً پاسخ نداد؛ چند لحظه بعد دوباره امتحان کن.") from last_error


def _groq_answer_with_explicit_settings(settings, text, history, context):
    current = dict(settings or {})
    if not str(current.get("groq_api_key") or "").strip():
        recovered = round7._settings_with_recovery()
        merged = dict(recovered or {})
        merged.update({key: value for key, value in current.items() if value not in (None, "")})
        current = merged

    if _wants_live_web(text):
        return _fast_live_answer(current, text)

    try:
        return round7._PREVIOUS_GROQ_ANSWER(current, text, history, context)
    except RuntimeError as exc:
        detail = str(exc).lower()
        if "413" not in detail and "request_too_large" not in detail and "request entity too" not in detail:
            app_v3.logger.warning("aqua_round7_guard_previous_failed detail=%s", str(exc)[:320])
        return round7._compact_normal_answer(current, text, history, context)


aqua_ai._groq_answer = _groq_answer_with_explicit_settings
