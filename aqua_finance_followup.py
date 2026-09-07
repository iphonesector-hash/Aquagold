"""Scoped follow-up for finance QA: payment persistence and mobile-only UI patch injection."""
from __future__ import annotations

import json
import re

from flask import request

import app_v3


FOLLOWUP_SCRIPT = '<script defer src="/aqua-finance-followup.js?v=20260907-f2"></script>'


def _payment_key(value):
    value = re.sub(r'[\s_\-\u200c]+', '', str(value or '').lower().replace('ي', 'ی').replace('ك', 'ک'))
    aliases = {
        'cash': 'cash', 'نقد': 'cash', 'نقدی': 'cash',
        'card': 'card', 'pos': 'card', 'cardreader': 'card', 'کارتخوان': 'card',
        'transfer': 'transfer', 'cardtocard': 'transfer', 'کارتبهکارت': 'transfer',
        'banktransfer': 'transfer', 'انتقال': 'transfer',
        'cheque': 'cheque', 'check': 'cheque', 'چک': 'cheque',
        'credit': 'credit', 'نسیه': 'credit', 'اعتباری': 'credit',
        'other': 'other', 'سایر': 'other', 'unknown': 'other', 'نامشخص': 'other',
    }
    return aliases.get(value, 'other')


def _persist_created_payment(response):
    if request.method != 'POST' or response.status_code != 201 or not response.is_json:
        return
    if request.path not in ('/api/jobs', '/api/smart/register'):
        return
    payload = response.get_json(silent=True) or {}
    body = request.get_json(silent=True) or {}
    visit_id = payload.get('id') if request.path == '/api/jobs' else payload.get('visit_id')
    if not visit_id:
        return
    parsed = body.get('parsed') if isinstance(body.get('parsed'), dict) else {}
    raw_method = body.get('payment_method') or parsed.get('payment_method')
    method = _payment_key(raw_method)
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute('select payment_method,received_amount from service_visits where id=%s for update', (visit_id,))
        before = cur.fetchone()
        if not before:
            return
        if before.get('payment_method') == method:
            return
        cur.execute('update service_visits set payment_method=%s,updated_at=now() where id=%s', (method, visit_id))
        app_v3.audit(
            cur, 'service_visit', visit_id, 'payment_method_normalized',
            before={'payment_method': before.get('payment_method')},
            after={'payment_method': method},
        )


def _map_finance_unknown_to_other(response):
    if request.path != '/api/finance/dashboard' or not response.is_json or response.status_code != 200:
        return response
    payload = response.get_json(silent=True) or {}
    payments = payload.get('payments') or []
    other = next((item for item in payments if item.get('key') == 'other'), None)
    unknown = next((item for item in payments if item.get('key') == 'unknown'), None)
    if other is not None and unknown is not None:
        other['amount'] = int(other.get('amount') or 0) + int(unknown.get('amount') or 0)
        unknown['amount'] = 0
    for row in payload.get('records') or []:
        if row.get('method') == 'unknown':
            row['method'] = 'other'
            if not row.get('raw_method'):
                row['raw_method'] = 'other'
    response.set_data(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response


@app_v3.app.after_request
def aqua_finance_followup(response):
    try:
        _persist_created_payment(response)
    except Exception:
        app_v3.app.logger.exception('finance follow-up payment persistence failed')
    try:
        response = _map_finance_unknown_to_other(response)
    except Exception:
        app_v3.app.logger.exception('finance follow-up dashboard mapping failed')
    try:
        if request.path == '/' and response.status_code == 200 and 'text/html' in (response.content_type or ''):
            response.direct_passthrough = False
            html = response.get_data(as_text=True)
            if 'aqua-finance-followup.js' not in html and '</body>' in html:
                response.set_data(html.replace('</body>', FOLLOWUP_SCRIPT + '</body>', 1))
    except Exception:
        app_v3.app.logger.exception('finance follow-up script injection failed')
    return response
