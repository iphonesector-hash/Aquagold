import subprocess
import tempfile
from pathlib import Path

import pytest

from app import app
import aqua_map_workspace as workspace


def _asset(path: str) -> str:
    with app.test_client() as client:
        response = client.get(path)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_phase4c_generated_map_workspace_is_collapsible_and_special_locations_are_wired():
    js = _asset('/aqua-smart-tour.js')
    css = _asset('/aqua-smart-tour.css')

    assert js.count('function aqSetupMapWorkspace()') == 1
    assert js.count('function aqLoadSpecialLocations()') == 1
    assert js.count('function aqPersistSpecialLocation()') == 1
    assert js.count('function aqDeleteSpecialLocation(item)') == 1
    assert 'aqst-map-tools-toggle' in js
    assert 'aqst-special-toggle' in js
    assert 'موقعیت‌های خاص' in js
    assert 'ذخیره موقعیت' in js
    assert '/api/map/special-locations' in js
    assert "selectFreeDestination({lat:item.lat,lng:item.lng,name:item.name" in js
    assert 'MutationObserver(aqDecorateFreeDestinationCard)' in js

    marker = '/* Aqua Map Phase 4C — decluttered normal Map workspace + special locations. */'
    assert css.count(marker) == 1
    assert '.aqst-glow-shell::before' in css
    assert 'conic-gradient' in css
    assert '@keyframes aqstMapGlowSpin' in css
    assert '#aqst-map-tools-content>.aqst-adopted-actions' in css
    assert 'height:min(72dvh,760px)!important' in css
    assert '.aqst-special-pin' in css

    # Previous approved phases must survive the normal-map declutter layer.
    assert 'function bindMainMapLongPress()' in js
    assert 'function searchFreePlaces()' in js
    assert 'function evaluateReroute(pos,coords,near,initial=false)' in js
    assert 'function voiceManeuverSignature(step)' in js
    assert 'function aqSetupPhase4BPanels()' in js


def test_phase4c_special_location_validation_and_per_user_key():
    with app.test_request_context('/api/map/special-locations'):
        from flask import request

        request.current_user = {'user_id': '11111111-2222-3333-4444-555555555555'}
        assert workspace._settings_key() == 'map_special_locations:11111111-2222-3333-4444-555555555555'
        item = workspace._location_payload({
            'name': 'بانک تست',
            'address': 'فردیس',
            'lat': 35.72,
            'lng': 50.98,
        })
        assert item['name'] == 'بانک تست'
        assert item['address'] == 'فردیس'
        assert item['lat'] == 35.72
        assert item['lng'] == 50.98
        assert item['category'] == 'special'
        assert item['id']

        with pytest.raises(Exception):
            workspace._location_payload({'name': 'x', 'lat': 120, 'lng': 50})


def test_phase4c_routes_exist_and_generated_javascript_stays_valid():
    rules = {(rule.rule, tuple(sorted(rule.methods - {'OPTIONS', 'HEAD'}))) for rule in app.url_map.iter_rules()}
    assert ('/api/map/special-locations', ('GET',)) in rules
    assert ('/api/map/special-locations', ('POST',)) in rules
    assert ('/api/map/special-locations/<location_id>', ('PATCH',)) in rules
    assert ('/api/map/special-locations/<location_id>', ('DELETE',)) in rules

    js = _asset('/aqua-smart-tour.js')
    html = _asset('/')
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'aqua-smart-tour-phase4c.js'
        path.write_text(js, encoding='utf-8')
        result = subprocess.run(
            ['node', '--check', str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    assert result.returncode == 0, result.stderr or result.stdout
    assert 'id="aqua-boot-20260906"' in html
    assert 'class="aq-auth-view"' in html
