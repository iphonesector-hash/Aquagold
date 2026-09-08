from app import app


def test_generated_navigation_asset_has_final_guards():
    client = app.test_client()
    response = client.get('/aqua-smart-tour.js')
    assert response.status_code == 200
    js = response.get_data(as_text=True)

    assert 'async async function initNavMap' not in js
    assert 'await aqAcquireWakeLock()const' not in js
    assert 'async function startNavigation(target)' in js
    assert 'function aqAcquireWakeLock()' in js
    assert 'window.__aquaIosLongPress20260908' in js
    assert "addEventListener('touchstart'" in js
    assert 'offCount>=4' in js
    assert 'static.neshan.org/sdk/leaflet/1.4.0/leaflet.js' in js


def test_generated_navigation_css_has_mobile_destination_overlay():
    client = app.test_client()
    response = client.get('/aqua-smart-tour.css')
    assert response.status_code == 200
    css = response.get_data(as_text=True)
    assert 'iOS destination long-press feedback' in css
    assert '#aqst-free-card:not([hidden])' in css
    assert 'Aqua navigation smooth motion + raised route/marker' in css
