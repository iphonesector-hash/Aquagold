from datetime import timedelta

import pytest

from aquagold_validation import ValidationError, phone, timestamp


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("۰۹۱۲-۵۷۸-۲۸۰۳", "09125782803"),
        ("+98 912 578 2803", "09125782803"),
        ("989125782803", "09125782803"),
    ],
)
def test_phone_normalization(raw, expected):
    assert phone(raw) == expected


def test_bad_phone_is_rejected():
    with pytest.raises(ValidationError):
        phone("021-12345678")


def test_naive_browser_timestamp_is_interpreted_as_tehran_time():
    parsed = timestamp("2026-08-25T15:30", "زمان")
    assert parsed.utcoffset() == timedelta(hours=3, minutes=30)
