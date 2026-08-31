from pathlib import Path
R=Path(__file__).resolve().parents[1]
def src(n): return (R/n).read_text(encoding='utf-8')
def test_push_runtime_contract():
    p=src('aqua_push_runtime.py'); assert '/api/push/subscribe' in p and 'webpush(' in p and 'send_push(' in p
def test_push_service_worker_contract():
    s=src('sw.js'); assert "addEventListener('push'" in s and 'showNotification' in s and 'notificationclick' in s
def test_finance_polish_contract():
    j=src('aqua-system-polish.js'); assert "type:'line'" in j and "type:'doughnut'" in j and "type:'polarArea'" in j and '.aq-float' in j
def test_private_finance_bale_contract():
    p=src('aqua_finance_runtime.py'); assert "st.get('chat_id')" in p and 'sendPhoto' in p and 'last_finance_image' in p
