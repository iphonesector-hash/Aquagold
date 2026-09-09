from app import app


def _asset(path: str) -> str:
    response = app.test_client().get(path)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_final_map_navigation_runtime_keeps_search_and_navigation_guards():
    js = _asset('/aqua-smart-tour.js')

    # Restored Map UI must stay present while Navigation is patched.
    assert 'aqst-customer-search' in js
    assert 'جست‌وجوی مشتری: نام، شماره یا آدرس' in js
    assert 'aqst-map-place-q' in js
    assert 'جستجوی آدرس یا مکان روی نقشه' in js
    assert 'function aqFinalCompactMapUi()' in js

    # False reroute: real route-segment projection + GPS accuracy hysteresis.
    assert 'function aqFinalProject(pos,route)' in js
    assert 'p.coords.accuracy' in js
    assert 'offCount>=4' in js
    assert 'lastReroute>40000' in js
    assert 'if(proj.d>100)ST.nav.offCount++' not in js

    # One maneuver card only, Neshan-compatible iPhone fallback, smooth motion.
    assert "const next=$('#aqst-next-strip');if(next)next.hidden=true" in js
    assert 'static.neshan.org/sdk/leaflet/1.4.0/leaflet.js' in js
    assert 'function aqFinalAnimateMarker' in js
    assert "'line-color':'#8b2cff'" in js

    # Long press and wake lock must survive generated-asset composition.
    assert "addEventListener('touchstart'" in js
    assert 'aqFinalAcquireWakeLock' in js
    assert 'aqFinalInstallWakeGuards();await aqFinalAcquireWakeLock();' in js

    # Guard known generated-runtime syntax regressions.
    assert 'async async function' not in js
    assert 'await aqFinalAcquireWakeLock()const' not in js
    assert 'async function startNavigation(target)' in js


def test_final_map_navigation_css_is_compact_and_mobile_safe():
    css = _asset('/aqua-smart-tour.css')

    assert 'Aqua final Map/Navigation guard — PR29 20260909' in css
    assert '.aq-map-compact-actions' in css
    assert 'grid-template-columns:repeat(3,minmax(0,1fr))' in css
    assert '#aq-smart-tour.aq-map-ui-compact .aqst-searchbar input' in css
    assert 'height:40px!important' in css
    assert '#aqst-nav .aqst-next-strip{display:none!important}' in css
    assert '#8b2cff' in css
    assert '#aqst-free-card:not([hidden])' in css
    assert 'bottom:calc(94px + env(safe-area-inset-bottom,0px))' in css


def test_resilient_place_search_remains_the_final_search_handler():
    handler = app.view_functions['smart_tour_place_search']
    names = []
    current = handler
    while current is not None:
        names.append(getattr(current, '__name__', ''))
        current = getattr(current, '__wrapped__', None)
    assert '_resilient_place_search' in names
