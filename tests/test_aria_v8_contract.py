from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def src(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_aria_v8_is_loaded_after_operational_runtime():
    app = src("app.py")
    index = src("index.html")
    assert "import operational_v8" in app
    assert "import aria_v8" not in app
    assert index.index("/aria-v8.js") < index.index("/ui-detail-v8.js")


def test_iphone_recorder_flushes_chunks_and_uses_timeslices():
    js = src("aria-v8.js")
    assert "MediaRecorder.isTypeSupported" in js
    assert "requestData" in js
    assert "rec.start(250)" in js
    assert "new Blob(chunks" in js


def test_voice_transcript_is_preserved_and_directly_sent():
    js = src("aria-v8.js")
    base = src("aqua-ai.js")
    assert "this.aquaInput=spoken" in js
    assert "sendAquaVoiceText(spoken)" in js
    assert "this.submitAquaText?.(text,'voice')" in js
    assert "'/aqua-ai/chat'" in base
    assert "this.aquaInput=text" in js
    assert "ارسال خودکار انجام نشد" in js


def test_text_and_voice_share_one_auto_send_and_auto_speak_pipeline():
    base = src("aqua-ai.js")
    aria = src("aria-v8.js")
    assert "await this.primeAquaAudio?.()" in base
    assert "await this.speakAqua(m.content)" in base
    assert "this.aquaInput=text;this.aquaVoiceState='ready'" in base
    assert "setTimeout(()=>this.speakAqua" not in base
    assert aria.count("'/aqua-ai/chat'") == 0


def test_aria_v8_has_no_fragile_navigation_or_dom_watchers():
    combined = src("aria-v8.js") + src("index.html")
    assert "location.reload" not in combined
    assert "location.replace" not in combined
    assert "MutationObserver" not in combined
