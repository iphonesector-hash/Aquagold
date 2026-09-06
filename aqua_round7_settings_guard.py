"""Preserve explicit Groq settings while keeping Round 7 runtime recovery.

Round 7 must recover provider secrets on a fresh Vercel isolate, but it must not
replace a caller's already-valid settings/model. This tiny final wrapper keeps
both behaviours and leaves the rest of Round 7 untouched.
"""
from __future__ import annotations

import app_v3
import aqua_ai
import aqua_round7_fix as round7


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
        return round7._compact_live_answer(current, text)

    try:
        return round7._PREVIOUS_GROQ_ANSWER(current, text, history, context)
    except RuntimeError as exc:
        detail = str(exc).lower()
        if "413" not in detail and "request_too_large" not in detail and "request entity too" not in detail:
            app_v3.logger.warning("aqua_round7_guard_previous_failed detail=%s", str(exc)[:320])
        return round7._compact_normal_answer(current, text, history, context)


aqua_ai._groq_answer = _groq_answer_with_explicit_settings
