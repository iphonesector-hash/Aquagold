from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_miniapp_python_is_syntax_valid_and_registered():
    ast.parse(source("aqua_bale_miniapp.py"))
    ast.parse(source("aqua_bale_miniapp_csp.py"))
    app = source("app.py")
    assert "import aqua_bale_miniapp" in app
    assert "import aqua_bale_miniapp_csp" in app


def test_miniapp_has_isolated_login_reporting_and_password_routes():
    code = source("aqua_bale_miniapp.py")
    assert '@app_v3.app.get("/bale-mini")' in code
    assert '@app_v3.app.post("/api/mini/login")' in code
    assert '@app_v3.app.post("/api/mini/password")' in code
    assert '@app_v3.app.get("/api/mini/day")' in code
    assert '@app_v3.app.get("/api/mini/customers")' in code
    assert '@app_v3.app.get("/api/mini/finance")' in code
    assert "aqua_bale_mini_auth" in code
    assert "password_sha256" in code
    assert "ali0937" not in code
    assert "10 per minute" in code


def test_daily_report_uses_final_service_customer_data_and_cancelled_bale_jobs():
    code = source("aqua_bale_miniapp.py")
    day = code[code.index("def aqua_bale_mini_day"):code.index("def aqua_bale_mini_customers")]
    assert "from service_visits s" in day
    assert "join customers_v2 c" in day
    assert "c.last_name as customer_name" in day
    assert "coalesce(s.received_amount,0)" in day
    assert "status not in ('cancelled','scheduled')" in day
    assert "from bale_jobs b" in day
    assert "b.status='cancelled'" in day
    assert "completed + cancelled" in day


def test_customer_counts_are_consistent_with_finalized_services():
    code = source("aqua_bale_miniapp.py")
    block = code[code.index("def aqua_bale_mini_customers"):code.index("def aqua_bale_mini_customer_detail")]
    assert "status not in ('cancelled','scheduled')" in block
    assert 'item["total_services"] = item["completed_services"] + item["cancelled_services"]' in block
    assert "sum(s.received_amount)" in block


def test_finance_sql_uses_safe_alias_and_finalized_service_semantics():
    code = source("aqua_bale_miniapp.py")
    block = code[code.index("def aqua_bale_mini_finance"):]
    lower = block.lower()
    assert "as report_day" in lower
    assert "::date day" not in lower
    assert "status not in ('cancelled','scheduled')" in block
    assert 'item["day"] = item.pop("report_day")' in block


def test_daily_timeline_is_right_to_left_in_expected_order():
    js = source("aqua-bale-miniapp.js")
    css = source("aqua-bale-miniapp.css")
    block = js[js.index("function statusTimeline"):js.index("function jobCard")]
    template = block[block.index("return `<div class=\"timeline\">"):]
    assert template.index("${waitClass}") < template.index("${regClass}") < template.index("${finalClass}")
    assert "در صف انتظار" in template
    assert "ثبت شده" in template
    assert "${finalLabel}" in template
    assert ".timeline{direction:rtl" in css
    assert "flowRtl" in css


def test_finance_has_daily_weekly_monthly_collapsible_chart_and_settings():
    html = source("aqua-bale-miniapp.html")
    js = source("aqua-bale-miniapp.js")
    assert 'data-period="daily"' in html
    assert 'data-period="weekly"' in html
    assert 'data-period="monthly"' in html
    assert 'id="chartAccordion"' in html
    assert 'id="settingsToggle"' in html
    assert 'id="passwordForm"' in html
    assert "toggleChart" in js
    assert "changePassword" in js
    assert ".accordion.open" in source("aqua-bale-miniapp.css")


def test_visual_assets_are_vector_and_use_professional_icon_sprite():
    html = source("aqua-bale-miniapp.html")
    css = source("aqua-bale-miniapp.css")
    logo = source("assets/aquagold-bale-mark.svg")
    assert "/assets/aquagold-bale-mark.svg" in html
    assert "/assets/aqua-icons.svg#i-finance" in html
    assert "/assets/aqua-icons.svg#i-customers" in html
    assert "splash-logo" in css
    assert "drop-shadow" in css
    assert "linearGradient" in logo
    assert "feGaussianBlur" in logo


def test_ios_audio_can_reunlock_after_webview_suspend():
    js = source("aqua-bale-miniapp.js")
    assert "async function ensureAudio" in js
    assert "await state.audio.resume()" in js
    assert "state.audioUnlocked=false" in js
    assert "pageshow" in js
    assert "visibilitychange" in js
    assert "pointerdown" in js
    assert "touchend" in js


def test_bale_sdk_is_scoped_to_miniapp_csp_only():
    html = source("aqua-bale-miniapp.html")
    csp = source("aqua_bale_miniapp_csp.py")
    assert "https://tapi.bale.ai/miniapp.js?3" in html
    assert 'request.path == "/bale-mini"' in csp
    assert "https://tapi.bale.ai" in csp
