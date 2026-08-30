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


def test_v8_service_worker_caches_shell_but_never_api_and_handles_push():
    worker = source("sw.js")
    assert "aquagold-v8-rc2-shell" in worker
    assert "caches.keys()" in worker and "caches.delete" in worker
    assert "url.pathname.startsWith('/api/')" in worker
    assert "cache.addAll(SHELL)" in worker
    assert "event.request.mode==='navigate'" in worker
    assert "showNotification" in worker
    assert "notificationclick" in worker


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
    assert "location.reload" not in finalizer
    assert "location.replace" not in finalizer


def test_login_copy_is_present_before_alpine_reveals_page():
    index = source("index.html")
    alpine = index.index("/vendor/alpinejs-3.14.9.min.js")
    copy = index.index("پنل ورودی اکوا گلد نوشته شده توسط peyman.sector")
    assert copy > alpine
    assert "AquaGold CRM v8" in index
    assert "نسخه v8" in index


def test_bale_uses_only_smart_intake_completion_and_cancel_modal_is_hidden():
    bale = source("bale-ui.js")
    assert "sendBaleToSmart(j)" in bale
    assert "baleCompleteJob" not in bale
    assert "'/complete'" not in bale
    assert 'x-cloak x-show="baleCancelJob"' in bale
    assert 'style="display:none"' in bale


def test_operational_v8_removes_duplicate_floating_actions_and_excel_ui():
    finalizer = source("ui-v4-finalize.js")
    enhancements = source("ui-v4-enhancements.js")
    index = source("index.html")
    assert "aq-float" not in enhancements
    assert "downloadExcel" not in index
    assert ">Excel<" not in index
    assert "company-share" in finalizer


def test_runtime_has_no_legacy_monkeypatch_or_excel_export_layer():
    runtime = "\n".join(
        source(name)
        for name in ("app.py", "app_v3.py", "app_extras.py", "operational_v8.py", "aqua_ai.py", "bale_bridge.py")
    )
    assert not (ROOT / "app_fixes.py").exists()
    assert "app.view_functions" not in runtime
    assert "aqua_ai._groq_answer =" not in runtime
    assert "bale_bridge._extract_job =" not in runtime
    assert "/api/export.xlsx" not in runtime
    assert "openpyxl" not in runtime


def test_create_flows_lock_double_taps_and_voice_transcription_is_idempotent():
    base = source("ui-v3-base.js")
    commerce = source("ui-commerce.js")
    aria = source("aria-v8.js")
    timeline = source("ui-v4-finalize.js")
    for signature in (
        "async saveCustomer(){if(this.busy)return",
        "async createService(){if(this.busy)return",
        "async createExpense(){if(this.busy)return",
        "async createSettlement(){if(this.busy)return",
    ):
        assert signature in base
    assert "s.saveProduct=async function(){if(this.busy)return" in commerce
    assert "s.saveInvoice=async function(){if(this.busy)return" in commerce
    assert "'Idempotency-Key':crypto.randomUUID()" in aria
    assert "'Idempotency-Key':crypto.randomUUID()" in timeline


def test_tehran_date_has_fixed_rtl_order_and_separate_live_clock():
    finalizer = source("ui-v4-finalize.js")
    assert "`${parts.weekday} / ${day} / ${parts.month} / ${parts.year}`" in finalizer
    assert 'dir="rtl" style="unicode-bidi:isolate" x-text="tehranDate"' in finalizer
    assert 'dir="ltr" x-text="tehranTime"' in finalizer
