from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_today_sales_alias_is_postgres_safe():
    aqua = source("aqua_ai.py")
    assert "::int as hour_of_day" in aqua
    assert 'point["hour"] = point.pop("hour_of_day"' in aqua


def test_tts_has_retry_and_persian_fallback_model():
    aqua = source("aqua_ai.py")
    assert "eleven_multilingual_v2" in aqua
    assert "aqua_tts_failed" in aqua
    assert "range(3)" in aqua


def test_legacy_auto_speak_is_migrated_but_future_off_choice_is_respected():
    aqua = source("aqua_ai.py")
    assert '"auto_speak": True' in aqua
    assert "VOICE_UI_SETTINGS_VERSION = 2" in aqua
    assert 'stored["voice_ui_settings_version"] = VOICE_UI_SETTINGS_VERSION' in aqua
    assert 'if int(stored.get("voice_ui_settings_version") or 0) < VOICE_UI_SETTINGS_VERSION' in aqua


def test_canonical_voice_controller_is_the_only_injected_runtime():
    controller = source("aqua_voice_injector.py")
    assert 'src="/aqua-voice-ui.js?v=20260831-stable2"' in controller
    assert "aqua-voice-runtime-hotfix|aqua-ios-tts-patch|aqua-voice-ui" in controller
    voice_js = controller.split('VOICE_UI_JS = r"""', 1)[1].split('"""', 1)[0]
    assert "aqua-voice-ui-clean" not in voice_js


def test_voice_commit_happens_only_after_send_guards_pass():
    controller = source("aqua_voice_injector.py")
    guard = controller.index("if(this.aquaSendLock||this.aquaBusy||this.aquaSendPromise)")
    commit = controller.index("this.aquaVoiceCommittedRun=voiceRunId")
    assert guard < commit
    assert "return this.submitAquaText(text,'voice',runId)" in controller
    assert "this.aquaInput=sent?'':spoken" in controller


def test_send_path_has_feedback_and_exactly_one_inflight_promise():
    controller = source("aqua_voice_injector.py")
    assert "aquaSendPromise:null" in controller
    assert "پیام قبلی هنوز در حال ارسال است" in controller
    assert "if(this.aquaSendPromise===operation)this.aquaSendPromise=null" in controller
    assert "if(!this.aquaInput)this.aquaInput=text" in controller


def test_ios_system_speech_is_primed_in_direct_user_gestures():
    controller = source("aqua_voice_injector.py")
    assert "primeAquaDeviceSpeech" in controller
    assert "this.stopAquaSpeech();this.primeAquaDeviceSpeech();return this.submitAquaText" in controller
    assert "this.stopAquaSpeech();this.primeAquaDeviceSpeech();this.setAquaVoicePhase('starting')" in controller
    assert "label.includes('dariush')" in controller
    assert "label.includes('داریوش')" in controller
    assert "splitSpeech(text)" in controller


def test_speech_is_cleaned_and_prefers_enhanced_dariush():
    controller = source("aqua_voice_injector.py")
    assert "cleanSpeechText" in controller
    assert "Extended_Pictographic" in controller
    assert "label.includes('enhanced')" in controller
    assert "label.includes('compact')" in controller
    assert "utterance.rate=.9" in controller


def test_live_market_queries_use_web_search_with_compound_fallback():
    aqua = source("aqua_ai.py")
    assert "def _needs_live_web_search" in aqua
    assert '"دلار", "طلا", "سکه"' in aqua
    assert '"enabled_tools": ["web_search"]' in aqua
    assert '("groq/compound", "groq/compound-mini")' in aqua
    assert "هرگز قیمت روز را حدس نزن" in aqua


def test_device_speech_does_not_spend_elevenlabs_quota():
    controller = source("aqua_voice_injector.py")
    voice_js = controller.split('VOICE_UI_JS = r"""', 1)[1].split('"""', 1)[0]
    assert "/api/aqua-ai/speak" not in voice_js
    assert "window.speechSynthesis" in voice_js


def test_current_aqua_asset_is_cache_busted():
    index = source("index.html")
    assert "/aqua-ai.js?v=20260827-v76" in index
