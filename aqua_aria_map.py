"""Authenticated Aria address intent wired to the existing AquaGold map adapter.

This layer changes only address-to-map behavior. Aqua/Aria voice, web search,
provider/model selection and microphone runtime are intentionally left untouched.
"""
from __future__ import annotations

import re

from flask import Response, jsonify, request

import app_routing
import app_v3
import aqua_neshan_preview as neshan
import aqua_smart_tour
import aqua_today_tour
from aqua_map_address import normalize_persian_address


_SMART_ACTIVE_TODAY_ROWS = aqua_smart_tour._active_today_rows


def _active_today_and_overdue_rows():
    """Return today's jobs plus unfinished older new/review jobs, never future jobs."""
    today = list(_SMART_ACTIVE_TODAY_ROWS())
    seen = {str(row.get("id")) for row in today}
    now = aqua_smart_tour._now()
    try:
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute(
                """select id,customer_id,status,customer_name,phone,address,job_type,raw_text,parsed,received_at,updated_at
                   from bale_jobs where status in ('new','review') order by received_at asc limit 100"""
            )
            raw_rows = cur.fetchall()
    except Exception:
        app_v3.logger.warning("aria_map_overdue_tour_read_failed", exc_info=True)
        return today

    for raw in raw_rows:
        row = app_v3.row_json(raw)
        if str(row.get("id")) in seen:
            continue
        try:
            received = row.get("received_at")
            received_local = (
                received.astimezone(aqua_smart_tour.TEHRAN)
                if hasattr(received, "astimezone")
                else aqua_smart_tour.datetime.fromisoformat(str(received).replace("Z", "+00:00")).astimezone(aqua_smart_tour.TEHRAN)
            )
            if received_local.date() >= now.date():
                continue
        except Exception:
            continue
        row["id"] = str(row["id"])
        if row.get("customer_id"):
            row["customer_id"] = str(row["customer_id"])
        row["phone"] = aqua_smart_tour._extract_phone(row.get("phone"), row.get("raw_text"))
        row["display_name"] = aqua_smart_tour._extract_customer_name(row)
        prior = aqua_smart_tour._parse_schedule(row, received_local)
        prior_label = (prior or {}).get("label") or received_local.strftime("%Y-%m-%d")
        schedule = {
            "immediate": False,
            "start": now,
            "end": now.replace(hour=23, minute=59, second=0, microsecond=0),
            "label": f"عقب‌افتاده • {prior_label}",
        }
        row["schedule"] = {
            "immediate": False,
            "start": schedule["start"].isoformat(),
            "end": schedule["end"].isoformat(),
            "label": schedule["label"],
        }
        row["_schedule"] = schedule
        row["overdue"] = True
        today.append(row)
        seen.add(row["id"])
        if len(today) >= aqua_smart_tour.MAX_TOUR_JOBS:
            break
    return today


aqua_smart_tour._active_today_rows = _active_today_and_overdue_rows
aqua_today_tour._active_rows = _active_today_and_overdue_rows


_ORIGINAL_CHAT = app_v3.app.view_functions.get("aqua_chat")
_ADDRESS_VERBS = ("پیدا کن", "نشون بده", "نشان بده", "روی نقشه", "باز کن", "مسیر")
_CONTEXT_WORDS = ("اطرافش", "اونجا", "همین آدرس", "این آدرس", "این نقطه")
_FILLER_WORDS = ("آریا", "لطفا", "لطفاً", "رو", "را", "برام", "برای من")


def _strip_filler_words(value):
    cleaned = value
    cleaned = re.sub(r"(?:روی\s+نقشه\s*)?(?:نشون بده|نشان بده|پیدا کن|باز کن)", " ", cleaned)
    cleaned = re.sub(r"^(?:برو\s+به|مسیر(?:\s+به)?)\s*", "", cleaned)
    for token in _FILLER_WORDS:
        cleaned = re.sub(rf"(?<!\S){re.escape(token)}(?!\S)", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" ،,.-")


def extract_address_intent(value):
    text = normalize_persian_address(value)
    if any(word in text for word in _CONTEXT_WORDS):
        return {"context": True, "address": ""}
    if "مشتری" in text:
        return None
    if not any(word in text for word in _ADDRESS_VERBS):
        return None
    return {"context": False, "address": _strip_filler_words(text)}


