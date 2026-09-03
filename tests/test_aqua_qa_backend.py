from aqua_qa_backend_fix import (
    classify_payment_method,
    is_readonly_service_count,
    service_visit_to_invoice,
)


def test_empty_payment_method_is_other():
    assert classify_payment_method("") == "other"
    assert classify_payment_method(None) == "other"
    assert classify_payment_method("نقدی") == "cash"
    assert classify_payment_method("کارتخوان") == "card"
    assert classify_payment_method("کارت به کارت") == "transfer"


def test_qa_today_service_prompt_is_readonly():
    assert is_readonly_service_count("امروز چند سرویس داریم؟ فقط بگو، هیچ تغییری اعمال نکن.")
    assert is_readonly_service_count("تعداد سرویس امروز را فقط بگو")
    assert not is_readonly_service_count("مبلغ پرداختی مشتری رضایی را تغییر بده")
    assert not is_readonly_service_count("قیمت دلار امروز")


def test_service_visit_invoice_shape():
    invoice = service_visit_to_invoice(
        {
            "id": "12345678-1234-5678-1234-567812345678",
            "customer_id": "12345678-1234-5678-1234-567812345679",
            "customer_name": "رضایی",
            "phone": "09120000000",
            "service_type": "تعویض فیلتر",
            "description": "سرویس دوره‌ای",
            "invoice_amount": 68300000,
            "received_amount": 68300000,
            "visited_at": "2026-09-03T12:00:00+03:30",
        }
    )
    assert invoice["total"] == 68300000
    assert invoice["source"] == "service_visit"
    assert invoice["item_count"] == 1
    assert invoice["items"][0]["line_total"] == 68300000
    assert invoice["invoice_no"].startswith("SV-")
