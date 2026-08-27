"""Static contracts for the premium dashboard and its lazy-mounted controls."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_premium_assets_load_before_alpine_boots():
    index = source("index.html")
    required = [
        "/ui-v3-base.js",
        "/ui-v4-enhancements.js",
        "/ui-v4-finalize.js",
        "/ui-commerce.js",
        "/ui-visual-polish.js",
        "/aqua-premium.js",
    ]
    alpine = index.index("/vendor/alpinejs-3.14.9.min.js")
    assert all(index.index(path) < alpine for path in required)
    assert "/aqua-premium.css" in index
    assert "/assets/aqua-wave.webp" in source("aqua-premium.css")
    assert "document.write" not in index


def test_dashboard_actions_have_a_real_destination_and_icon():
    premium = source("aqua-premium.js")
    index = source("index.html")
    commerce = source("ui-commerce.js")
    icons = source("assets/aqua-icons.svg")
    action_block = premium.split("quickActions:", 1)[1].split("]", 1)[0]
    actions = re.findall(r"\{id: '([^']+)'.*?icon: '([^']+)'", action_block)
    assert {action for action, _ in actions} == {
        "customers", "services", "smart", "invoices", "products", "finance", "map", "settings",
        "bale-jobs", "aqua-ai",
    }
    dynamic = {"bale-jobs": source("bale-ui.js"), "aqua-ai": source("aqua-ai.js")}
    for destination, icon in actions:
        page_markup = f"page==='{destination}'"
        assert page_markup in index or page_markup in commerce or page_markup in dynamic.get(destination, "")
        assert f'id="i-{icon}"' in icons


def test_every_literal_premium_icon_reference_exists_in_sprite():
    combined = "\n".join(
        source(name)
        for name in ("index.html", "aqua-premium.js", "ui-v4-enhancements.js", "ui-commerce.js")
    )
    icons = source("assets/aqua-icons.svg")
    referenced = set(re.findall(r"icon\('([^']+)'", combined))
    available = set(re.findall(r'<symbol id="i-([^"]+)"', icons))
    assert referenced <= available


def test_lazy_modules_wait_for_authenticated_dom_before_marking_mounted():
    commerce = source("ui-commerce.js")
    enhancements = source("ui-v4-enhancements.js")
    commerce_guard = commerce.index("if(!main){setTimeout(()=>this.mountCommerce(),120);return}")
    commerce_flag = commerce.index("this.commerceMounted=true")
    enhancement_guard = enhancements.index(
        "if(!document.querySelector('main.content')){setTimeout(()=>this.mountEnhancements(),120);return}"
    )
    enhancement_flag = enhancements.index("this.enhancementsMounted=true")
    assert commerce_guard < commerce_flag
    assert enhancement_guard < enhancement_flag


def test_recovery_service_worker_is_network_only_and_clears_stale_caches():
    worker = source("sw.js")
    assert "aquagold-network-only-recovery" in worker
    assert "await Promise.all(keys.map(key => caches.delete(key)))" in worker
    assert "event.respondWith(fetch(request))" in worker
    assert "cache.add" not in worker


def test_login_bootstrap_is_deterministic_and_session_verified():
    finalizer = source("ui-v4-finalize.js")
    assert "this.authReady=false;this.token=false;this.user=null" in finalizer
    assert "fetch('/api/session'" in finalizer
    assert "credentials:'same-origin'" in finalizer
    assert "if(r.ok)" in finalizer
    assert "this.user=d.user;this.token=true;this.page='dashboard'" in finalizer
    assert "const r=await fetch('/api/login'" in finalizer
    assert "const verify=await fetch('/api/session'" in finalizer
    assert "if(!verify.ok||!session?.user)" in finalizer
    assert "this.user=session.user;this.token=true;this.authReady=true;this.page='dashboard'" in finalizer


def test_login_copy_is_present_before_alpine_reveals_page():
    index = source("index.html")
    alpine = index.index("/vendor/alpinejs-3.14.9.min.js")
    copy = index.index("پنل ورودی اکوا گلد نوشته شده توسط peyman.sector")
    assert copy > alpine
    assert "AquaGold CRM v7." in index
    assert "نسخه v7." in index


def test_bale_modal_backdrops_are_fail_safe_hidden():
    bale = source("bale-ui.js")
    assert 'x-cloak x-show="baleCompleteJob"' in bale
    assert 'x-cloak x-show="baleCancelJob"' in bale
    assert bale.count('style="display:none"') >= 2
