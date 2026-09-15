from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_aria_address_guard_preserves_customer_search_and_persian_words():
    text = source("aqua_aria_map.py")
    assert 'if "مشتری" in text:' in text
    assert "_strip_filler_words" in text
    assert "(?<!\\S)" in text and "(?!\\S)" in text
    assert "روی\\s+نقشه" in text


def test_today_tour_reads_both_active_bale_states_and_uses_real_map_provider():
    text = source("aqua_today_tour.py")
    assert "status in ('new','review')" in text
    assert "geocode_provider(address, 1)" in text
    assert "ROUTING_URL" in text
    assert '"quality": "unresolved"' in text
    assert "/api/map/today-tour/plan" in text


def test_duplicate_customer_flow_has_history_selection_and_stable_idempotency():
    text = source("aqua-duplicate-customer.js")
    assert "/customers/${encodeURIComponent(id)}/jobs?per_page=10" in text
    assert "انتخاب این مشتری" in text
    assert "این شماره متعلق به مشتری موجود است" in text
    assert "smartRegisterIdempotency" in text
    assert "'Idempotency-Key':this.smartRegisterIdempotency.key" in text


def test_expense_editor_has_independent_jalali_year_month_day_controls():
    text = source("aqua-expense-jalali.js")
    assert "en-US-u-ca-persian" in text
    assert "Asia/Tehran" in text
    assert "make('سال'" in text
    assert "make('ماه'" in text
    assert "make('روز'" in text
    assert "تاریخ شمسی هزینه" in text


def test_runtime_imports_new_completion_layers_in_safe_order():
    text = source("app.py")
    assert "import aqua_today_tour" in text
    assert text.index("import aqua_duplicate_customer_flow") < text.index("import aqua_smart_register_guard")
    assert text.index("import aqua_expense_jalali") < text.index("import aqua_targeted_fix")
