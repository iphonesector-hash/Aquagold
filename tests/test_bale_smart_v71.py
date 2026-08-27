from pathlib import Path
R=Path(__file__).resolve().parents[1]
def src(n): return (R/n).read_text(encoding="utf-8")
def test_bale_done_routes_to_smart():
 b=src("bale-ui.js"); assert "sendBaleToSmart" in b and "انجام شد → ثبت هوشمند" in b and "oldSmartRegister" in b
def test_bale_finalize_links_existing_smart_service():
 b=src("bale_bridge.py"); assert "/api/bale/jobs/<job_id>/finalize" in b and "raw_chat_input=%s" in b and "smart_finalize" in b
def test_ai_settings_saved_feedback():
 a=src("aqua-ai.js"); assert "aquaSettingsSaved" in a and "خالی شدن فیلد کلیدها طبیعی است" in a
def test_v71_assets():
 i=src("index.html"); assert "AquaGold CRM v7.1" in i and "/bale-ui.js?v=20260827-v71" in i and "/aqua-ai.js?v=20260827-v71" in i
