from datetime import datetime, timezone
from uuid import uuid4
import pytest
import app_v3
from aqua_finance_dashboard import build_report, payment_key, bounds, revision
from aquagold_validation import ValidationError


def visit(amount=100, method='cash', **extra):
    return {'id': uuid4(), 'customer_id': 'c1', 'name': 'آزمایش', 'date': '2026-09-07T22:00:00+03:30',
            'received_amount': amount, 'invoice_amount': amount, 'company_share_amount': amount // 2,
            'customer_balance': 0, 'payment_method': method, **extra}


def test_payment_aliases_and_unknown_never_guess():
    assert [payment_key(x) for x in ('نقدی', 'کارت‌خوان', 'card_reader', 'کارت به کارت', 'card-to-card')] == ['cash','card','card','transfer','transfer']
    assert payment_key(None) == payment_key('روش قدیمی ناشناخته') == 'unknown'
    assert payment_key('other') == 'other'
    r = build_report([visit(100,'cash'),visit(200,'pos'),visit(300,'transfer'),visit(400,None),visit(500,'other')],[],[])
    assert sum(p['amount'] for p in r['payments']) == r['totals']['received'] == 1500
    assert {p['key']:p['amount'] for p in r['payments']}['unknown'] == 400


def test_all_rows_not_page_slice_and_expense_only_days():
    r = build_report([visit() for _ in range(301)], [{'amount':20000,'category':'parts','expense_date':'2026-09-08T12:00:00Z'}], [])
    assert r['totals']['received'] == 30100
    assert r['totals']['services'] == 301
    assert r['totals']['net_profit'] == -4950
    assert r['days'][-1]['net_profit'] == -20000
    assert len(r['records']) == 301


def test_tehran_day_boundary_and_negative_company_balance():
    s={'id':uuid4(),'amount':300,'notes':'test','settled_at':datetime(2026,9,7,21,tzinfo=timezone.utc)}
    r=build_report([visit(200,date='2026-09-07T21:00:00Z')],[],[s])
    assert r['days'][0]['date']=='2026-09-08'
    assert r['totals']['company_net']==-200
    assert r['settlements'][0]['revision']==revision(s)


def test_date_range_inclusive_tehran_and_validation():
    start,end=bounds({'from':'2026-09-07','to':'2026-09-07'})
    assert (end-start).days==1
    assert start.isoformat()=='2026-09-07T00:00:00+03:30'
    for args in ({'from':'wrong'}, {'from':'2026-09-08','to':'2026-09-07'}):
        with pytest.raises(ValidationError):bounds(args)


def test_revision_detects_payment_and_settlement_change():
    v=visit()
    assert revision(v)==revision({'payment_method':v['payment_method'],'received_amount':v['received_amount']})
    assert revision(v)!=revision({**v,'payment_method':'card'})
    assert revision({'amount':10})!=revision({'amount':11})


def test_empty_report_is_zero_and_no_fake_points():
    r=build_report([],[],[])
    assert all(v==0 for v in r['totals'].values())
    assert r['days']==r['records']==r['settlements']==[]


def test_finance_requires_authentication():
    c=app_v3.app.test_client()
    assert c.get('/api/finance/dashboard').status_code==401
    assert c.patch('/api/finance/payments/'+str(uuid4()),json={}).status_code==401
    assert c.delete('/api/settlements/'+str(uuid4()),json={}).status_code==401
