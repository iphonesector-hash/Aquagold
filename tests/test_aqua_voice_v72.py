from pathlib import Path
R=Path(__file__).resolve().parents[1]
def src(n): return (R/n).read_text(encoding="utf-8")
def test_today_sales_alias_is_postgres_safe():
 a=src("aqua_ai.py"); assert "::int as hour_of_day" in a and 'point["hour"] = point.pop("hour_of_day"' in a
def test_tts_has_retry_and_persian_fallback_model():
 a=src("aqua_ai.py"); assert "eleven_multilingual_v2" in a and "aqua_tts_failed" in a and "range(3)" in a
def test_voice_transcription_does_not_deadlock_send():
 j=src("aqua-ai.js"); assert "صدای شما به متن تبدیل شد" in j and "if(this.aquaInput)await this.sendAqua()" not in j
def test_safari_tts_is_single_flight():
 j=src("aqua-ai.js"); assert "aquaSpeaking" in j and "آریا در حال صحبت است" in j and "this.aquaAudio" in j
def test_v72_cache_bust():
 i=src("index.html"); assert "/aqua-ai.js?v=20260827-v72" in i
