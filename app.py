import os
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from flask import jsonify, request

# Ensure production and isolated Vercel previews share the stable runtime secret
# required to read encrypted provider settings.
import aquagold_secret_bootstrap  # noqa: E402,F401
import app_v3
from aquagold_validation import text as valid_text
from ai_intake import parse_with_ai


def _row_json(row):
    out = {}
    for key, value in dict(row).items():
        if isinstance(value, Decimal):
            value = float(value)
        elif isinstance(value, UUID):
            value = str(value)
        elif isinstance(value, (date, datetime)):
            value = value.isoformat()
        out[key] = value
    return out


app_v3.row_json = _row_json
app = app_v3.app

# Register these response normalizers before later UI injectors: Flask runs
# after_request handlers in reverse order, so the finance follow-up and Round 8
# finalize the HTML after the older branch layers.
import aqua_round8_field_fix  # noqa: E402,F401
import aqua_finance_followup  # noqa: E402,F401

# Registers v3/v4/v6 extensions, Aqua AI, Bale intake and PostgreSQL compatibility fixes.
import app_extras  # noqa: E402,F401
import app_fixes  # noqa: E402,F401
import app_commerce  # noqa: E402,F401
import app_routing  # noqa: E402,F401
import aqua_neshan_preview  # noqa: E402,F401
import aqua_ai  # noqa: E402,F401
import aqua_groq_runtime_hotfix  # noqa: E402,F401
import aqua_live_search_hotfix  # noqa: E402,F401
import aqua_voice_runtime_hotfix  # noqa: E402,F401
import bale_bridge  # noqa: E402,F401
import bale_bootstrap  # noqa: E402,F401
import bale_reports  # noqa: E402,F401
import bale_inbox_guard  # noqa: E402,F401
# Preview only: mirror live new/review Bale jobs read-only from main when configured.
import aqua_preview_bale_sync  # noqa: E402,F401
import aqua_smart_register_guard  # noqa: E402,F401
# Register the PR29 Map/Navigation guard before the older map injectors so,
# under Flask's reverse after_request order, it normalizes their final assets last.
import aqua_map_navigation_final_fix  # noqa: E402,F401
# Time-window-aware Bale tour + in-app Neshan navigation, scoped to the Map page.
import aqua_smart_tour  # noqa: E402,F401
# Prefer Neshan's official VRP/logistics solver for time-window tours; retain the
# existing Aqua planner as a deterministic fallback if the service is unavailable.
import aqua_neshan_logistics  # noqa: E402,F401
# Controls fix is registered before polish so reverse after_request execution sees
# the fully polished dynamic Navigation DOM and mounts day/night + minimize buttons.
import aqua_navigation_controls_fix  # noqa: E402,F401
# Register polish/GPS before the pro asset replacer: Flask executes after_request
# in reverse registration order, so the pro fragment is emitted first and patched after.
import aqua_navigation_polish  # noqa: E402,F401
import aqua_navigation_gps_fix  # noqa: E402,F401
# Retain Neshan maneuver metadata and serve the professional Aria navigation UI.
import aqua_navigation_pro  # noqa: E402,F401
# Heading-up/pitched Neshan drive view + free map search/long-press destinations.
import aqua_navigation_drive  # noqa: E402,F401
# Drive adapter registers its own search handler, so lock the fallback after it.
import aqua_navigation_search_fix  # noqa: E402,F401
# Finally bind the current official /v3/search endpoint, preserving Geocoding Plus fallback.
import aqua_navigation_search_v3_fix  # noqa: E402,F401
# Visible Start Navigation CTA for routes drawn by the older optimizer.
import aqua_smart_tour_start_fix  # noqa: E402,F401
import aqua_voice_injector  # noqa: E402,F401
import aqua_requested_ui_hotfix  # noqa: E402,F401
import aqua_push_runtime  # noqa: E402,F401
# Final outer Bale command wrapper: recognizes /aqua before normal work intake.
import bale_aqua_command_runtime  # noqa: E402,F401
import aqua_finance_runtime  # noqa: E402,F401
# Read-only bearer-authenticated surface for the Aqua Aria custom GPT.
import aqua_gpt_actions  # noqa: E402,F401
# Branch-scoped presentation overrides. Main is intentionally untouched.
import aqua_scoped_branch_hotfix  # noqa: E402,F401
# Final isolated QA layer: live web/model recovery, exact clock, layout and Push test.
import aqua_branch_final_fix  # noqa: E402,F401
# Keep Web Push working with both the legacy JSONB and newer split-column schemas.
import aqua_push_schema_compat  # noqa: E402,F401
# Register Round 4 before Round 3 so Flask's reverse after_request order emits Round 4 last.
import aqua_round4_ui_fix  # noqa: E402,F401
# Register the final UI injector before Round 2 so its script is emitted after Round 2.
import aqua_round3_ui_fix  # noqa: E402,F401
# Second isolated QA layer: fast Compound web search plus Bale/map/chart/Push UI repairs.
import aqua_round2_fix  # noqa: E402,F401
# Targeted requested fixes: real service edits, expense edit, fast live prices, dashboard share amount.
import aqua_targeted_fix  # noqa: E402,F401
# Keep targeted edit modals outside the hidden login view.
import aqua_targeted_modal_fix  # noqa: E402,F401
# Final branch-only guard: keep long Aqua AI provider calls outside mutation idempotency locks.
import aqua_round3_backend_fix  # noqa: E402,F401
# QA B1/B2/B3: Aria session-safe chat, payment-method unlabeled totals, service-backed invoices.
import aqua_qa_backend_fix  # noqa: E402,F401
# Round 7 owns the latest voice/news/loader/UI fixes.
import aqua_round7_fix  # noqa: E402,F401
# Preserve explicit Groq settings while still allowing fresh-isolate secret recovery.
import aqua_round7_settings_guard  # noqa: E402,F401
import aqua_finance_dashboard  # noqa: E402,F401


@app_v3.roles_required("technician")
def _smart_parse_ai():
    text = valid_text((request.get_json() or {}).get("text"), "متن", required=True, max_length=8000)
    return jsonify(parse_with_ai(text))


app.view_functions["smart_parse"] = _smart_parse_ai

# Safe runtime diagnostic: exposes only whether providers are configured, never secrets.
_original_health = app.view_functions["health"]


def _health_with_ai_status():
    response = app.make_response(_original_health())
    if response.is_json:
        payload = response.get_json() or {}
        status = aqua_ai.configuration_status()
        payload["ai"] = "configured" if status["brain"] else "not_configured"
        payload["aqua_ai"] = status
        payload["neshan"] = aqua_neshan_preview.configuration_status()
        try:
            bale = bale_bridge._public_settings(bale_bridge._load_settings())
            payload["bale"] = {"enabled": bale["enabled"], "token": bale["bot_token_configured"], "webhook": bale["webhook_configured"]}
        except Exception:
            payload["bale"] = {"enabled": False, "token": False, "webhook": False}
        return jsonify(payload), response.status_code
    return response


app.view_functions["health"] = _health_with_ai_status

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
