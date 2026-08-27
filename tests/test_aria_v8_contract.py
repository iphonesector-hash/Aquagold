from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def src(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_aria_v8_is_loaded_after_operational_runtime():
    app = src("app.py")
    assert "import operational_v8" in app
    assert "import aria_v8" in app
    assert app.index("import aria_v8") > app.index("import operational_v8")
    injector = src("aria_v8.py")
    assert '/aria-v8.js?v=20260828-v8' in injector


def test_iphone_recorder_flushes_chunks_and_uses_timeslices():
    js = src("aria-v8.js")
    assert "isTypeSupported" in js
    assert "requestData" in js
    assert "rec.start(250)" in js
    assert "new Blob(chunks" in js
    assert "audio/mp4" in js


def test_voice_transcript_is_preserved_and_directly_sent():
    js = src("aria-v8.js")
    assert "this.aquaInput=spoken" in js
    assert "sendAquaVoiceText(spoken)" in js
    assert "'/aqua-ai/chat'" in js
    assert "this.aquaInput=text" in js
    assert "ارسال خودکار انجام نشد" in js


def test_aria_v8_has_no_fragile_navigation_or_dom_watchers():
    combined = src("aria-v8.js") + src("aria_v8.py")
    assert "location.reload" not in combined
    assert "location.replace" not in combined
    assert "MutationObserver" not in combined
