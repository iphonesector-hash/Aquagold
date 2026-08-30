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
    assert "eleven_v3_conversational" in a
    assert 'models = ["eleven_v3_conversational", "eleven_v3"]' in a
    assert "{408, 429, 500, 502, 503, 504}" in a
    assert "aqua_tts_failed" in a
    assert "range(3)" in a


def test_aria_provider_fallback_is_current_and_errors_are_controlled():
    ai = src("aqua_ai.py")
    assert "openai/gpt-oss-120b" in ai
    assert "llama-3.3-70b-versatile" not in ai
    assert "فعلاً ارتباط آریا" in ai
    assert "برای جلوگیری از نمایش اطلاعات قدیمی" in ai


def test_v8_voice_capture_flushes_and_auto_sends_without_form_submit():
    j = src("aria-v8.js")
    base = src("aqua-ai.js")
    assert "requestData" in j
    assert "rec.start(250)" in j
    assert "sendAquaVoiceText(spoken)" in j
    assert "this.aquaInput=spoken" in j
    assert "this.submitAquaText?.(text,'voice')" in j
    assert "'/aqua-ai/chat'" in base


def test_safari_tts_remains_interruptible():
    base = src("aqua-ai.js")
    finalizer = src("ui-v4-finalize.js")
    assert "stopAquaSpeech" in base
    assert "aquaSpeaking" in base
    assert "aquaPlayer" in base
    assert "await this.primeAquaAudio?.()" in base
    assert "await this.speakAqua(m.content)" in base
    assert "stopAquaConversation" in finalizer


def test_v8_voice_controller_has_deterministic_static_load_order():
    index = src("index.html")
    assert index.index("/ui-v4-finalize.js") < index.index("/aria-v8.js")
    assert index.index("/aria-v8.js") < index.index("/ui-detail-v8.js")
    assert index.index("/ui-detail-v8.js") < index.index("/vendor/alpinejs")
