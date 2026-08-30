from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def src(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_final_ui_layer_is_injected_after_aria():
    index = src("index.html")
    assert '/aria-v8.js?v=' in index
    assert '/ui-detail-v8.js?v=' in index
    assert index.index('/aria-v8.js') < index.index('/ui-detail-v8.js')


def test_dashboard_actions_are_one_blue_family_and_daily_title_is_final():
    js = src("ui-detail-v8.js")
    assert "کارهای روزانه" in js
    assert ".ops-today .btn" in js
    assert "tone:'blue'" in js
    assert "el.dataset.opsTone='blue'" in js
    assert "gold" not in js


def test_dashboard_date_contract_is_rtl_day_month_year():
    js = src("ui-detail-v8.js")
    assert "${weekdayName(d)} / ${persianDigits(String(p.day).padStart(2,'0'))} / ${monthName(p.month)} / ${persianDigits(p.year)}" in js
    assert "شهریور" in js
    assert "direction:rtl" in js


def test_money_contract_uses_persian_comma_and_full_toman():
    js = src("ui-detail-v8.js")
    assert ".replace(/٬/g,'،')" in js
    assert "moneyToman" in js
    assert " تومان" in js
    assert "normalizeMoneyLabels" in js


def test_detail_layer_does_not_add_duplicate_click_sound_handler():
    js = src("ui-detail-v8.js")
    assert "MutationObserver" not in js
    assert "addEventListener('click'" not in js
    assert "preventDefault" not in js
