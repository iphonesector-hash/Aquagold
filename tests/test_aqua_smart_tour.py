from datetime import datetime
from pathlib import Path

import aqua_smart_tour as tour


ROOT = Path(__file__).resolve().parents[1]


def _now():
    # Tuesday 2026-09-08 in Tehran.
    return datetime(2026, 9, 8, 12, 0, tzinfo=tour.TEHRAN)


def parse(line):
    return tour._parse_schedule({"raw_text": line, "received_at": _now().isoformat()}, _now())


def test_bare_afternoon_windows_follow_field_work_convention():
    s = parse("سه شنبه ۳ تا ۵\nفیلتر\nشامعی 09121234567\nتهران")
    assert (s["start"].hour, s["end"].hour) == (15, 17)

    s = parse("سه شنبه ۶ تا ۸\nفیلتر\nشامعی 09121234567\nتهران")
    assert (s["start"].hour, s["end"].hour) == (18, 20)

    s = parse("سه شنبه ۷ تا ۸\nفیلتر\nشامعی 09121234567\nتهران")
    assert (s["start"].hour, s["end"].hour) == (19, 20)

    s = parse("سه شنبه ۹ تا ۱۰\nفیلتر\nشامعی 09121234567\nتهران")
    assert (s["start"].hour, s["end"].hour) == (21, 22)


def test_explicit_24_hour_window_is_kept():
    s = parse("سه شنبه ۱۹ الی ۲۰\nساید\nمعماری 09121234567")
    assert (s["start"].hour, s["end"].hour) == (19, 20)


def test_immediate_and_from_now_are_first_class_windows():
    s = parse("سه شنبه همین الان\nفیلتر\nشامعی 09121234567")
    assert s["immediate"] is True
    assert s["start"] == _now()

    s = parse("سه شنبه از الان الی ۱۸\nفیلتر\nشامعی 09121234567")
    assert s["immediate"] is True
    assert s["start"] == _now()
    assert s["end"].hour == 18


def test_job_for_other_explicit_weekday_is_not_in_today_tour():
    assert parse("دوشنبه ۱۹ الی ۲۰\nفیلتر\nشامعی 09121234567") is None


def test_phone_and_customer_name_recovered_from_bale_raw_text():
    job = {
        "raw_text": "سه شنبه ۱۹ الی ۲۰\nفیلتر\nشامعی ۰۹۱۲۱۲۳۴۵۶۷\nولنجک، خیابان نمونه",
        "customer_name": "سه شنبه ۱۹ الی ۲۰",
    }
    assert tour._extract_phone(job["raw_text"]) == "09121234567"
    assert tour._extract_customer_name(job) == "شامعی"


def test_navigation_failure_and_ios_resume_are_fail_safe():
    fragment = (ROOT / "aqua-navigation-pro-fragment.js").read_text(encoding="utf-8")
    polish = (ROOT / "aqua_navigation_polish.py").read_text(encoding="utf-8")

    assert "if(ST.nav.active){try{await stopNavigation()}" in fragment
    assert "document.documentElement.classList.remove('aqst-nav-fullscreen')" in fragment
    assert "function aqRestoreWakeLock()" in polish
    assert "document.addEventListener('visibilitychange'" in polish
    assert "window.addEventListener('orientationchange'" in polish
    assert "window.__aquaNavLifecycleBound" in polish
