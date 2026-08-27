from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def src(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_vapid_string_is_pywebpush_compatible_der_not_pem():
    fix = src("operational_v8_fixes.py")
    assert "serialization.Encoding.DER" in fix
    assert "serialization.PrivateFormat.PKCS8" in fix
    assert "urlsafe_b64encode" in fix
    assert "-----BEGIN" in fix
    assert "operational_v8._ensure_vapid = _ensure_vapid_compatible" in fix


def test_company_share_uses_postgres_safe_alias_and_range_matched_settlements():
    fix = src("operational_v8_fixes.py")
    assert "as report_day" in fix
    assert 'item["day"] = item.pop("report_day")' in fix
    assert '_range_clause("s.settled_at")' in fix
    assert "from company_settlements s where" in fix
    assert 'view_functions["ops_company_share"]' in fix


def test_recurring_list_uses_only_latest_completed_service_per_customer():
    fix = src("operational_v8_fixes.py")
    assert "select distinct on (v.customer_id)" in fix
    assert "where v.status='completed'" in fix
    assert 'view_functions["ops_recurring"]' in fix


def test_backup_without_reporting_destination_is_controlled_400():
    fix = src("operational_v8_fixes.py")
    assert "ابتدا ربات گزارش و کانال مقصد را در تنظیمات مشخص کن" in fix
    assert "}), 400" in fix
    assert 'view_functions["ops_backup_send"]' in fix


def test_nightly_retry_is_not_permanently_blocked_by_failed_first_run():
    fix = src("operational_v8_fixes.py")
    assert 'if result.get("ok") is True' in fix
    assert 'errors["report"]' in fix
    assert 'errors["backup"]' in fix
    assert 'return jsonify(summary), (200 if ok else 502)' in fix


def test_recurring_push_window_is_retry_safe_and_marks_only_after_send():
    fix = src("operational_v8_fixes.py")
    assert "now()-interval '48 hours'" in fix
    assert "now()+interval '24 hours'" in fix
    assert 'reminder_key = "recurring:" + item["service_id"]' in fix
    assert "if count > 0:" in fix
    assert 'view_functions["ops_nightly"] = ops_nightly_fixed' in fix


def test_nightly_money_is_persian_grouped_and_full_toman():
    fix = src("operational_v8_fixes.py")
    assert "replace(\",\", \"،\")" in fix
    assert "۰۱۲۳۴۵۶۷۸۹" in fix
    assert " تومان" in fix


def test_operational_import_is_serialized_across_cold_starts():
    app = src("app.py")
    assert "pg_advisory_lock(hashtext('aquagold-operational-v8-import'))" in app
    assert "pg_advisory_unlock(hashtext('aquagold-operational-v8-import'))" in app
    assert app.index("pg_advisory_lock") < app.index("import operational_v8") < app.index("pg_advisory_unlock")


def test_fix_load_order_precedes_aria_ui_injection():
    app = src("app.py")
    assert "import operational_v8_fixes" in app
    assert app.index("import operational_v8") < app.index("import operational_v8_fixes") < app.index("import aria_v8")
