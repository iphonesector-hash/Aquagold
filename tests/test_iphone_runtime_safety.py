from pathlib import Path

from app import app


ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def _asset(path):
    response = app.test_client().get(path)
    assert response.status_code == 200, path
    return response.get_data(as_text=True)


def test_startup_skips_second_cinematic_splash_when_official_boot_exists():
    html = _asset("/")
    polish = source("ui-visual-polish.js")
    assert 'id="aqua-boot-20260906"' in html
    assert "document.getElementById('aqua-boot-20260906')" in polish
    assert polish.index("aqua-boot-20260906") < polish.index("document.body.appendChild(d)")


def test_round_fixes_do_not_observe_the_whole_document():
    round6 = source("aqua-round6-user-fixes.js")
    round7 = source("aqua-round7-user-fixes.js")
    round8 = source("aqua-round8-field-fixes.js")
    assert "observe(document.documentElement,{childList:true,subtree:true})" not in round6
    assert "observe(document.body,{childList:true,subtree:true})" not in round7
    assert "dailySection()" in round7
    assert "loaderObserver.observe(document.documentElement" not in round8
    assert "loaderObserver.observe(boot," in round8


def test_bale_discard_observer_is_scoped_to_bale_jobs():
    code = source("bale_inbox_guard.py")
    assert "observer.observe(document.body,{childList:true,subtree:true})" not in code
    assert "includes('bale-jobs')" in code
    assert "observer.observe(root,{childList:true,subtree:true})" in code


def test_served_map_clears_previous_preview_routes():
    js = _asset("/aqua-smart-tour.js")
    assert "function drawSingle(route,origin,target){clearLayers(ST.singleLayers);clearLayers(ST.tourLayers);" in js
    assert "clearLayers(ST.singleLayers);clearLayers(ST.tourLayers);" in js
    assert js.count("try{clearLayers(ST.singleLayers)}catch{}") >= 3
    assert "remainingDistance(route,projection)" in js
    assert "evaluateReroute(pos,coords,projection,initial)" in js
    assert "aqSyncRemainingRoute(route,projection)" in js
