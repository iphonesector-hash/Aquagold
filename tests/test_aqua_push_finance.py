from pathlib import Path
R=Path(__file__).resolve().parents[1]
def src(n): return (R/n).read_text(encoding='utf-8')
def test_push_runtime_contract():
    p=src('aqua_push_runtime.py'); assert '/api/push/subscribe' in p and 'webpush(' in p and 'send_push(' in p
    assert 'aqua-system-polish.js' not in p and '@app_v3.app.after_request' not in p
def test_push_service_worker_contract():
    s=src('sw.js'); assert "addEventListener('push'" in s and 'showNotification' in s and 'notificationclick' in s
def test_finance_polish_contract():
    base=src('ui-v3-base.js'); ui=src('ui-v4-enhancements.js')
    assert "type:'line'" in base and "type:'doughnut'" in base and "type:'polarArea'" in base
    assert 'financeDonutChart' in ui and 'financePolarChart' in ui
    assert 'aq-float no-print' not in ui
    assert not (R/'aqua-system-polish.js').exists()

def test_scoped_ui_contract():
    base=src('ui-v3-base.js'); html=src('index.html'); final=src('ui-v4-finalize.js')
    assert 'persianNumericDate' in base and '\\u2066' in base and '\\u2069' in base
    assert 'enableAquaPush' in base and 'refreshPushStatus' in base
    assert 'safe-area-inset-top' in html and '20260901-stable1' in html
    assert "const verify=await fetch('/api/session'" in final
def test_private_finance_bale_contract():
    p=src('aqua_finance_runtime.py'); assert "st.get('chat_id')" in p and 'sendPhoto' in p and 'last_finance_image' in p
