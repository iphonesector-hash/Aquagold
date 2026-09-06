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


def test_miniapp_has_isolated_login_and_read_only_reporting_routes():
    code = source("aqua_bale_miniapp.py")
    assert '@app_v3.app.get("/bale-mini")' in code
    assert '@app_v3.app.post("/api/mini/login")' in code
    assert '@app_v3.app.get("/api/mini/day")' in code
    assert '@app_v3.app.get("/api/mini/customers")' in code
    assert '@app_v3.app.get("/api/mini/finance")' in code
    assert "ali0937" not in code
    assert "10 per minute" in code


def test_daily_timeline_is_right_to_left_in_expected_order():
    js = source("aqua-bale-miniapp.js")
    block = js[js.index("function statusTimeline"):js.index("function jobCard")]
    assert block.index("در صف انتظار") < block.index("ثبت شده") < block.index("انجام شده")
    assert "segment.flow" not in block  # behavior is represented by classes, not duplicate DOM injection
    assert "flowRtl" in source("aqua-bale-miniapp.css")


def test_finance_has_daily_weekly_monthly_and_collapsible_chart():
    html = source("aqua-bale-miniapp.html")
    js = source("aqua-bale-miniapp.js")
    assert 'data-period="daily"' in html
    assert 'data-period="weekly"' in html
    assert 'data-period="monthly"' in html
    assert 'id="chartAccordion"' in html
    assert "toggleChart" in js
    assert "accordion.open" in source("aqua-bale-miniapp.css")


def test_bale_sdk_is_scoped_to_miniapp_csp_only():
    html = source("aqua-bale-miniapp.html")
    csp = source("aqua_bale_miniapp_csp.py")
    assert "https://tapi.bale.ai/miniapp.js?3" in html
    assert 'request.path == "/bale-mini"' in csp
    assert "https://tapi.bale.ai" in csp
