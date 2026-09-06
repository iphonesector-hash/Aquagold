from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "aqua-bale-standalone" / "app.py"


def code():
    return APP.read_text(encoding="utf-8")


def test_standalone_runtime_is_syntax_valid_and_independent():
    ast.parse(code())
    assert "import app_v3" not in code()
    assert (ROOT / "aqua-bale-standalone" / "vercel.json").exists()
    assert (ROOT / "aqua-bale-standalone" / "aqua-bale-miniapp.html").exists()
    assert (ROOT / "aqua-bale-standalone" / "assets" / "aquagold-bale-mark.svg").exists()


def test_group_assistant_fails_closed_and_never_answers_private():
    text = code()
    webhook = text[text.index("def bale_webhook"):text.index("def activate_bale")]
    assert "chat_type not in GROUP_TYPES" in webhook
    assert '"private_or_non_group"' in webhook
    assert "if not allowed or str(chat_id) not in allowed" in webhook
    assert '"chat_not_allowed"' in webhook
    assert "if ASSISTANT_WAKE in flat" in webhook
    assert webhook.index("chat_type not in GROUP_TYPES") < webhook.index("if ASSISTANT_WAKE in flat")
    assert webhook.index("if not allowed or str(chat_id) not in allowed") < webhook.index("if ASSISTANT_WAKE in flat")


def test_assistant_supports_requested_operational_questions():
    text = code()
    assert "_assistant_done_today" in text
    assert "_assistant_sales_today" in text
    assert "_assistant_cancelled_today" in text
    assert "_assistant_customer_status" in text
    assert "کارهای انجام‌شده امروز" in text
    assert "فروش امروز" in text
    assert "کنسلی‌های امروز" in text
    assert "دریافتی" in text
    assert "cancel_reason" in text


def test_existing_group_job_ingestion_is_preserved():
    text = code()
    webhook = text[text.index("def bale_webhook"):text.index("def activate_bale")]
    assert "_extract_job(text)" in webhook
    assert "insert into bale_jobs" in webhook
    assert "on conflict(chat_id,message_id) do nothing" in webhook


def test_bale_activation_points_webhook_to_standalone_host_and_sends_web_app_button():
    text = code()
    block = text[text.index("def activate_bale"):]
    assert 'request.host_url.rstrip("/")' in block
    assert '"setWebhook"' in block
    assert '"web_app"' in block
    assert '"allowed_chat_ids"' in block
