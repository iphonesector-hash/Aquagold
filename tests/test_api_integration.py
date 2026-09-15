"""End-to-end API checks against a disposable PostgreSQL/PostGIS database."""

import os

import pytest
from werkzeug.security import generate_password_hash


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def app_module():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL is not configured")
    import app_v3

    app_v3.DATABASE_URL = os.environ["TEST_DATABASE_URL"]
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("truncate table api_idempotency,auth_sessions,audit_log,invoice_items,invoices,products,company_settlements,expenses,service_items,service_visits,customer_phones,customers_v2 restart identity cascade")
        cur.execute("delete from users")
        cur.execute("delete from app_settings where key like 'map_special_locations:%'")
        cur.execute(
            """insert into users(username,password_hash,first_name,last_name,role,active)
               values(%s,%s,'مدیر','آزمایش','superadmin',true),
                     (%s,%s,'کاربر','خواندنی','viewer',true),
                     (%s,%s,'فنی','آزمایش','technician',true)""",
            (
                "admin", generate_password_hash("A-strong-test-password"),
                "viewer", generate_password_hash("Viewer-test-password"),
                "technician", generate_password_hash("Technician-test-password"),
            ),
        )
    import app as entry
    entry.app.config.update(TESTING=True)
    return entry


def login(client, username="admin", password="A-strong-test-password"):
    response = client.post("/api/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["csrf_token"]


def test_secure_session_customer_service_and_pagination(app_module):
    client = app_module.app.test_client()
    csrf = login(client)
    customer_key = "7b7bbc93-f1fd-4b07-a375-8c1eb4b147f0"
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": customer_key}

    session = client.get("/api/session")
    assert session.status_code == 200
    assert session.get_json()["user"]["role"] == "superadmin"

    created = client.post(
        "/api/customers",
        headers=headers,
        json={
            "client_id": customer_key,
            "last_name": "صادقی",
            "phones": ["۰۹۱۲۵۷۸۲۸۰۳", "09122501272"],
            "address": "آریاشهر، آیت‌الله کاشانی",
            "latitude": 35.7219,
            "longitude": 51.3347,
        },
    )
    assert created.status_code == 201, created.get_json()
    customer_id = created.get_json()["id"]
    assert customer_id == customer_key

    replayed = client.post(
        "/api/customers",
        headers=headers,
        json={
            "client_id": customer_key,
            "last_name": "صادقی",
            "phones": ["۰۹۱۲۵۷۸۲۸۰۳", "09122501272"],
            "address": "آریاشهر، آیت‌الله کاشانی",
            "latitude": 35.7219,
            "longitude": 51.3347,
        },
    )
    assert replayed.status_code == 201
    assert replayed.headers["Idempotency-Replayed"] == "true"
    assert replayed.get_json()["id"] == customer_id

    duplicate = client.post(
        "/api/customers",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "8887c65e-74dd-46c7-9f69-d87ad22b1531"},
        json={"last_name": "مشتری دیگر", "phones": ["09125782803"]},
    )
    assert duplicate.status_code == 409

    service = client.post(
        "/api/jobs",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "422a42c4-d3eb-489d-ac26-d9e257a50288"},
        json={
            "client_id": "422a42c4-d3eb-489d-ac26-d9e257a50288",
            "customer_id": customer_id,
            "service_type": "تعویض فیلتر",
            "invoice_amount": 1_000_000,
            "received_amount": 1_200_000,
            "payment_method": "card",
            "status": "completed",
        },
    )
    assert service.status_code == 201, service.get_json()
    assert service.get_json()["customer_balance"] == 0
    assert service.get_json()["overpayment_amount"] == 200_000

    customers = client.get("/api/customers?page=1&per_page=1&q=صادقی").get_json()
    assert customers["pagination"] == {"page": 1, "per_page": 1, "total": 1, "pages": 1}
    assert customers["items"][0]["service_count"] == 1
    assert customers["items"][0]["total_received"] == 1_200_000

    jobs = client.get("/api/jobs?page=1&per_page=1&q=فیلتر").get_json()
    assert jobs["pagination"]["total"] == 1
    assert jobs["items"][0]["overpayment_amount"] == 200_000

    logged_out = client.post("/api/logout", headers={"X-CSRF-Token": csrf})
    assert logged_out.status_code == 200
    assert client.get("/api/session").status_code == 401


def test_role_guard_and_csrf(app_module):
    client = app_module.app.test_client()
    csrf = login(client, "viewer", "Viewer-test-password")
    forbidden = client.post(
        "/api/customers",
        headers={"X-CSRF-Token": csrf},
        json={"last_name": "محدود", "phones": ["09120000000"]},
    )
    assert forbidden.status_code == 403

    missing_csrf = client.post("/api/logout")
    assert missing_csrf.status_code == 403


def test_validation_rejects_bad_phone_and_coordinates(app_module):
    client = app_module.app.test_client()
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    bad_phone = client.post(
        "/api/customers", headers=headers,
        json={"last_name": "آزمایش", "phones": ["123"]},
    )
    assert bad_phone.status_code == 400
    bad_location = client.post(
        "/api/customers", headers=headers,
        json={"last_name": "آزمایش", "latitude": 120, "longitude": 51},
    )
    assert bad_location.status_code == 400

    malformed = client.post(
        "/api/customers", headers={**headers, "Content-Type": "application/json"}, data="{",
    )
    assert malformed.status_code == 400
    assert malformed.is_json