def _is_contextually_specific(query):
    locality = (
        "تهران", "کرج", "مرزداران", "صادقیه", "آریاشهر", "پونک", "ستارخان",
        "یوسف آباد", "یوسف‌آباد", "سعادت آباد", "سعادت‌آباد", "تهرانسر",
        "فردیس", "شهر", "استان",
    )
    return any(token in query for token in locality) and len(query.split()) >= 2


def _decorate_result(item, index, query, source):
    latitude = item.get("latitude")
    longitude = item.get("longitude")
    if latitude is None or longitude is None:
        return None
    formatted = str(
        item.get("formatted_address")
        or item.get("address")
        or item.get("display_name")
        or "، ".join(
            str(item.get(key) or "").strip()
            for key in ("neighbourhood", "city", "province")
            if str(item.get(key) or "").strip()
        )
        or query
    ).strip()
    title = str(
        item.get("title")
        or item.get("name")
        or item.get("neighbourhood")
        or item.get("city")
        or formatted
        or query
    ).strip()
    return {
        **item,
        "id": str(item.get("id") or f"aria-address-{index}"),
        "kind": "address",
        "name": title,
        "title": title,
        "address": formatted,
        "formatted_address": formatted,
        "latitude": float(latitude),
        "longitude": float(longitude),
        "source": source,
    }


def _neshan_address_results(query, limit=3):
    payload = neshan.geocode_address(query, plus=True)
    results = []
    for index, raw in enumerate((payload.get("items") or [])[:limit], 1):
        location = raw.get("location") or {}
        decorated = _decorate_result(
            {
                **raw,
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "unmatched": str(raw.get("unMatchedTerm") or "").strip(),
            },
            index,
            query,
            "neshan",
        )
        if decorated:
            results.append(decorated)
    return results


def _address_results(query, limit=3):
    try:
        results = _neshan_address_results(query, limit)
        if results:
            return results
    except Exception as exc:
        app_v3.logger.warning("aria_map_neshan_geocode_failed detail=%s", str(exc)[:180])
    provider_results = app_routing.geocode_provider(query, limit)
    results = []
    for index, item in enumerate(provider_results[:limit], 1):
        decorated = _decorate_result(item, index, query, "fallback-geocode")
        if decorated:
            results.append(decorated)
    return results


@app_v3.roles_required("technician")
@app_v3.limiter.limit("20 per minute; 200 per day")
def aria_map_chat():
    payload = request.get_json(silent=True) or {}
    intent = extract_address_intent(payload.get("text"))
    if intent is None:
        return _ORIGINAL_CHAT()
    if intent["context"]:
        return jsonify({
            "answer": "اول یک آدرس را پیدا و از بین نتیجه‌ها انتخاب کن؛ بعد بگو مشتری‌های اطرافش را نشان بدهم.",
            "needs_location_context": True,
        })
    query = intent["address"]
    if len(query) < 3:
        return jsonify({"answer": "اسم محله یا خیابون اصلی رو هم بگو.", "results": []})
    try:
        results = _address_results(query, 3)
    except Exception:
        app_v3.logger.exception("aria_map_geocoding_failed")
        return jsonify({"answer": "فعلاً ارتباط با سرویس نقشه برقرار نشد. دوباره امتحان کن."}), 503
    if not results:
        return jsonify({"answer": "این آدرس رو دقیق پیدا نکردم. اسم محله یا خیابون اصلی رو هم بگو.", "results": []})
    first = results[0]
    precise_first = (
        _is_contextually_specific(query)
        and not str(first.get("unmatched") or "").strip()
        and first.get("source") == "neshan"
    )
    if len(results) != 1 and not precise_first:
        return jsonify({
            "answer": "چند جای مشابه پیدا کردم. کدومش منظورت بود؟",
            "query": query,
            "multiple_results": True,
            "results": results,
        })
    return jsonify({
        "answer": "پیداش کردم؛ روی نقشه نشونش می‌دم.",
        "query": query,
        "results": results,
        "action": {"type": "show_address_on_map", "location": first},
    })


