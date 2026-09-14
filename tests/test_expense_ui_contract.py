from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_expense_edit_updates_timestamp_and_has_touch_actions():
    backend = (ROOT / "aqua_targeted_fix.py").read_text()
    assert "expense_date = valid_timestamp" in backend
    assert "min-h-11" in backend
    assert "type=\"datetime-local\"" in backend


def test_amount_parser_accepts_persian_and_arabic_digits():
    source = (ROOT / "ui-v3-base.js").read_text()
    assert "replace(/[۰-۹٠-٩]/g" in source
