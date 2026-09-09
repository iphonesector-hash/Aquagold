import math
import subprocess
import tempfile
from pathlib import Path

import pytest

from app import app
import aqua_smart_tour as smart_tour


def _asset(path):
    response = app.test_client().get(path)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_phase4c_is_lazy_map_owned_and_does_not_rewrite_startup_html():
    html = _asset("/")
    js = _asset("/aqua-smart-tour.js")
    base = Path("ui-v3-base.js").read_text(encoding="utf-8")

    assert 'id="aqua-boot-20260906"' in html
    assert 'class="aq-auth-view"' in html
    assert "aqst-map-workspace" not in html
    assert "aquagold:map-ready" in base
    assert "window.addEventListener('aquagold:map-ready',enhance)" in js
    assert "if(!mapEl||!isMapPageVisible())return" in js

    start = js.index("function aqNormalMapSection()")
    end = js.index("async function refreshVoiceCapability()", start)
    phase4c = js[start:end]
    assert "MutationObserver" not in phase4c
    assert "after_request" not in phase4c
    assert "setInterval" not in phase4c
    assert "aqMapWorkspaceObserver" not in js


def test_phase4c_generated_map_controls_and_markers_have_single_ownership():
    js = _asset("/aqua-smart-tour.js")
    css = _asset("/aqua-smart-tour.css")

    assert js.count("workspace.id='aqst-map-workspace'") == 1
    assert js.count('id="aqst-map-tools-toggle"') == 1
    assert js.count('id="aqst-special-toggle"') == 1
    assert js.count('id="aqst-map-tools-content"') == 1
    assert js.count("function aqSetupNormalMapWorkspace()") == 1
    assert js.count("function aqRenderSpecialMarkers()") == 1
    assert "for(const marker of ST.nav.specialMarkers)" in js
    assert "ST.nav.specialMarkers=[]" in js
    assert "selectFreeDestination({lat:Number(item.lat),lng:Number(item.lng)" in js
    assert "class=\"aqst-free-save\">ذخیره موقعیت" in js
    assert "window.confirm(`موقعیت «${item.name}» حذف شود؟`)" in js

    marker = "/* Aqua Map Phase 4C — lazy normal-Map workspace and special locations. */"
    assert css.count(marker) == 1
    assert "height:clamp(320px,calc(100dvh - 190px" in css
    assert ".aqst-map-sheet[data-open=true]" in css
    assert "pointer-events:none" in css
    assert "@keyframes aqstMapHandleGlow" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert ".aqst-special-pin" in css


def test_phase4c_generated_javascript_and_approved_map_guards_remain_valid():
    js = _asset("/aqua-smart-tour.js")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "aqua-smart-tour-phase4c.js"
        path.write_text(js, encoding="utf-8")
        result = subprocess.run(
            ["node", "--check", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    assert result.returncode == 0, result.stderr or result.stdout

    assert "function bindMainMapLongPress()" in js
    assert "function searchFreePlaces()" in js
    assert "function evaluateReroute(pos,coords,near,initial=false)" in js
    assert "function voiceManeuverSignature(step)" in js
    assert "function aqSetupPhase4BPanels()" in js
    assert "firstBand=voiceManeuverBand(first.distance)" in js


def test_phase4c_marker_render_is_idempotent():
    js = _asset("/aqua-smart-tour.js")
    start = js.index("function aqSpecialLocations()")
    end = js.index("function aqRenderSpecialLocations()", start)
    block = js[start:end]
    script = f"""
const ST={{nav:{{specialLocations:[
 {{id:'1',name:'بانک',address:'',lat:35.7,lng:50.9}},
 {{id:'2',name:'انبار',address:'',lat:35.8,lng:51.0}}
],specialMarkers:[{{old:true}}]}}}};
let removed=0,added=0;
const map={{removeLayer(){{removed++;}}}};
function mainMap(){{return map;}}
function $(){{return null;}}
function esc(value){{return String(value);}}
function selectFreeDestination(){{}}
function aqSetNormalMapPanel(){{}}
const L={{
 divIcon(value){{return value;}},
 marker(){{return {{addTo(){{added++;return this;}},bindTooltip(){{return this;}},on(){{return this;}}}};}}
}};
globalThis.window={{L}};
{block}
aqRenderSpecialMarkers();
if(ST.nav.specialMarkers.length!==2)throw new Error('first render duplicated markers');
aqRenderSpecialMarkers();
if(ST.nav.specialMarkers.length!==2)throw new Error('second render duplicated markers');
if(added!==4||removed!==3)throw new Error(`unexpected marker lifecycle ${{added}}/${{removed}}`);
"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "phase4c-marker-idempotency.js"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            ["node", str(path)], check=False, capture_output=True, text=True, timeout=20
        )
    assert result.returncode == 0, result.stderr or result.stdout


def test_phase4c_special_location_validation_and_per_user_namespace():
    assert smart_tour._special_locations_key("17") == "map_special_locations:17"
    assert smart_tour._special_locations_key("42") == "map_special_locations:42"

    item = smart_tour._special_location_payload(
        {"name": " بانک تست ", "address": " فردیس ", "lat": 35.72, "lng": 50.98}
    )
    assert item["name"] == "بانک تست"
    assert item["address"] == "فردیس"
    assert item["lat"] == 35.72
    assert item["lng"] == 50.98
    assert item["id"]

    edited = smart_tour._special_location_payload(
        {"name": "بانک تست ویرایش", "address": "فلکه سوم", "lat": 1, "lng": 2},
        existing=item,
    )
    assert edited["id"] == item["id"]
    assert edited["lat"] == item["lat"]
    assert edited["lng"] == item["lng"]

    for payload in (
        {"name": "", "lat": 35, "lng": 51},
        {"name": "x", "lat": 91, "lng": 51},
        {"name": "x", "lat": math.nan, "lng": 51},
        {"name": "x", "lat": 35, "lng": math.inf},
        [],
    ):
        with pytest.raises(Exception):
            smart_tour._special_location_payload(payload)


def test_phase4c_malformed_saved_json_is_ignored_and_deduplicated():
    valid = smart_tour._special_location_payload(
        {"name": "انبار", "address": "کرج", "lat": 35.8, "lng": 50.9}
    )

    class Cursor:
        def execute(self, sql, params):
            self.sql = sql
            self.params = params

        def fetchone(self):
            return {
                "value": {
                    "items": [
                        None,
                        {"id": "bad", "name": "خراب", "lat": 35, "lng": 51},
                        valid,
                        dict(valid),
                        {**valid, "id": "ea75aa91-8ee2-4423-9b9b-a67f8b761ee8", "lat": "NaN"},
                    ]
                }
            }

    items = smart_tour._read_special_locations(Cursor(), "map_special_locations:17")
    assert items == [valid]


def test_phase4c_special_location_routes_are_registered_once():
    rules = [(rule.rule, tuple(sorted(rule.methods - {"OPTIONS", "HEAD"}))) for rule in app.url_map.iter_rules()]
    assert rules.count(("/api/map/special-locations", ("GET",))) == 1
    assert rules.count(("/api/map/special-locations", ("POST",))) == 1
    assert rules.count(("/api/map/special-locations/<uuid:location_id>", ("PATCH",))) == 1
    assert rules.count(("/api/map/special-locations/<uuid:location_id>", ("DELETE",))) == 1
