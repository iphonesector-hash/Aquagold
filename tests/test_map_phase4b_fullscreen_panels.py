import subprocess
import tempfile
from pathlib import Path

from app import app


def _asset(path: str) -> str:
    with app.test_client() as client:
        response = client.get(path)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_phase4b_generated_navigation_has_one_fullscreen_sheet_owner():
    js = _asset("/aqua-smart-tour.js")

    assert js.count("function aqSyncPhase4BPanelInsets()") == 1
    assert js.count("function aqSetPhase4BSheet(kind,collapsed)") == 1
    assert js.count("function aqTogglePhase4BSheet(kind)") == 1
    assert js.count("function aqBindPhase4BSwipe(handle,kind)") == 1
    assert js.count("function aqSetupPhase4BPanels()") == 1
    assert js.count("if(typeof aqSetupPhase4BPanels==='function')aqSetupPhase4BPanels();") == 1

    assert "aqst-head-handle" in js
    assert "aqst-foot-handle" in js
    assert "aqst-head-collapsed" in js
    assert "aqst-foot-collapsed" in js
    assert "ResizeObserver" in js
    assert "MutationObserver" in js
    assert "visualViewport?.addEventListener?.('resize'" in js
    assert "addEventListener('orientationchange'" in js

    # Phase 4B is presentation-only. Approved navigation/search/voice behavior
    # must remain in the same generated asset.
    assert "function bindMainMapLongPress()" in js
    assert "function searchFreePlaces()" in js
    assert "function evaluateReroute(pos,coords,near,initial=false)" in js
    assert "function voiceManeuverSignature(step)" in js
    assert "function maybeAnnounceManeuver(info)" in js
    assert "function ariaSpeak(text,{replace=false}={})" in js


def test_phase4b_css_makes_map_edge_to_edge_and_sheets_collapsible():
    css = _asset("/aqua-smart-tour.css")
    marker = "/* Aqua Map Phase 4B — true fullscreen navigation + collapsible glass sheets. */"

    assert css.count(marker) == 1
    assert "html.aqst-nav-fullscreen #aqst-nav{display:block!important;overflow:hidden!important" in css
    assert "#aqst-nav .aqst-navmap{position:absolute!important;inset:0!important;width:100%!important;height:100%!important" in css
    assert "#aqst-nav #aqst-nav-map{position:absolute!important;inset:0!important;width:100%!important;height:100%!important" in css
    assert "env(safe-area-inset-top)" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "backdrop-filter:blur(24px)" in css
    assert "0 0 26px rgba(20,178,239,.14)" in css
    assert "#aqst-nav.aqst-head-collapsed .aqst-navhead" in css
    assert "#aqst-nav.aqst-foot-collapsed .aqst-navfoot" in css
    assert "top:var(--aqst-head-bottom,112px)!important" in css
    assert "bottom:var(--aqst-foot-clear,150px)!important" in css
    assert "@media(prefers-reduced-motion:reduce)" in css


def test_phase4b_generated_javascript_stays_syntax_valid_and_startup_surfaces_render():
    js = _asset("/aqua-smart-tour.js")
    html = _asset("/")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "aqua-smart-tour-generated.js"
        path.write_text(js, encoding="utf-8")
        result = subprocess.run(
            ["node", "--check", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    assert result.returncode == 0, result.stderr or result.stdout

    assert 'id="aqua-boot-20260906"' in html
    assert "/assets/aquagold-loading-v20260906b.jpg?v=2" in html
    assert 'class="aq-auth-view"' in html
    assert "/assets/brand-sector.svg" in html
