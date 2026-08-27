from pathlib import Path

R = Path(__file__).resolve().parents[1]

def src(name):
    return (R / name).read_text(encoding="utf-8")


def test_today_sales_alias_is_postgres_safe():
    a = src("aqua_ai.py")
    assert "::int as hour_of_day" in a
    assert 'point["hour"] = point.pop("hour_of_day"' in a


def test_tts_has_retry_and_persian_fallback_model():
    a = src("aqua_ai.py")
    assert "eleven_multilingual_v2" in a
    assert "aqua_tts_failed" in a
    assert "range(3)" in a


def test_v8_voice_capture_flushes_and_auto_sends_without_form_submit():
    j = src("aria-v8.js")
    assert "requestData" in j
    assert "rec.start(250)" in j
    assert "sendAquaVoiceText(spoken)" in j
    assert "this.aquaInput=spoken" in j
    assert "'/aqua-ai/chat'" in j


def test_safari_tts_remains_interruptible():
    base = src("aqua-ai.js")
    finalizer = src("ui-v4-finalize.js")
    assert "stopAquaSpeech" in base
    assert "aquaSpeaking" in base
    assert "aquaPlayer" in base
    assert "stopAquaConversation" in finalizer


def test_v8_voice_controller_is_injected_last():
    app = src("app.py")
    injector = src("aria_v8.py")
    assert "import aria_v8" in app
    assert '/aria-v8.js?v=20260828-v8' in injector
