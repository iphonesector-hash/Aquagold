from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source():
    return (ROOT / "bale_inbox_guard.py").read_text(encoding="utf-8")


def test_aqua_command_is_intercepted_before_work_intake():
    text = source()
    assert 'command == "/aqua"' in text
    assert '"aqua_launcher": True' in text
    assert 'return _original_webhook(secret)' in text


def test_aqua_command_uses_bale_main_miniapp_direct_link():
    text = source()
    assert 'https://ble.ir/aqua_goldbot?startapp' in text
    assert '"inline_keyboard"' in text
    assert '"💧 باز کردن AquaGold"' in text
    assert 'لطفاً برای ورود به مینی‌اپ آکوا، دکمه زیر را بزنید' in text


def test_aqua_command_stays_scoped_to_group_and_allowlist():
    text = source()
    assert '{"group", "supergroup"}' in text
    assert '"chat_not_allowed"' in text
