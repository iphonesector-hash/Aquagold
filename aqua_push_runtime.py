"""Web Push for new Bale jobs and client UI injection."""
from __future__ import annotations
import base64, hashlib, json
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from flask import jsonify, request
from pywebpush import WebPushException, webpush
import app_v3, bale_bridge

ORDER=int('FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551',16)
SUBJECT='https://aquagold-db.vercel.app'

def _b64(v): return base64.urlsafe_b64encode(v).rstrip(b'=').decode()
def _key():
    raw=hashlib.sha256((str(app_v3.app.secret_key)+'|aquagold-push-v1').encode()).digest()
    return ec.derive_private_key((int.from_bytes(raw,'big')%(ORDER-1))+1,ec.SECP256R1())
def _public(): return _b64(_key().public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint))
def _private(): return _b64(_key().private_bytes(serialization.Encoding.DER,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))

def _schema():
    with app_v3.get_db() as db, db.cursor() as c:
        c.execute("""create table if not exists push_subscriptions(
          id uuid primary key default gen_random_uuid(),user_id uuid not null references users(id) on delete cascade,
          endpoint text not null unique,p256dh text not null,auth text not null,user_agent text,active boolean not null default true,
          created_at timestamptz not null default now(),updated_at timestamptz not null default now(),last_success_at timestamptz,last_error text)""")
        c.execute("create index if not exists push_subscriptions_active_idx on push_subscriptions(active) where active=true")
        c.execute("create index if not exists push_subscriptions_user_idx on push_subscriptions(user_id,updated_at desc)")

def send_push(title,body,url='/?open=bale-jobs',tag='aquagold-work'):
    _schema(); payload=json.dumps({'title':title,'body':body,'url':url,'tag':tag},ensure_ascii=False)
    with app_v3.get_db() as db, db.cursor() as c:
        c.execute('select id,endpoint,p256dh,auth from push_subscriptions where active=true'); rows=[dict(x) for x in c.fetchall()]
    sent=failed=0
    for x in rows:
        try:
            webpush(subscription_info={'endpoint':x['endpoint'],'keys':{'p256dh':x['p256dh'],'auth':x['auth']}},data=payload,
                    vapid_private_key=_private(),vapid_claims={'sub':SUBJECT},timeout=6)
            sent+=1
            with app_v3.get_db() as db, db.cursor() as c: c.execute('update push_subscriptions set last_success_at=now(),last_error=null,updated_at=now() where id=%s',(x['id'],))
        except WebPushException as e:
            failed+=1; status=getattr(getattr(e,'response',None),'status_code',None)
            with app_v3.get_db() as db, db.cursor() as c:
                if status in {404,410}: c.execute('update push_subscriptions set active=false,last_error=%s,updated_at=now() where id=%s',(f'expired:{status}',x['id']))
                else: c.execute('update push_subscriptions set last_error=%s,updated_at=now() where id=%s',(str(e)[:500],x['id']))
        except Exception as e:
            failed+=1; app_v3.logger.warning('push_failed: %s',e)
    return {'sent':sent,'failed':failed}

@app_v3.app.get('/api/push/public-key')
@app_v3.roles_required('technician')
def push_public_key(): return jsonify({'public_key':_public()})

@app_v3.app.get('/api/push/status')
@app_v3.roles_required('technician')
def push_status():
    _schema()
    with app_v3.get_db() as db, db.cursor() as c:
        c.execute('select count(*)::int n from push_subscriptions where active=true and user_id=%s::uuid',(request.current_user['user_id'],)); n=int((c.fetchone() or {}).get('n') or 0)
    return jsonify({'supported':True,'active':n>0,'subscriptions':n})

@app_v3.app.post('/api/push/subscribe')
@app_v3.roles_required('technician')
def push_subscribe():
    _schema(); d=request.get_json(silent=True) or {}; k=d.get('keys') or {}; endpoint=str(d.get('endpoint') or '').strip(); p=str(k.get('p256dh') or '').strip(); a=str(k.get('auth') or '').strip()
    if not endpoint.startswith('https://') or not p or not a: return jsonify({'error':'اشتراک Push معتبر نیست'}),400
    with app_v3.get_db() as db, db.cursor() as c:
        c.execute("""insert into push_subscriptions(user_id,endpoint,p256dh,auth,user_agent,active,updated_at) values(%s::uuid,%s,%s,%s,%s,true,now())
          on conflict(endpoint) do update set user_id=excluded.user_id,p256dh=excluded.p256dh,auth=excluded.auth,user_agent=excluded.user_agent,active=true,last_error=null,updated_at=now() returning id""",
          (request.current_user['user_id'],endpoint[:4000],p[:1000],a[:1000],(request.user_agent.string or '')[:500])); row=c.fetchone()
    return jsonify({'ok':True,'id':str(row['id'])})

@app_v3.app.delete('/api/push/subscribe')
@app_v3.roles_required('technician')
def push_unsubscribe():
    _schema(); endpoint=str((request.get_json(silent=True) or {}).get('endpoint') or '').strip()
    with app_v3.get_db() as db, db.cursor() as c:
        if endpoint: c.execute('update push_subscriptions set active=false,updated_at=now() where user_id=%s::uuid and endpoint=%s',(request.current_user['user_id'],endpoint))
        else: c.execute('update push_subscriptions set active=false,updated_at=now() where user_id=%s::uuid',(request.current_user['user_id'],))
    return jsonify({'ok':True})

_old=app_v3.app.view_functions.get('bale_webhook')
def _webhook(secret):
    r=app_v3.app.make_response(_old(secret))
    try:
        d=r.get_json(silent=True) if r.is_json else {}; update=request.get_json(silent=True) or {}; msg,text,*_=bale_bridge._message_payload(update)
        if d.get('registered') and d.get('job_id') and msg and text:
            p=bale_bridge._extract_job(text) or {}; send_push('کار جدید AquaGold',f"{p.get('customer_name') or 'کار جدید'} • {p.get('job_type') or 'سرویس'}",tag=f"bale-{d['job_id']}")
    except Exception as e: app_v3.logger.warning('bale_push_hook_failed: %s',e)
    return r
if _old: app_v3.app.view_functions['bale_webhook']=_webhook

@app_v3.app.after_request
def _inject(response):
    try:
        if request.path in {'/','/index.html'} and response.mimetype=='text/html':
            response.direct_passthrough=False; body=response.get_data(as_text=True)
            if '/aqua-system-polish.js' not in body:
                p=body.lower().find('</head>')
                if p>=0: response.set_data(body[:p]+'<script src="/aqua-system-polish.js?v=20260831-2"></script>'+body[p:]); response.headers['Content-Length']=str(len(response.get_data()))
            response.headers['Cache-Control']='no-store, max-age=0'
    except Exception as e: app_v3.logger.warning('push_ui_inject_failed: %s',e)
    return response
