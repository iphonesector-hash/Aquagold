from smart_intake import parse_intake


def test_bale_standard_format():
    text = '''پنجشنبه ۱۹ الی ۲۰
ساید
معماری ۰۹۱۲۷۶۵۳۱۱۴
کرج فردیس شهرک ناز خ ۶ فرعی سوم شرقی
پ ۱۵ ویلایی
سما ۳'''
    p = parse_intake(text)
    assert p['last_name'] == 'معماری'
    assert p['phones'] == ['09127653114']
    assert p['service_type'] == 'یخچال/ساید'
    assert p['visitor_code'] == 'سما 3'
    assert 'کرج فردیس' in p['address']
    assert 'پ 15 ویلایی' in p['address']
    assert p['time_text'] == 'پنجشنبه 19 الی 20'


def test_device_format_and_address_continuation():
    text = '''سه شنبه ساعت ۱۵
دستگاه
صادقی 09121234567
تهران آریاشهر خیابان بهنام شهرک فرهنگیان
پلاک ۲۲ واحد ۵
حسین ۲'''
    p = parse_intake(text)
    assert p['last_name'] == 'صادقی'
    assert p['service_type'] == 'دستگاه'
    assert p['visitor_code'] == 'حسین 2'
    assert 'پلاک 22 واحد 5' in p['address']


def test_phone_normalization():
    p = parse_intake('جمعه ۱۰ الی ۱۱\nفیلتر\nرضایی +989121234567\nتهران خیابان آزادی\nعلی 1')
    assert p['phones'][0] == '09121234567'
