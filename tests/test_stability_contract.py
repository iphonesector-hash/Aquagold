from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_security_audit_uses_non_vulnerable_cryptography_release():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "cryptography==50.0.0" in requirements


def test_premium_layer_stabilizes_dynamic_commerce_without_changing_markup_contract():
    premium = (ROOT / "aqua-premium.js").read_text(encoding="utf-8")
    assert "ensureCommerceReady" in premium
    assert "hydrateDynamicSections" in premium
    assert "this.mountCommerce?.();" in premium
    assert "this.refreshCommerce()" in premium
    assert "Alpine.initTree(section)" in premium
    assert "['products', 'invoices'].includes(page)" in premium


def test_first_party_aqua_ai_and_commerce_are_loaded_before_alpine():
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    premium = index.index('/aqua-premium.js')
    aqua_ai = index.index('/aqua-ai.js')
    commerce = index.index('/commerce-guidance.js')
    alpine = index.index('/vendor/alpinejs-3.14.9.min.js')
    assert premium < aqua_ai < commerce < alpine


def test_farangis_is_not_registered_in_runtime_entrypoint():
    app_py = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "import aqua_ai" in app_py
    assert "import farangis_bridge" not in app_py


def test_dynamic_ai_mount_is_explicitly_hydrated():
    aqua_ai = (ROOT / "aqua-ai.js").read_text(encoding="utf-8")
    assert "Alpine.initTree(section)" in aqua_ai
    assert "Alpine.initTree(card)" in aqua_ai
