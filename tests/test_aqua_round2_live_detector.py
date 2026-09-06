from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def _load_detector():
    src = (ROOT / "aqua_round2_fix.py").read_text(encoding="utf-8")
    start = src.index("FA_NORMALISE")
    end = src.index("aqua_ai._needs_live_web_search")
    ns = {"re": re}
    exec(src[start:end], ns)
    return ns["_needs_live_web_search"]

def test_tehran_weather_is_live_search():
    needs = _load_detector()
    assert needs("آب و هوای تهران")
    assert needs("هوای تهران")
    assert needs("قیمت دلار امروز")
    assert not needs("سلام آریا")


def test_weather_does_not_use_generic_aria_down_error():
    src = (ROOT / "aqua_round2_fix.py").read_text(encoding="utf-8")
    targeted = (ROOT / "aqua_targeted_fix.py").read_text(encoding="utf-8")
    assert "_is_weather_query" in src
    assert "هیچ حدسی نزدم" in src
    assert "آب و هوای تهران"  # keep file utf-8
    assert "or _is_weather_query(text)" in targeted
    assert "الان نتونستم آب‌وهوای زنده را از وب بگیرم" in targeted
