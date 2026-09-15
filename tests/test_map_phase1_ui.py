import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from app import app
import aqua_navigation_search_v3_fix as map_search


def _asset(path: str) -> str:
    response = app.test_client().get(path)
    assert response.status_code == 200, path
    return response.get_data(as_text=True)


def _assert_css_structurally_valid(css: str) -> None:
    """Reject unbalanced generated CSS while ignoring comments and quoted strings."""
    depth = 0
    i = 0
    quote = None
    while i < len(css):
        ch = css[i]
        nxt = css[i + 1] if i + 1 < len(css) else ""
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in {"'", '"'}:
            quote = ch
        elif ch == "/" and nxt == "*":
            end = css.find("*/", i + 2)
            assert end != -1, "unterminated CSS comment"
            i = end + 2
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            assert depth >= 0, "unexpected closing CSS brace"
        i += 1
    assert quote is None, "unterminated CSS string"
    assert depth == 0, "unbalanced CSS braces"


def _assert_generated_js_parses(js: str) -> None:
    node = shutil.which("node")
    assert node, "Node.js is required to syntax-check the generated Map asset"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "generated-aqua-smart-tour.js"
        path.write_text(js, encoding="utf-8")
        checked = subprocess.run(
            [node, "--check", str(path)],
            text=True,
            capture_output=True,
            check=False,
        )
    assert checked.returncode == 0, checked.stderr


def _generated_function(js: str, name: str, next_name: str) -> str:
    start = js.index(f"function {name}(")
    tail = js[start + 1 :]
    next_match = re.search(rf"(?:async\s+)?function\s+{re.escape(next_name)}\(", tail)
    assert next_match, f"generated function {next_name} missing"
    end = start + 1 + next_match.start()
    return js[start:end].rstrip()


