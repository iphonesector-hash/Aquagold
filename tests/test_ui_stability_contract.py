from pathlib import Path


def test_active_latest_ui_layer_is_alpine_safe():
    injector = Path('aqua_round4_ui_fix.py').read_text(encoding='utf-8')
    safe = Path('aqua-round6-safe-ui.js').read_text(encoding='utf-8')

    assert '/aqua-round6-safe-ui.js' in injector
    assert '<script src="/aqua-round6-user-fixes.js' not in injector
    assert 'new MutationObserver' not in safe
    assert '.observe(document.documentElement' not in safe
    assert 'UI-STABILITY' in safe

    prefix = safe.split('window.app=function', 1)[0]
    forbidden_top_level_calls = (
        '\n  patchCustomerTemplate();',
        '\n  patchDashboardDueAlarm();',
        '\n  removeManualSmartDuplicates();',
        '\n  mountSafeUi(',
    )
    for marker in forbidden_top_level_calls:
        assert marker not in prefix


def test_known_bad_round6_layer_is_not_injected():
    injector = Path('aqua_round4_ui_fix.py').read_text(encoding='utf-8')
    assert 'aqua-round6-user-fixes.js?v=' not in injector
