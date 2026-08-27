from pathlib import Path

R = Path(__file__).resolve().parents[1]


def src(name):
    return (R / name).read_text(encoding="utf-8")


def test_bale_done_routes_to_smart():
    bale = src("bale-ui.js")
    assert "sendBaleToSmart" in bale
    assert "انجام شد → ثبت هوشمند" in bale
    assert "oldSmartRegister" in bale


def test_bale_finalize_links_existing_smart_service():
    bridge = src("bale_bridge.py")
    assert "/api/bale/jobs/<job_id>/finalize" in bridge
    assert "raw_chat_input=%s" in bridge
    assert "smart_finalize" in bridge


def test_ai_settings_saved_feedback():
    ai = src("aqua-ai.js")
    assert "aquaSettingsSaved" in ai
    assert "خالی شدن فیلد کلیدها طبیعی است" in ai


def test_runtime_assets_are_cache_busted_without_pin_to_old_aqua_version():
    index = src("index.html")
    assert "AquaGold CRM v7.1" in index
    assert "/bale-ui.js?v=" in index
    assert "/aqua-ai.js?v=" in index
    assert "/ui-v4-finalize.js?v=" in index
