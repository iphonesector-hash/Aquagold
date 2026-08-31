"""Nightly private Bale finance image for AquaGold."""
from __future__ import annotations
import json,secrets,urllib.request
from datetime import datetime,time,timedelta,timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
import arabic_reshaper
from bidi.algorithm import get_display
from flask import jsonify
from PIL import Image,ImageDraw,ImageFont
import app_v3,bale_bridge,bale_reports
T=ZoneInfo('Asia/Tehran'); FA=str.maketrans('0123456789','۰۱۲۳۴۵۶۷۸۹')
def _num(v):
    try:v=int(round(float(v or 0)))
    except:v=0
    return f'{v:,}'.replace(',','٬').translate(FA)
def _shape(s): return get_display(arabic_reshaper.reshape(str(s or '')))
def _font(n,b=False):
    root=Path(__file__).resolve().parent; names=[root/'vendor/fonts'/('Vazirmatn-Bold.woff2' if b else 'Vazirmatn-Regular.woff2'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if b else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    for p in names:
        try:
            if p.exists(): return ImageFont.truetype(str(p),n)
        except: pass
    return ImageFont.load_default()
def _rtl(d,s,x,y,f,c):
    s=_shape(s); b=d.textbbox((0,0),s,font=f); d.text((x-(b[2]-b[0]),y),s,font=f,fill=c)

def _data(now):
    start=datetime.combine(now.date(),time.min,tzinfo=T); end=start+timedelta(days=1); week=start-timedelta(days=6); a,b=start.astimezone(timezone.utc),end.astimezone(timezone.utc)
    with app_v3.get_db() as db,db.cursor() as c:
        c.execute("""select coalesce(sum(received_amount),0)::bigint received,coalesce(sum(company_share_amount),0)::bigint company,count(*)::int services from service_visits
          where status not in ('cancelled','scheduled') and coalesce(visited_at,created_at)>=%s and coalesce(visited_at,created_at)<%s""",(a,b)); total=dict(c.fetchone() or {})
        c.execute('select coalesce(sum(amount),0)::bigint expenses from expenses where expense_date>=%s and expense_date<%s',(a,b)); total['expenses']=int((c.fetchone() or {}).get('expenses') or 0); total['profit']=int(total.get('received') or 0)-int(total.get('company') or 0)-total['expenses']
        c.execute("""select coalesce(service_type,'نامشخص') label,coalesce(sum(received_amount),0)::bigint value from service_visits where status not in ('cancelled','scheduled')
          and coalesce(visited_at,created_at)>=%s and coalesce(visited_at,created_at)<%s group by 1 order by value desc limit 5""",(a,b)); services=[dict(x) for x in c.fetchall()]
        c.execute("""select date(coalesce(visited_at,created_at) at time zone 'Asia/Tehran') day,coalesce(sum(received_amount),0)::bigint received,coalesce(sum(company_share_amount),0)::bigint company
          from service_visits where status not in ('cancelled','scheduled') and coalesce(visited_at,created_at)>=%s and coalesce(visited_at,created_at)<%s group by 1""",(week.astimezone(timezone.utc),b)); hist={x['day']:[int(x['received'] or 0),int(x['company'] or 0),0] for x in c.fetchall()}
        c.execute("select date(expense_date at time zone 'Asia/Tehran') day,coalesce(sum(amount),0)::bigint expenses from expenses where expense_date>=%s and expense_date<%s group by 1",(week.astimezone(timezone.utc),b))
        for x in c.fetchall(): hist.setdefault(x['day'],[0,0,0])[2]=int(x['expenses'] or 0)
    series=[]
    for i in range(7):
        day=(week+timedelta(days=i)).date(); r,co,e=hist.get(day,[0,0,0]); series.append((day,r,r-co-e))
    return total,services,series

def _png(now):
    total,services,series=_data(now); W,H=1200,1500; bg=(5,18,23); card=(14,37,42); white=(235,250,250); muted=(139,168,174); teal=(42,190,178); cyan=(49,200,207); violet=(139,92,246); amber=(245,158,11); rose=(244,63,94)
    im=Image.new('RGB',(W,H),bg); d=ImageDraw.Draw(im); f48=_font(48,1); f30=_font(30,1); f34=_font(34,1); f22=_font(22)
    d.rounded_rectangle((45,38,1155,180),34,fill=(8,49,56)); _rtl(d,'گزارش تصویری مالی AquaGold',1110,65,f48,white); _rtl(d,bale_reports._fa_date(now.date()),1110,125,f22,(156,235,230))
    stats=[('دریافتی امروز',total.get('received'),teal),('سهم شرکت',total.get('company'),cyan),('هزینه‌ها',total.get('expenses'),amber),('سود خالص',total.get('profit'),violet if total.get('profit',0)>=0 else rose)]; boxes=[(45,215,575,375),(625,215,1155,375),(45,405,575,565),(625,405,1155,565)]
    for (label,val,color),box in zip(stats,boxes): d.rounded_rectangle(box,28,fill=card,outline=color,width=2); _rtl(d,label,box[2]-30,box[1]+25,f22,muted); _rtl(d,f'{_num(val)} تومان',box[2]-30,box[1]+78,f34,color)
    d.rounded_rectangle((45,600,730,1040),30,fill=card); _rtl(d,'روند ۷ روز اخیر',690,625,f30,white); maxv=max([max(r,p,0) for _,r,p in series]+[1]); pr=[]; pp=[]
    for i,(day,r,p) in enumerate(series): x=85+i*605/6; pr.append((x,980-max(r,0)/maxv*270)); pp.append((x,980-max(p,0)/maxv*270)); d.text((x-8,992),str(day.day).translate(FA),font=f22,fill=muted)
    if len(pr)>1:d.line(pr,fill=teal,width=6,joint='curve');d.line(pp,fill=violet,width=5,joint='curve')
    for x,y in pr:d.ellipse((x-6,y-6,x+6,y+6),fill=teal)
    for x,y in pp:d.ellipse((x-5,y-5,x+5,y+5),fill=violet)
    d.rounded_rectangle((770,600,1155,1040),30,fill=card); _rtl(d,'ترکیب مالی امروز',1120,625,f30,white); vals=[max(int(total.get('company') or 0),0),max(int(total.get('expenses') or 0),0),max(int(total.get('profit') or 0),0)]; cols=[cyan,amber,violet]; sm=sum(vals); angle=-90
    if sm:
        for v,col in zip(vals,cols): a=360*v/sm; d.pieslice((830,695,1090,955),start=angle,end=angle+a,fill=col); angle+=a
    else:d.ellipse((830,695,1090,955),fill=(43,63,68))
    d.ellipse((888,753,1032,897),fill=card); _rtl(d,'شرکت • هزینه • سود',1110,985,f22,muted)
    d.rounded_rectangle((45,1080,1155,1445),30,fill=card); _rtl(d,'سرویس‌های برتر امروز',1110,1105,f30,white); mx=max([int(x.get('value') or 0) for x in services]+[1]); y=1175; pal=[teal,cyan,violet,amber,rose]
    if not services:_rtl(d,'امروز سرویس مالی ثبت نشده است',1110,1240,f22,muted)
    for i,x in enumerate(services[:5]): v=int(x.get('value') or 0); d.rounded_rectangle((180,y+14,180+int(650*v/mx),y+42),14,fill=pal[i%5]); _rtl(d,x.get('label') or 'نامشخص',1110,y,f22,white); _rtl(d,_num(v),150,y,f22,muted); y+=52
    out=BytesIO(); im.save(out,'PNG',optimize=True); return out.getvalue(),total

def _photo(token,chat,png,caption):
    b='----AquaGold'+secrets.token_hex(10); parts=[]
    def field(n,v):parts.extend([f'--{b}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n'.encode(),str(v).encode(),b'\r\n'])
    field('chat_id',chat);field('caption',caption);parts.extend([f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="finance.png"\r\nContent-Type: image/png\r\n\r\n'.encode(),png,b'\r\n',f'--{b}--\r\n'.encode()])
    q=urllib.request.Request(bale_bridge.BALE_API.format(token=token,method='sendPhoto'),data=b''.join(parts),headers={'Content-Type':f'multipart/form-data; boundary={b}'},method='POST')
    with urllib.request.urlopen(q,timeout=18) as r: raw=r.read().decode(errors='replace'); return json.loads(raw) if raw else {'ok':True}

def send_private_finance_image(now=None,force=False):
    now=now or datetime.now(T); key=now.date().isoformat(); st=bale_reports._settings(); chat=str(st.get('chat_id') or '').strip(); bot=bale_bridge._load_settings()
    if not force and str(st.get('last_finance_image') or '')==key:return {'ok':True,'skipped':'already_sent','key':key}
    if not chat or not bot.get('bot_token'):return {'ok':False,'error':'private_bale_recipient_not_configured'}
    png,total=_png(now); result=_photo(bot['bot_token'],chat,png,f"📊 گزارش تصویری مالی AquaGold • {bale_reports._fa_date(now.date())}")
    if not result.get('ok',True):return {'ok':False,'error':'bale_send_photo_failed'}
    with app_v3.get_db() as db,db.cursor() as c:
        c.execute('select value from app_settings where key=%s for update',(bale_reports.REPORTS_KEY,)); row=c.fetchone(); raw=dict((row or {}).get('value') or {}); raw['last_finance_image']=key; bale_reports._save_settings(c,raw)
    return {'ok':True,'sent':True,'key':key,'received':int(total.get('received') or 0)}

@app_v3.app.post('/api/reports/finance-image/send')
@app_v3.roles_required('admin')
def finance_image_send_now(): return jsonify(send_private_finance_image(force=True))
_old=app_v3.app.view_functions.get('bale_reports_cron')
def _cron():
    r=app_v3.app.make_response(_old())
    try:
        now=datetime.now(T)
        if r.status_code<400 and now.hour==23:
            x=send_private_finance_image(now)
            if not x.get('ok'):app_v3.logger.warning('finance_image_cron_failed: %s',x)
    except Exception as e:app_v3.logger.warning('finance_image_cron_exception: %s',e)
    return r
if _old:app_v3.app.view_functions['bale_reports_cron']=_cron
