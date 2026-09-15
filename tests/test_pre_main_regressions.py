from datetime import datetime
from uuid import uuid4

import pytest
from flask import jsonify

from app import app
import app_v3
import aqua_aria_map as aria
import aqua_smart_tour as tour
import aqua_today_tour as today
from aqua_finance_followup import _persist_created_payment
from aqua_map_address import address_result_matches

NOW = datetime(2026, 9, 15, 12, tzinfo=tour.TEHRAN)


def job(raw, received='2026-09-14T12:00:00+03:30', ident=None):
    return {'id': ident or str(uuid4()), 'status': 'new', 'raw_text': raw,
            'received_at': received, 'phone': '', 'customer_name': 'آزمایش'}


@pytest.mark.parametrize('raw,day', [
    ('چهارشنبه ۱۱', 16), ('سه شنبه ۳ تا ۵', 15), ('سه‌شنبه ۱۹ الی ۲۰', 15),
    ('پنج شنبه ۱۱', 17), ('یک‌شنبه ۱۱', 20), ('فردا ۳ تا ۵', 15),
    ('پس فردا ۱۱', 16), ('امروز ۱۹ الی ۲۰', 14),
])
def test_due_day_is_anchored_to_receipt(raw, day):
    row = job(raw)
    assert tour._job_due_day(row).day == day
    schedule = tour._parse_schedule(row, NOW)
    assert (schedule is not None) == (day == NOW.day)


def test_previous_weekday_does_not_roll_forward_every_week():
    row = job('سه شنبه ۳ تا ۵', '2026-09-07T12:00:00+03:30')
    assert tour._job_due_day(row).day == 8
    assert tour._parse_schedule(row, NOW) is None


class RowsDB:
    def __init__(self, rows):
        self.rows = rows
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def cursor(self):
        return self
    def execute(self, *args):
        pass
    def fetchall(self):
        return self.rows


def test_active_tour_excludes_future_and_unknown_and_keeps_today_and_overdue(monkeypatch):
    rows = [job('چهارشنبه ۱۱', ident='future'), job('سه شنبه ۳ تا ۵', ident='today'),
            job('دوشنبه ۱۹ الی ۲۰', ident='overdue'), job('فردا', ident='relative-today'),
            job('فیلتر', received='invalid', ident='unknown'), job('۱۴۰۵/۰۶/۲۵', ident='explicit-unknown')]
    monkeypatch.setattr(app_v3, 'get_db', lambda: RowsDB(rows))
    monkeypatch.setattr(tour, '_sync_preview_jobs', lambda: None)
    monkeypatch.setattr(tour, '_now', lambda: NOW)
    result = aria._active_today_and_overdue_rows()
    assert {row['id'] for row in result} == {'today', 'relative-today', 'overdue'}
    assert next(row for row in result if row['id'] == 'overdue')['overdue'] is True
    assert {row['id'] for row in today._active_rows()} == {'today', 'relative-today', 'overdue'}


def test_overdue_append_respects_capacity_without_extra_database_read(monkeypatch):
    monkeypatch.setattr(aria, '_SMART_ACTIVE_TODAY_ROWS', lambda: [{'id': str(i)} for i in range(tour.MAX_TOUR_JOBS)])
    monkeypatch.setattr(app_v3, 'get_db', lambda: pytest.fail('tour is already full'))
    assert len(aria._active_today_and_overdue_rows()) == tour.MAX_TOUR_JOBS


@pytest.mark.parametrize('text', ['هوای تهران چطوره؟', 'اخبار کرج رو نشون بده', 'قیمت طلا تهران', 'مشتری مرزداران رو پیدا کن'])
def test_server_does_not_intercept_non_address_chat(text):
    assert aria.extract_address_intent(text) is None


def test_server_address_intent_keeps_the_street_number():
    assert aria.extract_address_intent('مرزداران گلستان ۱۵ روی نقشه نشون بده')['address'] == 'مرزداران گلستان 15'


def test_provider_match_requires_relevant_terms_and_exact_number():
    query = 'مرزداران گلستان پانزده'
    assert address_result_matches(query, {'title': 'گلستان ۱۵', 'address': 'تهران مرزداران'})
    assert not address_result_matches(query, {'title': 'گلستان ۱۵۰', 'address': 'تهران مرزداران'})
    assert not address_result_matches(query, {'title': 'شیراز'})


@pytest.mark.parametrize('path,key', [('/api/jobs', 'id'), ('/api/smart/register', 'visit_id')])
def test_payment_replay_never_opens_a_write_transaction(monkeypatch, path, key):
    monkeypatch.setattr(app_v3, 'get_db', lambda: pytest.fail('replay must not write'))
    with app.test_request_context(path, method='POST', json={'payment_method': 'cash'}):
        response = jsonify({key: str(uuid4())})
        response.status_code = 201
        response.headers['Idempotency-Replayed'] = 'true'
        _persist_created_payment(response)


def test_generated_map_asset_keeps_the_coordinate_bridge_after_all_injectors():
    response = app.test_client().get('/aqua-smart-tour.js')
    assert response.status_code == 200
    source = response.get_data(as_text=True)
    assert source.count('window.AquaMapBridge={') == 1
    assert 'await selectFreeDestination(point)' in source
    assert 'await startNavigation(point)' in source
