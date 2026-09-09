import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from app import app


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


def test_phase1_generated_map_ui_contract_is_compact_and_unique():
    html = _asset("/")
    js = _asset("/aqua-smart-tour.js")
    css = _asset("/aqua-smart-tour.css")

    map_match = re.search(r'<section x-show="page===\'map\'".*?</section>', html, re.S)
    assert map_match, "Map section missing from generated root HTML"
    map_html = map_match.group(0)

    # The permanent top action group remains a single logical group with exactly
    # one instance of each required action. CSS flattens the existing route pair
    # on narrow screens so the three buttons participate in the same 3-column grid.
    for label in ("موقعیت من", "اطراف من", "بهینه‌سازی مسیر"):
        assert map_html.count(f">{label}<") == 1, label
    assert 'grid-template-columns:repeat(3,minmax(0,1fr))!important' in css
    assert '.no-print>.aqst-route-pair{display:contents!important}' in css
    assert 'height:36px!important' in css

    # Customer search is the existing functional control, only compacted. Its
    # query/results/selection functions must still survive final asset generation.
    assert "aqst-customer-search" in js
    assert "searchCustomers(q)" in js
    assert "selectCustomer(c)" in js
    assert "aqst-search-results" in js
    assert '#aq-smart-tour .aqst-searchbar input{height:38px!important' in css
    assert '#aq-smart-tour .aqst-results{top:43px!important}' in css

    # Address/place search remains present and usable; Phase 1 must not remove it.
    assert "aqst-free-search" in js
    assert "aqst-map-place-q" in js
    assert "searchFreePlaces" in js
    assert "/api/map/smart-tour/place-search" in js

    # Build guards prevent duplicate ownership of the Map enhancement/control set.
    assert js.count("host.id='aq-smart-tour'") == 1
    assert js.count("controls.id='aqst-controls'") == 1
    assert js.count("box.id='aqst-free-search'") == 1

    _assert_css_structurally_valid(css)
    _assert_generated_js_parses(js)


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
