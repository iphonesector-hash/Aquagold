"""Static contracts for the premium dashboard and its lazy-mounted controls."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_premium_assets_load_before_alpine_boots():
    index = source("index.html")
    required = ["/ui-v3-base.js", "/ui-v4-enhancements.js", "/ui-v4-finalize.js", "/ui-commerce.js", "/ui-visual-polish.js", "/aqua-premium.js"]
    alpine = index.index("/vendor/alpinejs-3.14.9.min.js")
    assert all(index.index(path) < alpine for path in required)
    assert "/aqua-premium.css" in index
    assert "document.write" not in index


def test_dashboard_actions_have_a_real_destination_and_icon():
    premium = source("aqua-premium.js")
    index = source("index.html")
    commerce = source("ui-commerce.js")
    icons = source("assets/aqua-icons.svg")
    block = premium.split("quickActions:", 1)[1].split("]", 1)[0]
    actions = re.findall(r"\{id: '([^']+)'.*?icon: '([^']+)'", block)
    assert {action for action, _ in actions} == {"customers", "services", "smart", "invoices", "products", "finance", "map", "settings"}
    for destination, icon in actions:
        assert f"page==='{destination}'" in index or f"page==='{destination}'" in commerce
        assert f'id="i-{icon}"' in icons


def test_every_literal_premium_icon_reference_exists_in_sprite():
    combined = "\n".join(source(name) for name in ("index.html", "aqua-premium.js", "ui-v4-enhancements.js", "ui-commerce.js"))
    icons = source("assets/aqua-icons.svg")
    assert set(re.findall(r"icon\('([^']+)'", combined)) <= set(re.findall(r'<symbol id="i-([^"]+)"', icons))


def test_lazy_modules_wait_for_authenticated_dom_before_marking_mounted():
    commerce = source("ui-commerce.js")
    enhancements = source("ui-v4-enhancements.js")
    assert commerce.index("if(!main){setTimeout(()=>this.mountCommerce(),120);return}") < commerce.index("this.commerceMounted=true")
    assert enhancements.index("if(!document.querySelector('main.content')){setTimeout(()=>this.mountEnhancements(),120);return}") < enhancements.index("this.enhancementsMounted=true")


def test_recovery_service_worker_is_network_only_and_clears_stale_caches():
    worker = source("sw.js")
    assert "aquagold-network-only-recovery" in worker
    assert "await Promise.all(keys.map(key => caches.delete(key)))" in worker
    assert "event.respondWith(fetch(request))" in worker
    assert "cache.add" not in worker


def test_login_is_session_verified_and_does_not_reload_the_document():
    finalizer = source("ui-v4-finalize.js")
    assert "this.authReady=false;this.token=false;this.user=null" in finalizer
    assert "fetch('/api/session'" in finalizer
    assert "fetch('/api/login'" in finalizer
    assert "const verify=await fetch('/api/session'" in finalizer
    assert "if(!verify.ok||!session?.user)" in finalizer
    assert "this.user=session.user;this.token=true;this.authReady=true;this.page='dashboard'" in finalizer
    assert "location.replace" not in finalizer


def test_login_copy_is_static_and_versioned():
    index = source("index.html")
    assert "پنل ورودی اکوا گلد نوشته شده توسط peyman.sector" in index
    assert "AquaGold CRM v6.4" in index
    assert "نسخه v6.4" in index
    assert "طراحی‌شده برای استفاده سریع روی iPhone" not in index


def test_entry_animation_has_rotating_rings_and_spinner():
    visual = source("ui-visual-polish.js")
    assert "aq-ring r1" in visual
    assert "aq-ring r2" in visual
    assert "aq-ring r3" in visual
    assert "aq-loader" in visual
    assert "@keyframes aqSpin" in visual
    assert "@keyframes aqSpinBack" in visual
