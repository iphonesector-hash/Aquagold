"""Branch-only runtime guard for Aqua AI request locking.

Aqua AI chat/voice calls are long-running provider operations, not database create
mutations. They must not participate in the generic idempotency row lock used by
financial/customer writes, otherwise a retry can be trapped behind a stale
"request is processing" row.
"""
from __future__ import annotations

from flask import request

import app_v3

_BYPASS_PATHS = {
    "/api/aqua-ai/chat",
    "/api/aqua-ai/transcribe",
    "/api/aqua-ai/speak",
}
_original_idempotency_begin = app_v3._idempotency_begin


def _aqua_round3_idempotency_begin(user_id):
    if request.path in _BYPASS_PATHS:
        return None, None
    return _original_idempotency_begin(user_id)


app_v3._idempotency_begin = _aqua_round3_idempotency_begin
