"""Finance-only reports and audited corrections; no shared report overrides."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
import hashlib
import json
import re
from zoneinfo import ZoneInfo

from flask import jsonify, request
import app_v3
from aquagold_validation import ValidationError, integer, text, timestamp, uuid

TEHRAN = ZoneInfo('Asia/Tehran')
LABELS = {'cash': 'نقد', 'card': 'کارت‌خوان', 'transfer': 'کارت به کارت',
          'cheque': 'چک', 'credit': 'اعتباری', 'other': 'سایر', 'unknown': 'نامشخص'}


def payment_key(value):
    value = re.sub(r'[\s_\-\u200c]+', '', str(value or '').lower().replace('ي', 'ی').replace('ك', 'ک'))
    aliases = {'cash': 'cash', 'نقد': 'cash', 'نقدی': 'cash', 'card': 'card',
               'pos': 'card', 'cardreader': 'card', 'کارتخوان': 'card',
               'transfer': 'transfer', 'cardtocard': 'transfer', 'کارتبهکارت': 'transfer',
               'banktransfer': 'transfer', 'انتقال': 'transfer', 'cheque': 'cheque',
               'check': 'cheque', 'چک': 'cheque', 'credit': 'credit', 'نسیه': 'credit',
               'اعتباری': 'credit', 'other': 'other', 'سایر': 'other'}
    return aliases.get(value, 'unknown')


def revision(row):
    values = {k: str(row.get(k) or '') for k in ('amount', 'settled_at', 'notes', 'payment_method', 'received_amount')}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def bounds(args):
    result = []
    for key in ('from', 'to'):
        raw = args.get(key)
        try:
            value = date.fromisoformat(raw) if raw else None
        except (ValueError, TypeError):
            raise ValidationError('بازه تاریخ معتبر نیست')
        result.append(datetime.combine(value, time.min, TEHRAN) if value else None)
    start, end = result
    if start and end and start > end:
        raise ValidationError('تاریخ شروع باید قبل از پایان باشد')
    return start, end + timedelta(days=1) if end else None


def build_report(visits, expenses, settlements):
    totals = dict.fromkeys(('invoice', 'received', 'company_share', 'customer_balance', 'expenses', 'settled', 'services'), 0)
    payments = {k: 0 for k in LABELS}
    days = defaultdict(lambda: dict.fromkeys(('received', 'company_share', 'expenses', 'services', 'settled', 'customer_balance'), 0))
    types, customers, categories = {}, {}, defaultdict(int)
    def day_of(value):
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if isinstance(value, datetime):
            return value.replace(tzinfo=TEHRAN).date().isoformat() if value.tzinfo is None else value.astimezone(TEHRAN).date().isoformat()
        return value.isoformat()
    records = []
    for v in visits:
        day = day_of(v['date'])
        amount = int(v.get('received_amount') or 0)
        company = int(v.get('company_share_amount') or 0)
        balance = int(v.get('customer_balance') or 0)
        totals['invoice'] += int(v.get('invoice_amount') or 0)
        totals['received'] += amount
        totals['company_share'] += company
        totals['customer_balance'] += balance
        totals['services'] += 1
        key = payment_key(v.get('payment_method'))
        payments[key] += amount
        for k, n in [('received', amount), ('company_share', company), ('customer_balance', balance), ('services', 1)]:
            days[day][k] += n
        label = v.get('service_type') or 'نامشخص'
        item = types.setdefault(label, {'label': label, 'received': 0, 'count': 0})
        item['received'] += amount
        item['count'] += 1
        cid = str(v.get('customer_id') or '')
        customer = customers.setdefault(cid, {'label': v.get('name') or 'بدون نام', 'received': 0, 'count': 0, 'balance': 0})
        customer['received'] += amount
        customer['count'] += 1
        customer['balance'] += balance
        records.append({'id': str(v['id']), 'date': day, 'name': v.get('name') or 'بدون نام',
                        'service_type': label, 'amount': amount, 'method': key,
                        'raw_method': v.get('payment_method') or '', 'revision': revision(v)})
    for e in expenses:
        amount = int(e.get('amount') or 0)
        totals['expenses'] += amount
        days[day_of(e['expense_date'])]['expenses'] += amount
        categories[e.get('category') or 'other'] += amount
    for s in settlements:
        amount = int(s.get('amount') or 0)
        totals['settled'] += amount
        days[day_of(s['settled_at'])]['settled'] += amount
    totals['net_profit'] = totals['received'] - totals['company_share'] - totals['expenses']
    totals['company_net'] = totals['company_share'] - totals['settled']
    totals['customers'] = len(customers)
    series = []
    for day, values in sorted(days.items()):
        series.append({'date': day, **values, 'net_profit': values['received'] - values['company_share'] - values['expenses']})
    return {'totals': totals, 'payments': [{'key': k, 'label': LABELS[k], 'amount': v} for k, v in payments.items()],
            'days': series, 'service_types': sorted(types.values(), key=lambda x: -x['received']),
            'customers': sorted(customers.values(), key=lambda x: -x['received']),
            'expense_categories': [{'label': k, 'amount': v} for k, v in categories.items()],
            'records': records, 'settlements': [{**app_v3.row_json(s), 'id': str(s['id']), 'revision': revision(s)} for s in settlements]}


@app_v3.app.get('/api/finance/dashboard')
@app_v3.token_required
def finance_dashboard():
    start, end = bounds(request.args)
    def where(column):
        clauses, params = [], []
        if start:
            clauses.append(f'{column}>=%s'); params.append(start)
        if end:
            clauses.append(f'{column}<%s'); params.append(end)
        return (' and '.join(clauses) or 'true'), params
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute('set transaction isolation level repeatable read read only')
        condition, params = where('coalesce(v.visited_at,v.created_at)')
        cur.execute("""select v.id,v.customer_id,v.service_type,v.payment_method,v.invoice_amount,
          v.received_amount,v.company_share_amount,v.customer_balance,
          coalesce(v.visited_at,v.created_at) date,trim(concat_ws(' ',c.first_name,c.last_name)) name
          from service_visits v left join customers_v2 c on c.id=v.customer_id
          where coalesce(v.status,'') not in ('cancelled','scheduled') and """ + condition +
                    ' order by coalesce(v.visited_at,v.created_at) desc,v.id', params)
        visits = cur.fetchall()
        condition, params = where('expense_date')
        cur.execute('select amount,category,expense_date from expenses where ' + condition, params)
        expenses = cur.fetchall()
        condition, params = where('settled_at')
        cur.execute('select * from company_settlements where ' + condition + ' order by settled_at desc,id', params)
        settlements = cur.fetchall()
        cur.execute("""select coalesce(sum(company_share_amount),0)::bigint amount from service_visits
          where coalesce(status,'') not in ('cancelled','scheduled')""")
        earned = int(cur.fetchone()['amount'])
        cur.execute('select coalesce(sum(amount),0)::bigint amount from company_settlements')
        paid = int(cur.fetchone()['amount'])
    payload = build_report(visits, expenses, settlements)
    payload['company_all_time'] = {'earned': earned, 'paid': paid, 'balance': earned - paid}
    payload['range'] = {'from': request.args.get('from') or '', 'to': request.args.get('to') or ''}
    payload['can_edit'] = app_v3.ROLE_LEVELS.get(request.current_user.get('role'), 0) >= app_v3.ROLE_LEVELS['admin']
    return jsonify(payload)


def check_revision(row, data):
    if not data.get('revision') or data['revision'] != revision(row):
        return jsonify({'error': 'این رکورد تغییر کرده؛ گزارش را تازه کنید و دوباره ویرایش کنید'}), 409


@app_v3.app.patch('/api/finance/payments/<visit_id>')
@app_v3.roles_required('admin')
def finance_payment_edit(visit_id):
    vid = uuid(visit_id, 'شناسه سرویس')
    data = request.get_json() or {}
    method = data.get('payment_method')
    if method not in LABELS or method == 'unknown':
        raise ValidationError('روش پرداخت معتبر را انتخاب کنید')
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute('select payment_method,received_amount from service_visits where id=%s for update', (vid,))
        before = cur.fetchone()
        if not before:
            return jsonify({'error': 'سرویس پیدا نشد'}), 404
        conflict = check_revision(before, data)
        if conflict:
            return conflict
        cur.execute('update service_visits set payment_method=%s,updated_at=now() where id=%s', (method, vid))
        app_v3.audit(cur, 'service', vid, 'finance_payment_edit', before=app_v3.row_json(before), after={'payment_method': method})
    return jsonify({'ok': True})


@app_v3.app.route('/api/settlements/<settlement_id>', methods=['PATCH', 'DELETE'])
@app_v3.roles_required('admin')
def finance_settlement_edit(settlement_id):
    sid = uuid(settlement_id, 'شناسه تسویه')
    data = request.get_json() or {}
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute('select * from company_settlements where id=%s for update', (sid,))
        before = cur.fetchone()
        if not before:
            return jsonify({'error': 'تسویه پیدا نشد'}), 404
        conflict = check_revision(before, data)
        if conflict:
            return conflict
        if request.method == 'DELETE':
            cur.execute('delete from company_settlements where id=%s', (sid,))
            app_v3.audit(cur, 'settlement', sid, 'delete', before=app_v3.row_json(before))
        else:
            amount = integer(data.get('amount'), 'مبلغ تسویه', minimum=1)
            settled_at = timestamp(data.get('settled_at'), 'تاریخ تسویه', required=True)
            notes = text(data.get('notes'), 'توضیحات', max_length=4000)
            cur.execute('update company_settlements set amount=%s,settled_at=%s,notes=%s where id=%s', (amount, settled_at, notes, sid))
            app_v3.audit(cur, 'settlement', sid, 'update', before=app_v3.row_json(before), after={'amount': amount, 'settled_at': settled_at.isoformat(), 'notes': notes})
    return jsonify({'ok': True})
