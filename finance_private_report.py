"""Daily finance-only summary sent to the registered private Bale account at 23:00 Tehran."""
from __future__ import annotations

from datetime import datetime, time, timezone

import app_v3
import bale_bridge
import bale_reports


def _finance_text(local_now):
    start=datetime.combine(local_now.date(),time.min,tzinfo=bale_reports.TEHRAN).astimezone(timezone.utc)
    end=local_now.astimezone(timezone.utc)
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("""select coalesce(sum(received_amount),0)::bigint received,
                              coalesce(sum(company_share_amount),0)::bigint company,
                              count(*)::int services
                       from service_visits where status not in ('cancelled','scheduled')
                       and coalesce(visited_at,created_at)>=%s and coalesce(visited_at,created_at)<%s""",(start,end))
        s=cur.fetchone() or {}
        cur.execute("select coalesce(sum(amount),0)::bigint expenses from expenses where created_at>=%s and created_at<%s",(start,end))
        e=cur.fetchone() or {}
    received=int(s.get('received') or 0);company=int(s.get('company') or 0);expenses=int(e.get('expenses') or 0)
    mine=received-company;net=mine-expenses
    return '\n'.join([
        '📈 گزارش مالی روزانه AquaGold',f"📅 {bale_reports._fa_date(local_now.date())}",'',
        f"💰 کل دریافتی: {bale_reports._fa_number(received)} تومان",
        f"🏢 سهم شرکت: {bale_reports._fa_number(company)} تومان",
        f"👤 سهم شما: {bale_reports._fa_number(mine)} تومان",
        f"💸 هزینه‌ها: {bale_reports._fa_number(expenses)} تومان",
        f"✨ خالص امروز: {bale_reports._fa_number(net)} تومان",
        f"🧾 تعداد سرویس: {bale_reports._fa_number(s.get('services'))}",
        '', 'این گزارش فقط به حساب شخصی بله ارسال شده است.'
    ])


def send_private_finance(local_now):
    raw=bale_reports._settings();chat_id=str(raw.get('chat_id') or '').strip();bot=bale_bridge._load_settings()
    if not chat_id:return {'ok':False,'finance':'private_recipient_not_configured'}
    if not bot.get('bot_token'):return {'ok':False,'finance':'bale_token_not_configured'}
    key=local_now.date().isoformat()
    if str(raw.get('last_private_finance') or '')==key:return {'ok':True,'finance':'already_sent'}
    bale_bridge._bale_call(bot['bot_token'],'sendMessage',{'chat_id':chat_id,'text':_finance_text(local_now)},timeout=12)
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select value from app_settings where key=%s for update",(bale_reports.REPORTS_KEY,));row=cur.fetchone();settings=dict((row or {}).get('value') or {});settings['last_private_finance']=key;bale_reports._save_settings(cur,settings)
    return {'ok':True,'finance':'sent_private'}


_original_cron=app_v3.app.view_functions.get('bale_reports_cron')
def _cron_with_private_finance():
    response=app_v3.app.make_response(_original_cron())
    if response.status_code<300:
        try:
            result=send_private_finance(datetime.now(bale_reports.TEHRAN))
            if response.is_json:
                payload=response.get_json() or {};payload['private_finance']=result;return app_v3.jsonify(payload),response.status_code
        except Exception as exc:
            app_v3.logger.warning('private_finance_report_failed: %s',exc)
    return response
if _original_cron is not None:app_v3.app.view_functions['bale_reports_cron']=_cron_with_private_finance
