from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def src(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_runtime_schema_is_migration_owned():
    app = src("app.py")
    ops = src("operational_v8.py")
    assert "import operational_v8" in app
    assert "pg_advisory_lock" not in app
    assert "create table if not exists" not in ops.lower()
    assert "_ensure_ops_schema" not in ops


def test_vapid_string_is_pywebpush_compatible_der_not_pem():
    ops = src("operational_v8.py")
    assert "serialization.Encoding.DER" in ops
    assert "serialization.PrivateFormat.PKCS8" in ops
    assert "urlsafe_b64encode" in ops


def test_company_settlements_match_report_range():
    ops = src("operational_v8.py")
    assert '_range_clause("s.settled_at")' in ops
    assert "from company_settlements s where" in ops


def test_postgres_report_aliases_are_explicit_and_safe():
    app = src("app_v3.py")
    ops = src("operational_v8.py")
    assert '::date as "month"' in app
    assert '::date as "day"' in ops
    assert "::date month" not in app
    assert "::date day" not in ops


def test_recurring_uses_latest_completed_service_only():
    ops = src("operational_v8.py")
    assert "select distinct on (v.customer_id)" in ops
    assert "where v.status='completed'" in ops


def test_backup_contract_is_complete_and_excludes_sensitive_tables():
    block = src("operational_v8.py").split("def _backup_bytes", 1)[1].split("def _send_push", 1)[0]
    for table in ("service_items", "inventory", "customer_notes", "service_media", "audit_log"):
        assert f'"{table}"' in block
    for table in ("auth_sessions", "api_idempotency", "users"):
        assert f'"{table}"' not in block
    assert '"finance"' in block and '"admin_profile"' in block


def test_nightly_is_retry_safe_and_money_is_persian():
    ops = src("operational_v8.py")
    assert 'previous.get("ok") is True' in ops
    assert 'errors["report"]' in ops and 'errors["backup"]' in ops
    assert "200 if not errors else 502" in ops
    assert 'replace(",", "،")' in ops
    assert "۰۱۲۳۴۵۶۷۸۹" in ops
    assert "if count:" in ops
