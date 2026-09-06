"""Database-backed regression checks for AquaGold Bale Mini App."""

import os
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def mini_app():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL is not configured")
    import app_v3

    app_v3.DATABASE_URL = os.environ["TEST_DATABASE_URL"]
    import app as entry
    import aqua_bale_miniapp as mini

    entry.app.config.update(TESTING=True)
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("delete from bale_jobs")
        cur.execute("delete from service_visits")
        cur.execute("delete from customer_phones")
        cur.execute("delete from customers_v2")
        cur.execute("delete from company_settlements")
        cur.execute("delete from app_settings where key=%s", (mini.MINI_AUTH_KEY,))
        cur.execute(
            """insert into customers_v2(id,last_name,normalized_name,address,created_by)
               values('11111111-1111-4111-8111-111111111111','موسوی','موسوی','کرج، مهرشهر','test')"""
        )
        cur.execute(
            """insert into customer_phones(customer_id,phone,is_primary)
               values('11111111-1111-4111-8111-111111111111','09120000000',true)"""
        )
        cur.execute(
            """insert into service_visits(
                   id,customer_id,registered_by,service_type,status,amount,invoice_amount,received_amount,
                   company_share_percent,company_share_amount,customer_balance,visited_at,created_at)
               values('22222222-2222-4222-8222-222222222222','11111111-1111-4111-8111-111111111111',
                      'test','تعویض فیلتر','registered',2800000,2800000,2800000,50,1400000,0,%s,%s)""",
            (datetime(2026, 9, 6, 8, 30, tzinfo=timezone.utc), datetime(2026, 9, 6, 8, 30, tzinfo=timezone.utc)),
        )
        cur.execute(
            """insert into bale_jobs(
                   id,bale_update_id,chat_id,message_id,raw_text,customer_name,phone,address,job_type,
                   customer_id,status,cancel_reason,received_at,cancelled_at,updated_at)
               values('33333333-3333-4333-8333-333333333333',333,10,20,'یکشنبه ۲۰ الی ۲۱',
                      'یکشنبه ۲۰ الی ۲۱','09120000000','کرج','فیلتر',
                      '11111111-1111-4111-8111-111111111111','cancelled','لغو تست',%s,%s,%s)""",
            (
                datetime(2026, 9, 6, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 6, 9, 15, tzinfo=timezone.utc),
                datetime(2026, 9, 6, 9, 15, tzinfo=timezone.utc),
            ),
        )
    return entry, mini


def authorized_client(mini_app):
    entry, mini = mini_app
    client = entry.app.test_client()
    with entry.app.app_context():
        token = mini._serializer().dumps({"u": "admin"})
    client.set_cookie(mini.MINI_COOKIE, token)
    return client


def test_day_uses_final_surname_received_amount_and_cancellation(mini_app):
    client = authorized_client(mini_app)
    response = client.get("/api/mini/day?date=2026-09-06")
    assert response.status_code == 200, response.get_json()
    data = response.get_json()
    assert data["summary"]["completed"] == 1
    assert data["summary"]["cancelled"] == 1
    assert data["summary"]["received"] == 2_800_000
    service = next(x for x in data["jobs"] if x["status"] == "completed")
    cancelled = next(x for x in data["jobs"] if x["status"] == "cancelled")
    assert service["customer_name"] == "موسوی"
    assert cancelled["customer_name"] == "موسوی"
    assert service["customer_name"] != "یکشنبه ۲۰ الی ۲۱"


def test_customer_summary_counts_registered_service_as_completed(mini_app):
    client = authorized_client(mini_app)
    response = client.get("/api/mini/customers?q=موسوی")
    assert response.status_code == 200, response.get_json()
    customer = response.get_json()[0]
    assert customer["completed_services"] == 1
    assert customer["cancelled_services"] == 1
    assert customer["total_services"] == 2
    assert customer["total_received"] == 2_800_000


def test_finance_query_executes_and_counts_registered_service(mini_app):
    client = authorized_client(mini_app)
    response = client.get("/api/mini/finance?period=daily&date=2026-09-06")
    assert response.status_code == 200, response.get_json()
    data = response.get_json()
    assert data["summary"]["service_count"] == 1
    assert data["summary"]["received_total"] == 2_800_000
    assert data["summary"]["company_share"] == 1_400_000
    assert any(point["day"] == "2026-09-06" for point in data["chart"])
