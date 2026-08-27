from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def src(n): return (ROOT/n).read_text(encoding="utf-8")
def test_optional_modules_are_isolated():
    b=src("bale-ui.js"); f=src("ui-v4-finalize.js")
    assert "enhancement mount isolated" in b
    assert "mountAquaAI" in f and "baleMount" in f
def test_visual_layer_is_passive():
    v=src("ui-visual-polish.js")
    assert "MutationObserver" not in v and "pointerdown" not in v
    assert "pointer-events:none!important" in v and "SECTOR" in v
def test_notification_badge_can_be_read():
    e=src("ui-v4-enhancements.js"); i=src("index.html")
    assert "notificationBadgeCount" in e and "aq_notifications_seen" in e
    assert '@click="openNotifications"' in i
def test_v69_cache_busts_first_party_runtime():
    i=src("index.html")
    for name in ["ui-v3-base.js","ui-v4-enhancements.js","ui-commerce.js","ui-visual-polish.js","aqua-premium.js","aqua-ai.js","bale-ui.js","ui-v4-finalize.js"]:
        assert f"/{name}?v=20260827-v69" in i