if _ORIGINAL_CHAT is not None:
    app_v3.app.view_functions["aqua_chat"] = aria_map_chat


@app_v3.app.get("/aqua-aria-map.js")
def aria_map_js():
    return app_v3.send_from_directory(".", "aqua-aria-map.js", mimetype="application/javascript", max_age=0)


FINAL_RUNTIME_JS = r'''(()=>{'use strict';
if(window.__aqFinalCompletion)return;window.__aqFinalCompletion=1;
const $=(s,r=document)=>r.querySelector(s),fa=v=>String(v??'').replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[+d]),pad=n=>String(+n||0).padStart(2,'0');
const months=['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function state(){try{return Alpine?.$data?.(document.body)||document.body?._x_dataStack?.[0]}catch{return null}}
function jp(v){const o={};new Intl.DateTimeFormat('en-US-u-ca-persian',{timeZone:'Asia/Tehran',year:'numeric',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(v?new Date(v):new Date()).forEach(p=>{if(/^(year|month|day|hour|minute)$/.test(p.type))o[p.type]=+p.value});return o}
function greg(y,m,d){let x=new Date(Date.UTC(+y+621,2,1,12));for(let i=0;i<400;i++,x.setUTCDate(x.getUTCDate()+1)){const p=jp(x);if(p.year==y&&p.month==m&&p.day==d)return{x:x.getUTCFullYear(),m:x.getUTCMonth()+1,d:x.getUTCDate()}}}
function mdays(y,m){return m<=6?31:m<=11?30:greg(y,12,30)?30:29}
function syncExpense(s){const p=s.__aqExpenseJ,g=greg(p.y,p.m,p.d);if(!g)return false;s.expenseForm.expense_date=`${g.x}-${pad(g.m)}-${pad(g.d)}T${pad(p.h)}:${pad(p.i)}:00+03:30`;return true}
function field(label,items,current,change){const l=document.createElement('label');l.className='aqj-field';l.textContent=label;const q=document.createElement('select');q.className='field';for(const a of items){const o=document.createElement('option');o.value=a.v;o.textContent=a.t;o.selected=String(a.v)===String(current);q.append(o)}q.onchange=()=>change(q.value);l.append(q);return l}
function expensePicker(s,reset=false){const sec=[...document.querySelectorAll('section')].find(x=>x.querySelector('h2')?.textContent?.includes('هزینه‌ها و خریدها')),native=sec?.querySelector('input[x-model="expenseForm.expense_date"]');if(!native)return;native.type='hidden';native.classList.add('aqj-native');let host=$('#aqExpenseJalaliCreate',sec);if(reset)host?.remove(),host=null;if(!s.__aqExpenseJ||reset){const p=jp(s.expenseForm?.expense_date||new Date());s.__aqExpenseJ={y:p.year,m:p.month,d:p.day,h:p.hour||0,i:p.minute||0}}const p=s.__aqExpenseJ;if(!host){host=document.createElement('div');host.id='aqExpenseJalaliCreate';host.className='aqj';native.before(host)}host.replaceChildren();const t=document.createElement('b');t.textContent='تاریخ و ساعت هزینه (شمسی)';host.append(t);const dg=document.createElement('div');dg.className='aqj-date';host.append(dg);let years=[];for(let y=p.y-3;y<=p.y+3;y++)years.push({v:y,t:fa(y)});dg.append(field('سال',years,p.y,v=>{p.y=+v;p.d=Math.min(p.d,mdays(p.y,p.m));expensePicker(s);syncExpense(s)}),field('ماه',months.map((t,i)=>({v:i+1,t})),p.m,v=>{p.m=+v;p.d=Math.min(p.d,mdays(p.y,p.m));expensePicker(s);syncExpense(s)}),field('روز',Array.from({length:mdays(p.y,p.m)},(_,i)=>({v:i+1,t:fa(i+1)})),p.d,v=>{p.d=+v;syncExpense(s)}));const tg=document.createElement('div');tg.className='aqj-time';host.append(tg);tg.append(field('ساعت',Array.from({length:24},(_,i)=>({v:i,t:fa(pad(i))})),p.h,v=>{p.h=+v;syncExpense(s)}),field('دقیقه',Array.from({length:60},(_,i)=>({v:i,t:fa(pad(i))})),p.i,v=>{p.i=+v;syncExpense(s)}));syncExpense(s)}
function fixEdit(s){try{s.ensureExpenseJalaliPicker?.()}catch{}const p=$('#expenseJalaliPicker');if(p){p.style.cssText+=';width:100%!important;max-width:100%!important;min-width:0!important;overflow:hidden!important'}const modal=[...document.querySelectorAll('h3')].find(x=>x.textContent?.includes('ویرایش هزینه'))?.closest('.fixed,[style*="position:fixed"]');[...modal?.querySelectorAll('label')||[]].find(x=>x.textContent?.includes('تاریخ و ساعت هزینه'))?.style.setProperty('display','none','important')}
function mapLayout(){const c=$('#aqst-controls'),d=$('#aqst-tour-details');if(c&&d){if(c.nextElementSibling!==d)d.parentNode.insertBefore(c,d);c.classList.add('aq-controls-below')}$('#aquaTodayTourLaunch')?.remove()}
function card(s,l){let c=$('#ariaMapCard'),d=$('#aqst-tour-details');if(!c){c=document.createElement('div');c.id='ariaMapCard';c.className='card p-4 mt-3';(d?.parentNode||$('#mainMap')?.parentElement?.parentElement)?.insertBefore(c,d||null)}if(!c)return;c.style.display='block';c.removeAttribute('x-show');c.innerHTML=`<b>${esc(l.title||l.name||'نتیجه آدرس')}</b><div class="text-sm muted">${esc(l.formatted_address||l.address||'')}</div><div class="flex flex-wrap gap-2 mt-3"><button class="btn primary" data-nav>مسیریابی</button><button class="btn soft" data-near>مشتری‌های اطراف</button><button class="btn glass" data-close>بستن</button></div>`;c.querySelector('[data-nav]').onclick=()=>s.ariaNavigate?.();c.querySelector('[data-near]').onclick=()=>s.ariaNearby?.();c.querySelector('[data-close]').onclick=()=>{s.ariaLocation=null;try{s.ariaSearchMarker?.remove()}catch{}s.ariaSearchMarker=null;c.style.display='none'}}
function show(s,l){const a=+l?.latitude,b=+l?.longitude;if(!Number.isFinite(a)||!Number.isFinite(b))return false;s.ariaLocation={...l,latitude:a,longitude:b};s.page='map';let n=0;(function draw(){n++;try{s.renderMainMap?.()}catch{}if(!s.mainMap||!window.L){if(n<25)setTimeout(draw,100);return}try{s.ariaSearchMarker?.remove()}catch{}const i=L.divIcon({className:'aq-aria-marker',html:'<span>◆</span>',iconSize:[38,42],iconAnchor:[19,38]});s.ariaSearchMarker=L.marker([a,b],{icon:i}).addTo(s.mainMap).bindPopup(`<div dir="rtl"><b>${esc(l.title||l.name||'نتیجه آدرس')}</b><br>${esc(l.formatted_address||l.address||'')}</div>`).openPopup();s.mainMap.setView([a,b],17);setTimeout(()=>s.mainMap.invalidateSize?.(),50);card(s,s.ariaLocation);mapLayout()})();return true}
function patch(s){if(!s||s.__aqFinalCompletion)return;s.__aqFinalCompletion=1;expensePicker(s);const ce=s.createExpense?.bind(s);if(ce)s.createExpense=async function(...a){syncExpense(this);const r=await ce(...a);if(!this.expenseForm?.title&&!this.expenseForm?.amount)setTimeout(()=>expensePicker(this,true),30);return r};const oe=s.openExpenseEdit?.bind(s);if(oe)s.openExpenseEdit=function(...a){const r=oe(...a);setTimeout(()=>fixEdit(this),30);return r};const ra=s.runAquaAction?.bind(s);s.runAquaAction=function(a){if(a?.type==='show_address_on_map')return show(this,a.location);if(a?.customer?.kind==='address')return show(this,a.customer);return ra?.(a)};s.showAriaAddress=function(l){return show(this,l)};const st=s.submitAquaText?.bind(s);if(st)s.submitAquaText=async function(v,src='text'){const ok=await st(v,src),m=this.aquaMessages?.at?.(-1)||this.aquaMessages?.[this.aquaMessages.length-1];if(ok&&m?.results?.length)m.results=m.results.map((r,i)=>{const a=r.formatted_address||r.address||r.display_name||r.title||r.name||'';return{...r,id:r.id||`aria-address-${i}`,kind:r.kind||'address',name:r.name||r.title||a,title:r.title||r.name||a,address:a,formatted_address:r.formatted_address||a}});if(ok&&m?.action?.type==='show_address_on_map')setTimeout(()=>this.runAquaAction(m.action),30);return ok};mapLayout();fixEdit(s)}
function css(){if($('#aq-final-style'))return;const x=document.createElement('style');x.id='aq-final-style';x.textContent=`.aqj{width:100%;min-width:0;max-width:100%;overflow:hidden;border:1px solid var(--line);border-radius:17px;padding:10px;background:var(--surface-2)}.aqj>b{display:block;color:var(--muted);font-size:.78rem;margin-bottom:7px}.aqj-date{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}.aqj-time{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;margin-top:6px}.aqj-field{min-width:0;font-size:.68rem;color:var(--muted)}.aqj-field select{display:block;width:100%!important;min-width:0!important;max-width:100%!important;margin-top:3px;padding:.7rem .45rem!important;font-size:16px!important}.aqj-native{display:none!important}#expenseJalaliPicker,#expenseJalaliPicker *{box-sizing:border-box;min-width:0}#expenseJalaliPicker{width:100%!important;max-width:100%!important;overflow:hidden!important}#expenseJalaliPicker select{width:100%!important;max-width:100%!important;font-size:16px!important}#aqst-controls.aq-controls-below{position:relative!important;inset:auto!important;transform:none!important;width:100%!important;max-width:100%!important;margin:2px 0 6px!important;padding:0!important;z-index:4!important}#aqst-controls.aq-controls-below .aqst-toolbar{margin:0!important}#ariaMapCard{width:100%;max-width:100%;min-width:0;overflow:hidden}@media(max-width:600px){#aqst-controls.aq-controls-below .aqst-toolbar{grid-template-columns:1fr!important}}`;document.head.append(x)}
function boot(){css();let n=0;const t=setInterval(()=>{n++;const s=state();patch(s);mapLayout();if(s)expensePicker(s);if(n>100)clearInterval(t)},100);new MutationObserver(()=>{const s=state();patch(s);mapLayout();if(s&&!$('#aqExpenseJalaliCreate'))expensePicker(s)}).observe(document.documentElement,{subtree:true,childList:true})}
document.readyState==='loading'?document.addEventListener('DOMContentLoaded',boot,{once:true}):boot();
})();
'''


@app_v3.app.get("/aqua-final-task-fix.js")
def final_task_fix_js():
    return Response(FINAL_RUNTIME_JS, mimetype="application/javascript", headers={"Cache-Control": "no-store"})


@app_v3.app.after_request
def inject_aria_map(response):
    if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        if "aq-aria-marker" not in body:
            body = body.replace(
                "</head>",
                '<style>.aq-aria-marker{background:transparent;border:0}.aq-aria-marker span{display:grid;place-items:center;width:38px;height:38px;border:3px solid white;border-radius:14px;background:#7c3aed;color:white;box-shadow:0 8px 24px #0008}.bottom-nav{padding-bottom:max(8px,env(safe-area-inset-bottom));background:var(--surface-2)}#ariaMapCard{margin-bottom:max(0px,env(safe-area-inset-bottom))}</style></head>',
                1,
            )
        if "/aqua-aria-map.js" not in body:
            body = body.replace("</body>", '<script src="/aqua-aria-map.js?v=20260914-3"></script></body>', 1)
        if "/aqua-final-task-fix.js" not in body:
            body = body.replace("</body>", '<script src="/aqua-final-task-fix.js?v=20260914-2"></script></body>', 1)
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
    return response