def _assert_generated_ios_long_press_behavior(js: str) -> None:
    """Execute the served functions with an iPhone-like touch lifecycle in Node."""
    node = shutil.which("node")
    assert node, "Node.js is required for the generated iPhone Map behavior test"
    bind_fn = _generated_function(js, "bindMainMapLongPress", "renderFreeCard")
    card_fn = _generated_function(js, "renderFreeCard", "selectFreeDestination")
    script = f"""
const listeners={{}};
const cardHandlers={{}};
const mapEl={{
  dataset:{{}},
  addEventListener(name, fn){{ listeners[name]=fn; }},
  getBoundingClientRect(){{ return {{left:10,top:20}}; }}
}};
const card={{
  hidden:true,
  innerHTML:'',
  querySelector(sel){{ return {{addEventListener(name,fn){{cardHandlers[sel]=fn;}}}}; }}
}};
let map=null;
const selected=[];
let started=null;
function $(sel){{ if(sel==='#mainMap')return mapEl;if(sel==='#aqst-free-card')return card;return null; }}
function mainMap(){{ return map; }}
function esc(v){{ return String(v??''); }}
function startNavigation(point){{ started=point; }}
function selectFreeDestination(point){{ selected.push(point);renderFreeCard(point); }}
Object.defineProperty(globalThis,'navigator',{{value:{{vibrate(){{}}}},configurable:true}});
{bind_fn}
{card_fn}

// This is the real regression: the handler must bind before Leaflet/Alpine has
// exposed mainMap(). The map becomes available only after the Map page opens.
bindMainMapLongPress();
if(mapEl.dataset.aqLongPress!=='2')throw new Error('long-press did not bind before mainMap existed');
if(typeof listeners.touchstart!=='function'||typeof listeners.touchmove!=='function')throw new Error('touch handlers missing');
map={{containerPointToLatLng(point){{return {{lat:point[1]/10,lng:point[0]/10}};}}}};
listeners.touchstart({{touches:[{{clientX:30,clientY:50}}]}});
setTimeout(()=>{{
  if(selected.length!==1)throw new Error('hold did not select a destination');
  if(card.hidden)throw new Error('destination card did not render');
  if(typeof cardHandlers['.aqst-free-start']!=='function')throw new Error('start route handler missing');
  cardHandlers['.aqst-free-start']();
  if(!started||started.free!==true)throw new Error('manual destination did not enter navigation');

  // A drag greater than the movement threshold must cancel the second hold.
  listeners.touchstart({{touches:[{{clientX:30,clientY:50}}]}});
  listeners.touchmove({{touches:[{{clientX:55,clientY:75}}]}});
  setTimeout(()=>{{
    if(selected.length!==1)throw new Error('drag falsely created a destination');
  }},760);
}},760);
"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "phase2-ios-longpress.mjs"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            [node, str(path)],
            text=True,
            capture_output=True,
            timeout=4,
            check=False,
        )
    assert result.returncode == 0, result.stderr or result.stdout


def test_phase1_generated_map_ui_contract_is_compact_and_unique():
    html = _asset("/")
    js = _asset("/aqua-smart-tour.js")
    css = _asset("/aqua-smart-tour.css")

    map_match = re.search(r'<section x-show="page===\'map\'".*?</section>', html, re.S)
    assert map_match, "Map section missing from generated root HTML"
    map_html = map_match.group(0)

    for label in ("موقعیت من", "اطراف من", "بهینه‌سازی مسیر"):
        assert map_html.count(f">{label}<") == 1, label
    assert 'grid-template-columns:repeat(3,minmax(0,1fr))!important' in css
    assert '.no-print>.aqst-route-pair{display:contents!important}' in css

    assert "aqst-customer-search" in js
    assert "searchCustomers(q)" in js
    assert "selectCustomer(c)" in js
    assert "aqst-search-results" in js
    assert '#aq-smart-tour .aqst-searchbar input{height:38px!important' in css
    assert '#aq-smart-tour .aqst-results{top:43px!important}' in css

    assert "aqst-free-search" in js
    assert "aqst-map-place-q" in js
    assert "searchFreePlaces" in js
    assert "/api/map/smart-tour/place-search" in js

    assert js.count("host.id='aq-smart-tour'") == 1
    assert js.count("controls.id='aqst-controls'") == 1
    assert js.count("box.id='aqst-free-search'") == 1

    _assert_css_structurally_valid(css)
    _assert_generated_js_parses(js)


def test_phase2_generated_long_press_runs_before_map_init_and_drag_cancels():
    js = _asset("/aqua-smart-tour.js")
    css = _asset("/aqua-smart-tour.css")

    assert js.count("function bindMainMapLongPress()") == 1
    assert "const el=$('#mainMap');if(!el||el.dataset.aqLongPress==='2')return" in js
    assert "const m=mainMap();if(!m)return;const ll=m.containerPointToLatLng" in js
    assert "e.pointerType==='touch'" in js
    assert "['touchend','touchcancel']" in js
    assert "capture:true" in js

    # Execute the generated code rather than only checking marker strings.
    _assert_generated_ios_long_press_behavior(js)

    assert "Aqua Map Phase 2 — iPhone long-press + compact selected customer correction" in css
    assert 'width:calc(100% + 8px)!important' in css
    assert 'height:40px!important' in css
    assert 'grid-template-columns:minmax(0,1fr) auto!important' in css
    assert 'max-height:72px!important' in css
    assert 'flex-direction:row!important' in css
    assert '-webkit-touch-callout:none!important' in css

    _assert_css_structurally_valid(css)
    _assert_generated_js_parses(js)


def test_phase2_place_search_falls_back_when_neshan_search_is_not_licensed(monkeypatch):
    def fail_neshan(*args, **kwargs):
        raise RuntimeError("Api Key services not match")

    requested = {}

    def fake_geocoder(url, timeout=12):
        requested["url"] = url
        requested["timeout"] = timeout
        return [{
            "name": "کرج",
            "display_name": "کرج، بخش مرکزی شهرستان کرج، استان البرز، ایران",
            "lat": "35.8327",
            "lon": "50.9915",
            "type": "city",
            "address": {"city": "کرج", "state": "البرز"},
        }]

    monkeypatch.setattr(map_search.neshan, "_neshan_get", fail_neshan)
    monkeypatch.setattr(map_search.neshan, "geocode_address", fail_neshan)
    monkeypatch.setattr(map_search.app_routing, "_fetch_json", fake_geocoder)

    payload, status = map_search._place_search_payload("کرج", 35.69, 51.09)
    assert status == 200
    assert payload["provider"] == "aquagold-geocoder"
    assert payload["fallback"] is True
    assert payload["items"] == [{
        "title": "کرج",
        "address": "کرج، بخش مرکزی شهرستان کرج، استان البرز، ایران",
        "region": "کرج",
        "type": "city",
        "latitude": 35.8327,
        "longitude": 50.9915,
    }]
    assert "countrycodes=ir" in requested["url"]
    assert requested["timeout"] == 10


def test_phase1_startup_and_login_assets_still_render_unchanged_surfaces():
    html = _asset("/")
    assert 'id="aqua-boot-20260906"' in html
    assert '/assets/aquagold-loading-v20260906b.jpg?v=2' in html
    assert '/assets/brand-sector.svg' in html

    client = app.test_client()
    loading = client.get('/assets/aquagold-loading-v20260906b.jpg')
    brand = client.get('/assets/brand-sector.svg')
    assert loading.status_code == 200
    assert loading.mimetype == 'image/jpeg'
    assert brand.status_code == 200
    assert brand.mimetype in {'image/svg+xml', 'image/svg'}
