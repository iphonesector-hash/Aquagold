from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def src(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_smart_intake_ai_uses_current_production_groq_model():
    ai = src("ai_intake.py")
    assert '"model": "openai/gpt-oss-120b"' in ai
    assert '"response_format": {"type": "json_object"}' in ai
    assert "local-fallback-v8" in ai


def test_live_questions_route_to_compound_mini_first():
    ops = src("operational_v8.py")
    assert 'for model in ("groq/compound-mini", "groq/compound")' in ops
    assert "LIVE_HINTS" in ops and "دلار" in ops and "امروز" in ops
