import bale_bridge
import bale_phone_runtime_fix  # noqa: F401


def test_persian_digit_phone_without_legacy_keyword_is_work():
    parsed = bale_bridge._extract_job(
        "سه شنبه ۱۹\n"
        "تعویض پمپ ۵۸۰۰\n"
        "زاهدی ۰۹۱۲۱۵۴۷۲۹۰\n"
        "مرزداران خ بهار گلبرگ شرق پ۲۰ ط۲"
    )
    assert parsed is not None
    assert parsed["phone"] == "09121547290"
    assert parsed["rule"] == "name_phone"


def test_arabic_indic_phone_without_legacy_keyword_is_work():
    parsed = bale_bridge._extract_job(
        "امروز ساعت ۱۸\n"
        "تعویض پمپ\n"
        "احمدی ٠٩١٢١٢٣٤٥٦٧\n"
        "تهران مرزداران"
    )
    assert parsed is not None
    assert parsed["phone"] == "09121234567"
    assert parsed["rule"] == "name_phone"


def test_non_work_message_stays_ignored():
    assert bale_bridge._extract_job("سلام ممنون، رسیدم") is None
