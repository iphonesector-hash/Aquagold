from datetime import datetime

import bale_reports


def test_jalali_conversion_for_august_31_2026():
    assert bale_reports._g2j(2026, 8, 31) == (1405, 6, 9)
    assert bale_reports._j2g(1405, 6, 1) == (2026, 8, 23)


def test_money_format_uses_persian_digits_and_separators():
    assert bale_reports._fa_number(2_500_000) == "۲٬۵۰۰٬۰۰۰"


def test_daily_window_starts_at_midnight_tehran():
    now = datetime(2026, 8, 31, 23, 0, tzinfo=bale_reports.TEHRAN)
    start, end, key, title, label = bale_reports._window("daily", now)
    assert start.isoformat() == "2026-08-31T00:00:00+03:30"
    assert end == now
    assert key == "2026-08-31"
    assert title == "گزارش پایان کار روزانه"
    assert label == "۹ شهریور ۱۴۰۵"


def test_weekly_window_is_seven_calendar_days_including_friday():
    friday = datetime(2026, 9, 4, 23, 0, tzinfo=bale_reports.TEHRAN)
    start, _, _, _, _ = bale_reports._window("weekly", friday)
    assert start.date().isoformat() == "2026-08-29"
    assert friday.weekday() == 4