def test_special_locations_persist_validate_and_isolate_users(app_module):
    admin = app_module.app.test_client()
    admin_csrf = login(admin)
    created = admin.post(
        "/api/map/special-locations",
        headers={"X-CSRF-Token": admin_csrf, "Idempotency-Key": "0afe1d5a-3778-47c5-9c7c-ac694235ec81"},
        json={"name": "بانک تست", "address": "فردیس", "lat": 35.72, "lng": 50.98},
    )
    assert created.status_code == 201, created.get_json()
    item = created.get_json()
    assert admin.get("/api/map/special-locations").get_json()["items"] == [item]

    edited = admin.patch(
        f"/api/map/special-locations/{item['id']}",
        headers={"X-CSRF-Token": admin_csrf},
        json={"name": "بانک تست ویرایش", "address": "فلکه سوم", "lat": 1, "lng": 2},
    )
    assert edited.status_code == 200, edited.get_json()
    assert edited.get_json()["name"] == "بانک تست ویرایش"
    assert edited.get_json()["lat"] == item["lat"]
    assert edited.get_json()["lng"] == item["lng"]

    bad = admin.post(
        "/api/map/special-locations",
        headers={"X-CSRF-Token": admin_csrf},
        json={"name": "", "lat": 120, "lng": 51},
    )
    assert bad.status_code == 400

    technician = app_module.app.test_client()
    technician_csrf = login(technician, "technician", "Technician-test-password")
    assert technician.get("/api/map/special-locations").get_json()["items"] == []
    other = technician.post(
        "/api/map/special-locations",
        headers={"X-CSRF-Token": technician_csrf},
        json={"name": "انبار", "lat": 35.8, "lng": 50.9},
    )
    assert other.status_code == 201, other.get_json()
    assert len(technician.get("/api/map/special-locations").get_json()["items"]) == 1
    assert len(admin.get("/api/map/special-locations").get_json()["items"]) == 1

    removed = admin.delete(
        f"/api/map/special-locations/{item['id']}", headers={"X-CSRF-Token": admin_csrf}
    )
    assert removed.status_code == 200
    assert admin.get("/api/map/special-locations").get_json()["items"] == []


def test_bale_today_snapshot_uses_tehran_event_day(app_module):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    import app_v3

    app_v3.limiter.reset()  # Isolate this test from earlier login rate-limit tests.
    client = app_module.app.test_client()
    login(client)
    today = datetime.now(ZoneInfo('Asia/Tehran')).replace(hour=0, minute=0, second=0, microsecond=0)
    records = [
        ('new', today - timedelta(days=2), None, None),
        ('review', today, None, None),
        ('completed', today - timedelta(days=2), today + timedelta(minutes=1), None),
        ('completed', today, today - timedelta(seconds=1), None),
        ('cancelled', today - timedelta(days=2), None, today + timedelta(minutes=1)),
        ('cancelled', today, None, today - timedelta(seconds=1)),
    ]
    ids = []
    try:
        with app_v3.get_db() as db, db.cursor() as cur:
            for i, (status, received, completed, cancelled) in enumerate(records):
                cur.execute('''insert into bale_jobs(chat_id,message_id,raw_text,status,received_at,completed_at,cancelled_at)
                    values(-987654321,%s,'snapshot test',%s,%s,%s,%s) returning id''',
                    (i, status, received, completed, cancelled))
                ids.append(str(cur.fetchone()['id']))
        for tab, expected in [('new', {ids[0], ids[1]}), ('completed', {ids[2]}), ('cancelled', {ids[4]})]:
            response = client.get('/api/bale/jobs/today?status=' + tab)
            assert response.status_code == 200, response.get_json()
            data = response.get_json()
            actual = {row['id'] for row in data['items']} & set(ids)
            assert actual == expected
            assert data['counts'][tab] == len(data['items'])
    finally:
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute('delete from bale_jobs where chat_id=-987654321')



@pytest.mark.parametrize('path', ['/api/jobs', '/api/smart/register'])
def test_create_replay_preserves_later_payment_correction(app_module, path):
    from uuid import uuid4
    client = app_module.app.test_client()
    csrf = login(client)
    headers = {'X-CSRF-Token': csrf}
    customer = client.post('/api/customers', headers=headers, json={'last_name': 'آزمایش بازپخش'})
    assert customer.status_code == 201, customer.get_json()
    customer_id = customer.get_json()['id']
    key = str(uuid4())
    body = {'customer_id': customer_id, 'service_type': 'تست بازپخش', 'invoice_amount': 1000,
            'received_amount': 1000, 'payment_method': 'cash', 'status': 'completed'}
    if path.endswith('/register'):
        body['parsed'] = {'last_name': 'آزمایش بازپخش', 'phones': [], 'amount': 1000}
    else:
        body['client_id'] = key
    create_headers = {**headers, 'Idempotency-Key': key}
    created = client.post(path, headers=create_headers, json=body)
    assert created.status_code == 201, created.get_json()
    visit_id = created.get_json()['visit_id' if path.endswith('/register') else 'id']
    report = client.get('/api/finance/dashboard').get_json()
    record = next(row for row in report['records'] if row['id'] == visit_id)
    assert record['method'] == 'cash'
    edited = client.patch('/api/finance/payments/' + visit_id, headers=headers,
                          json={'payment_method': 'transfer', 'revision': record['revision']})
    assert edited.status_code == 200, edited.get_json()
    replay = client.post(path, headers=create_headers, json=body)
    assert replay.status_code == 201, replay.get_json()
    assert replay.headers['Idempotency-Replayed'] == 'true'
    report = client.get('/api/finance/dashboard').get_json()
    records = [row for row in report['records'] if row['id'] == visit_id]
    assert len(records) == 1 and records[0]['method'] == 'transfer'
