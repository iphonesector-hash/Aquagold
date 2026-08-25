from smart_intake import parse_intake, parse_money


def test_user_example_is_parsed():
    text = """سه شنبه از الان الی ۱۵:۳۰
فیلتر
صادقی ۰۹۱۲۵۷۸۲۸۰۳
۰۹۱۲۲۵۰۱۲۷۲
آریا شهر آیت الله کاشانی خ بهنام شهرک
فرهنگیان وارانک ۵ پ ۱۰ واحد ۵
مهمانی۳"""
    result = parse_intake(text)
    assert result['last_name'] == 'صادقی'
    assert result['phones'] == ['09125782803', '09122501272']
    assert 'کاشانی' in result['address']
    assert 'واحد 5' in result['address']
    assert result['visitor_code'] == 'مهمانی3'
    assert result['service_type'] == 'فیلتر'
    assert '15:30' in result['time_text']


def test_money_variants():
    assert parse_money('۵/۶۰۰/۰۰۰') == 5600000
    assert parse_money('۵٬۶۰۰٬۰۰۰ تومان') == 5600000
    assert parse_money('5,600,000') == 5600000
