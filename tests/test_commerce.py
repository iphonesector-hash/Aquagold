from decimal import Decimal

import pytest

from app_commerce import _clean_invoice_items, _clean_product, _safe_int, _uuid_or_none


def test_safe_int_accepts_persian_style_grouping_chars():
    assert _safe_int("1٬200٬000") == 1200000
    assert _safe_int("1,200,000") == 1200000
    assert _safe_int("bad") == 0
    assert _safe_int(-10) == 0


def test_uuid_validation():
    value = "12345678-1234-5678-1234-567812345678"
    assert _uuid_or_none(value) == value
    assert _uuid_or_none("") is None
    with pytest.raises(ValueError):
        _uuid_or_none("not-a-uuid")


def test_product_cleaning_never_accepts_negative_price_or_sort():
    product = _clean_product({"name": "  فیلتر  ", "price": -100, "sort_order": -2})
    assert product["name"] == "فیلتر"
    assert product["price"] == 0
    assert product["sort_order"] == 0


def test_invoice_calculation_with_fractional_quantity():
    product_id = "12345678-1234-5678-1234-567812345678"
    items, subtotal = _clean_invoice_items(
        [
            {"product_id": product_id, "title": "فیلتر", "quantity": "2", "unit_price": 1200000},
            {"title": "اجرت", "quantity": "0.5", "unit_price": 400000},
        ]
    )
    assert len(items) == 2
    assert items[0]["quantity"] == Decimal("2")
    assert items[0]["line_total"] == 2400000
    assert items[1]["line_total"] == 200000
    assert subtotal == 2600000


def test_invoice_bad_quantity_falls_back_to_one():
    items, subtotal = _clean_invoice_items([{"title": "فیلتر", "quantity": "NaN", "unit_price": 500000}])
    assert items[0]["quantity"] == Decimal("1")
    assert subtotal == 500000


def test_invoice_invalid_product_uuid_is_rejected():
    with pytest.raises(ValueError):
        _clean_invoice_items([{"product_id": "bad", "title": "فیلتر", "quantity": 1, "unit_price": 1000}])
