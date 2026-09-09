"""Branch-scoped Phase 4C normal Map workspace.

Keeps the approved routing/navigation stack intact while decluttering the normal
Map page into floating collapsible controls and adding per-user saved special
locations backed by app_settings (no schema migration).
"""
from __future__ import annotations

import math
from uuid import uuid4

from flask import jsonify, request
from psycopg.types.json import Jsonb

import app_v3
from aquagold_validation import text as valid_text

_MAX_SPECIAL_LOCATIONS = 100


def _settings_key() -> str:
    user_id = str((getattr(request, "current_user", {}) or {}).get("user_id") or "").strip()
    if not user_id:
        raise RuntimeError("authenticated user is required")
    return f"map_special_locations:{user_id}"


def _coord(value, label: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise app_v3.ValidationError(f"{label} نامعتبر است") from None
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise app_v3.ValidationError(f"{label} نامعتبر است")
    return number


def _read_locations(cur, *, lock: bool = False) -> list[dict]:
    sql = "select value from app_settings where key=%s"
    if lock:
        sql += " for update"
    cur.execute(sql, (_settings_key(),))
    row = cur.fetchone()
    value = (row or {}).get("value") if row else None
    if isinstance(value, dict):
        value = value.get("items")
    if not isinstance(value, list):
        return []
    clean = []
    for raw in value[:_MAX_SPECIAL_LOCATIONS]:
        if not isinstance(raw, dict):
            continue
        try:
            clean.append({
                "id": str(raw.get("id") or ""),
                "name": str(raw.get("name") or "موقعیت ذخیره‌شده")[:80],
                "address": str(raw.get("address") or "")[:280],
                "lat": float(raw["lat"]),
                "lng": float(raw["lng"]),
                "category": str(raw.get("category") or "special")[:32],
            })
        except (KeyError, TypeError, ValueError):
            continue
    return clean


def _write_locations(cur, items: list[dict]) -> None:
    cur.execute(
        """insert into app_settings(key,value,updated_at) values(%s,%s,now())
           on conflict(key) do update set value=excluded.value,updated_at=now()""",
        (_settings_key(), Jsonb({"items": items[:_MAX_SPECIAL_LOCATIONS]})),
    )


def _location_payload(raw: dict, *, existing: dict | None = None) -> dict:
    existing = existing or {}
    name = valid_text(raw.get("name", existing.get("name")), "نام موقعیت", required=True, max_length=80)
    address = valid_text(raw.get("address", existing.get("address", "")), "آدرس", required=False, max_length=280) or ""
    lat = _coord(raw.get("lat", existing.get("lat")), "عرض جغرافیایی", -90, 90)
    lng = _coord(raw.get("lng", existing.get("lng")), "طول جغرافیایی", -180, 180)
    return {
        "id": str(existing.get("id") or uuid4()),
        "name": name,
        "address": address,
        "lat": lat,
        "lng": lng,
        "category": "special",
    }


@app_v3.app.get("/api/map/special-locations")
@app_v3.roles_required("technician")
def map_special_locations_list():
    with app_v3.get_db() as db, db.cursor() as cur:
        items = _read_locations(cur)
    return jsonify({"items": items, "count": len(items)})


@app_v3.app.post("/api/map/special-locations")
@app_v3.roles_required("technician")
def map_special_locations_create():
    raw = request.get_json(silent=True) or {}
    item = _location_payload(raw)
    with app_v3.get_db() as db, db.cursor() as cur:
        items = _read_locations(cur, lock=True)
        if len(items) >= _MAX_SPECIAL_LOCATIONS:
            return jsonify({"error": "حداکثر ۱۰۰ موقعیت خاص قابل ذخیره است"}), 409
        items.insert(0, item)
        _write_locations(cur, items)
    return jsonify(item), 201


@app_v3.app.patch("/api/map/special-locations/<location_id>")
@app_v3.roles_required("technician")
def map_special_locations_update(location_id):
    raw = request.get_json(silent=True) or {}
    with app_v3.get_db() as db, db.cursor() as cur:
        items = _read_locations(cur, lock=True)
        index = next((i for i, item in enumerate(items) if item.get("id") == location_id), -1)
        if index < 0:
            return jsonify({"error": "موقعیت پیدا نشد"}), 404
        item = _location_payload(raw, existing=items[index])
        items[index] = item
        _write_locations(cur, items)
    return jsonify(item)


@app_v3.app.delete("/api/map/special-locations/<location_id>")
@app_v3.roles_required("technician")
def map_special_locations_delete(location_id):
    with app_v3.get_db() as db, db.cursor() as cur:
        items = _read_locations(cur, lock=True)
        kept = [item for item in items if item.get("id") != location_id]
        if len(kept) == len(items):
            return jsonify({"error": "موقعیت پیدا نشد"}), 404
        _write_locations(cur, kept)
    return jsonify({"ok": True, "id": location_id})


_PHASE4C_JS = r'''
function aqMapPageSection(){return [...document.querySelectorAll('section')].find(el=>String(el.getAttribute('x-show')||'').includes("page==='map'"))||null}
function aqMapWorkspaceFrame(){const map=$('#mainMap');if(!map)return null;const frame=map.closest('.aq-map-frame')||map.parentElement;if(frame)frame.classList.add('aq-map-frame');return frame}
function aqCloseMapWorkspaceSheets(except=''){
 for(const id of ['aqst-map-tools-sheet','aqst-special-sheet','aqst-special-save']){const el=$('#'+id);if(el&&id!==except)el.hidden=true}
}
function aqSetMapWorkspaceSheet(id,open){const el=$('#'+id);if(!el)return;aqCloseMapWorkspaceSheets(open?id:'');el.hidden=!open;const frame=aqMapWorkspaceFrame();frame?.classList.toggle('aqst-workspace-open',!!open);setTimeout(()=>mainMap()?.invalidateSize?.(),80)}
function aqToggleMapWorkspaceSheet(id){const el=$('#'+id);if(!el)return;aqSetMapWorkspaceSheet(id,el.hidden)}
function aqSpecialCount(){return Array.isArray(ST.nav.specialLocations)?ST.nav.specialLocations.length:0}
function aqRenderSpecialCount(){const el=$('#aqst-special-count');if(el)el.textContent=new Intl.NumberFormat('fa-IR').format(aqSpecialCount())}
function aqSpecialIcon(){return L.divIcon({className:'aqst-special-pin',html:'<span>★</span>',iconSize:[38,42],iconAnchor:[19,38]})}
function aqRenderSpecialMarkers(){
 const m=mainMap();if(!m||!window.L)return;ST.nav.specialMarkers=ST.nav.specialMarkers||[];for(const marker of ST.nav.specialMarkers){try{m.removeLayer(marker)}catch{}}ST.nav.specialMarkers=[];
 for(const item of ST.nav.specialLocations||[]){try{const marker=L.marker([item.lat,item.lng],{icon:aqSpecialIcon(),zIndexOffset:900}).addTo(m);marker.on('click',()=>{selectFreeDestination({lat:item.lat,lng:item.lng,name:item.name,address:item.address||'',source:'special'});aqCloseMapWorkspaceSheets()});ST.nav.specialMarkers.push(marker)}catch{}}
}
async function aqLoadSpecialLocations(){
 try{const data=await api('/api/map/special-locations');ST.nav.specialLocations=data.items||[]}catch{ST.nav.specialLocations=ST.nav.specialLocations||[]}
 aqRenderSpecialCount();aqRenderSpecialLocations();aqRenderSpecialMarkers();
}
function aqRenderSpecialLocations(){
 const out=$('#aqst-special-list');if(!out)return;const items=ST.nav.specialLocations||[];
 if(!items.length){out.innerHTML='<div class="aqst-special-empty">هنوز موقعیتی ذخیره نشده.<small>روی نقشه حدود یک ثانیه نگه دار، بعد «ذخیره موقعیت» را بزن.</small></div>';return}
 out.innerHTML=items.map(item=>`<article class="aqst-special-row" data-id="${esc(item.id)}"><button type="button" class="aqst-special-route"><span class="aqst-special-star">★</span><span><b>${esc(item.name)}</b><small>${esc(item.address||`${Number(item.lat).toFixed(5)}, ${Number(item.lng).toFixed(5)}`)}</small></span></button><div class="aqst-special-row-actions"><button type="button" class="aqst-special-edit" aria-label="ویرایش">✎</button><button type="button" class="aqst-special-delete" aria-label="حذف">×</button></div></article>`).join('');
 $$('.aqst-special-row',out).forEach(row=>{const item=items.find(x=>String(x.id)===String(row.dataset.id));if(!item)return;row.querySelector('.aqst-special-route')?.addEventListener('click',()=>{selectFreeDestination({lat:item.lat,lng:item.lng,name:item.name,address:item.address||'',source:'special'});aqCloseMapWorkspaceSheets()});row.querySelector('.aqst-special-edit')?.addEventListener('click',()=>aqOpenSpecialSave(item,item.id));row.querySelector('.aqst-special-delete')?.addEventListener('click',()=>aqDeleteSpecialLocation(item))});
}
function aqOpenSpecialSave(point,id=''){
 point=point||ST.nav.freeDestination;if(!point)return alert('اول یک نقطه روی نقشه انتخاب کن');const sheet=$('#aqst-special-save');if(!sheet)return;
 sheet.dataset.editId=id||'';sheet.dataset.lat=String(point.lat);sheet.dataset.lng=String(point.lng);$('#aqst-special-name').value=point.name&&point.name!=='مقصد انتخابی روی نقشه'?point.name:'';$('#aqst-special-address').value=point.address||'';$('#aqst-special-save-title').textContent=id?'ویرایش موقعیت خاص':'ذخیره موقعیت خاص';aqSetMapWorkspaceSheet('aqst-special-save',true);setTimeout(()=>$('#aqst-special-name')?.focus(),80)
}
async function aqPersistSpecialLocation(){
 const sheet=$('#aqst-special-save'),name=$('#aqst-special-name')?.value.trim(),address=$('#aqst-special-address')?.value.trim(),id=sheet?.dataset.editId||'';if(!sheet||!name)return alert('برای این موقعیت یک نام بنویس');
 const payload={name,address,lat:Number(sheet.dataset.lat),lng:Number(sheet.dataset.lng)},button=$('#aqst-special-save-go');if(button.disabled)return;button.disabled=true;
 try{const saved=await api(id?`/api/map/special-locations/${encodeURIComponent(id)}`:'/api/map/special-locations',{method:id?'PATCH':'POST',body:JSON.stringify(payload)});if(id){const i=(ST.nav.specialLocations||[]).findIndex(x=>String(x.id)===String(id));if(i>=0)ST.nav.specialLocations[i]=saved}else ST.nav.specialLocations=[saved,...(ST.nav.specialLocations||[])];aqRenderSpecialCount();aqRenderSpecialLocations();aqRenderSpecialMarkers();aqSetMapWorkspaceSheet('aqst-special-sheet',true);alert(id?'موقعیت ویرایش شد':'موقعیت خاص ذخیره شد')}catch(e){alert(e.message||'ذخیره موقعیت انجام نشد')}finally{button.disabled=false}
}
async function aqDeleteSpecialLocation(item){
 if(!item?.id)return;try{await api(`/api/map/special-locations/${encodeURIComponent(item.id)}`,{method:'DELETE'});ST.nav.specialLocations=(ST.nav.specialLocations||[]).filter(x=>String(x.id)!==String(item.id));aqRenderSpecialCount();aqRenderSpecialLocations();aqRenderSpecialMarkers()}catch(e){alert(e.message||'حذف موقعیت انجام نشد')}
}
function aqDecorateFreeDestinationCard(){
 const card=$('#aqst-free-card');if(!card||card.hidden||card.querySelector('.aqst-free-save'))return;const actions=card.querySelector('.aqst-free-card-actions');if(!actions)return;const b=document.createElement('button');b.type='button';b.className='aqst-free-save';b.textContent='ذخیره موقعیت';b.addEventListener('click',()=>aqOpenSpecialSave(ST.nav.freeDestination));actions.insertBefore(b,actions.lastElementChild)
}
function aqAdoptMapWorkspaceContent(){
 const section=aqMapPageSection(),tools=$('#aqst-map-tools-content');if(!section||!tools)return;const header=section.firstElementChild,actions=header?.querySelector('.no-print');if(actions&&actions.parentElement!==tools){actions.classList.add('aqst-adopted-actions');tools.appendChild(actions)}const smart=$('#aq-smart-tour');if(smart&&smart.parentElement!==tools)tools.appendChild(smart);aqDecorateFreeDestinationCard()
}
function aqSetupMapWorkspace(){
 const frame=aqMapWorkspaceFrame();if(!frame)return;if(!$('#aqst-map-workspace')){const root=document.createElement('div');root.id='aqst-map-workspace';root.innerHTML=`<div class="aqst-map-float-stack"><div class="aqst-glow-shell"><button type="button" id="aqst-map-tools-toggle" class="aqst-map-float-btn"><span>☷</span><b>ابزار نقشه</b></button></div><div class="aqst-glow-shell"><button type="button" id="aqst-special-toggle" class="aqst-map-float-btn"><span>★</span><b>موقعیت‌های خاص</b><i id="aqst-special-count">۰</i></button></div></div><section id="aqst-map-tools-sheet" class="aqst-map-sheet" hidden><div class="aqst-map-sheet-head"><b>ابزار نقشه</b><button type="button" class="aqst-sheet-close">×</button></div><div id="aqst-map-tools-content"></div></section><section id="aqst-special-sheet" class="aqst-map-sheet" hidden><div class="aqst-map-sheet-head"><b>موقعیت‌های خاص</b><button type="button" class="aqst-sheet-close">×</button></div><button type="button" id="aqst-save-current-special" class="aqst-special-save-current">＋ ذخیره نقطه انتخاب‌شده</button><div id="aqst-special-list"></div></section><section id="aqst-special-save" class="aqst-map-sheet aqst-special-editor" hidden><div class="aqst-map-sheet-head"><b id="aqst-special-save-title">ذخیره موقعیت خاص</b><button type="button" class="aqst-sheet-close">×</button></div><input id="aqst-special-name" maxlength="80" autocomplete="off" placeholder="مثلاً بانک ملت فردیس"><input id="aqst-special-address" maxlength="280" autocomplete="off" placeholder="آدرس یا توضیح کوتاه (اختیاری)"><button type="button" id="aqst-special-save-go">ذخیره</button></section>`;frame.appendChild(root);$('#aqst-map-tools-toggle').addEventListener('click',()=>aqToggleMapWorkspaceSheet('aqst-map-tools-sheet'));$('#aqst-special-toggle').addEventListener('click',()=>{aqRenderSpecialLocations();aqToggleMapWorkspaceSheet('aqst-special-sheet')});$('#aqst-save-current-special').addEventListener('click',()=>aqOpenSpecialSave(ST.nav.freeDestination));$('#aqst-special-save-go').addEventListener('click',aqPersistSpecialLocation);$$('.aqst-sheet-close',root).forEach(b=>b.addEventListener('click',()=>aqCloseMapWorkspaceSheets()));aqLoadSpecialLocations();
 const cardObserver=new MutationObserver(aqDecorateFreeDestinationCard);const attachCardObserver=()=>{const card=$('#aqst-free-card');if(card&&!card.dataset.aqSpecialWatch){card.dataset.aqSpecialWatch='1';cardObserver.observe(card,{childList:true,subtree:true,attributes:true,attributeFilter:['hidden']})}};setTimeout(attachCardObserver,300);setTimeout(attachCardObserver,1200)}
 aqAdoptMapWorkspaceContent();aqRenderSpecialCount();setTimeout(()=>mainMap()?.invalidateSize?.(),80)
}
if(!window.__aquaMapWorkspacePhase4c){window.__aquaMapWorkspacePhase4c=true;setTimeout(aqSetupMapWorkspace,150);setTimeout(aqSetupMapWorkspace,700);setTimeout(aqSetupMapWorkspace,1600);const aqMapWorkspaceObserver=new MutationObserver(()=>{if($('#mainMap'))aqSetupMapWorkspace()});aqMapWorkspaceObserver.observe(document.documentElement,{subtree:true,childList:true})}
'''.strip()


_PHASE4C_CSS = r'''
/* Aqua Map Phase 4C — decluttered normal Map workspace + special locations. */
section[x-show*="page==='map'"] .aq-map-frame{position:relative!important;overflow:hidden!important;border-radius:24px!important;isolation:isolate}
section[x-show*="page==='map'"] .aq-map-frame #mainMap{height:min(72dvh,760px)!important;min-height:520px!important}
#aqst-map-workspace{position:absolute;inset:0;z-index:820;pointer-events:none;direction:rtl}
#aqst-map-workspace button,#aqst-map-workspace input{font:inherit}
.aqst-map-float-stack{position:absolute;top:12px;right:12px;display:grid;gap:9px;pointer-events:auto;z-index:8}
.aqst-glow-shell{position:relative;overflow:hidden;border-radius:18px;padding:1px;box-shadow:0 10px 30px rgba(0,0,0,.24),0 0 20px rgba(36,190,244,.12);isolation:isolate}
.aqst-glow-shell::before{content:"";position:absolute;inset:-120%;background:conic-gradient(from 0deg,transparent 0 24%,rgba(50,221,255,.95) 31%,rgba(55,117,255,.95) 39%,transparent 48% 74%,rgba(39,241,205,.88) 82%,transparent 91%);animation:aqstMapGlowSpin 4.8s linear infinite;z-index:-2}
.aqst-glow-shell::after{content:"";position:absolute;inset:1px;border-radius:17px;background:linear-gradient(145deg,rgba(4,24,38,.94),rgba(8,48,70,.9));z-index:-1}
@keyframes aqstMapGlowSpin{to{transform:rotate(360deg)}}
.aqst-map-float-btn{min-height:44px;border:0;border-radius:17px;background:transparent;color:#e9faff;padding:9px 12px;display:flex;align-items:center;gap:8px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.06);-webkit-tap-highlight-color:transparent}
.aqst-map-float-btn>span{font-size:1.12rem;color:#64dcff}.aqst-map-float-btn>b{font-size:.74rem;white-space:nowrap}.aqst-map-float-btn>i{min-width:22px;height:22px;border-radius:999px;background:rgba(38,203,255,.16);display:grid;place-items:center;font-size:.64rem;font-style:normal;color:#9cecff}
.aqst-map-sheet{position:absolute;right:12px;left:12px;top:72px;max-height:calc(100% - 94px);overflow:auto;padding:12px;border-radius:22px;background:linear-gradient(155deg,rgba(4,20,32,.95),rgba(7,41,59,.93));border:1px solid rgba(105,221,255,.22);box-shadow:0 22px 60px rgba(0,0,0,.42),0 0 28px rgba(35,194,248,.15);backdrop-filter:blur(24px) saturate(1.2);-webkit-backdrop-filter:blur(24px) saturate(1.2);pointer-events:auto;z-index:9;animation:aqstMapSheetIn .26s cubic-bezier(.22,.8,.22,1)}
.aqst-map-sheet[hidden]{display:none!important}@keyframes aqstMapSheetIn{from{opacity:0;transform:translateY(-8px) scale(.985)}to{opacity:1;transform:none}}
.aqst-map-sheet-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.aqst-map-sheet-head>b{font-size:.9rem;color:#eefaff}.aqst-sheet-close{width:34px;height:34px;border:1px solid rgba(255,255,255,.08);border-radius:12px;background:rgba(255,255,255,.06);color:#dff6ff;font-size:1.2rem}
#aqst-map-tools-content{display:grid;gap:9px}#aqst-map-tools-content>.aqst-adopted-actions{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:6px!important;width:100%!important;margin:0!important}#aqst-map-tools-content>.aqst-adopted-actions>.aqst-route-pair{display:contents!important}#aqst-map-tools-content>.aqst-adopted-actions button{min-width:0!important;width:100%!important;height:42px!important;padding:0 7px!important;font-size:.7rem!important;border-radius:13px!important}
#aqst-map-tools-content #aq-smart-tour{margin:0!important}#aqst-map-tools-content #aq-smart-tour .aqst-selected{max-height:76px!important;margin-top:6px!important}#aqst-map-tools-content #aqst-free-search{margin-top:7px!important}
.aqst-special-save-current{width:100%;min-height:42px;border:1px dashed rgba(89,216,255,.32);border-radius:14px;background:rgba(34,181,229,.1);color:#9ae9ff;font-weight:900;margin-bottom:9px}.aqst-special-empty{padding:22px 10px;text-align:center;color:#a8bfca;font-size:.78rem}.aqst-special-empty small{display:block;margin-top:6px;line-height:1.8;color:#7e9aa8}
#aqst-special-list{display:grid;gap:7px}.aqst-special-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px;align-items:center;border:1px solid rgba(255,255,255,.07);border-radius:15px;background:rgba(255,255,255,.035);padding:5px}.aqst-special-route{border:0;background:transparent;color:#effaff;display:grid;grid-template-columns:auto minmax(0,1fr);gap:8px;align-items:center;text-align:right;padding:7px}.aqst-special-route span:last-child{min-width:0}.aqst-special-route b,.aqst-special-route small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.aqst-special-route b{font-size:.8rem}.aqst-special-route small{font-size:.66rem;color:#8faab6;margin-top:2px}.aqst-special-star{width:32px;height:32px;border-radius:12px;display:grid!important;place-items:center;background:rgba(36,194,248,.12);color:#69dcff!important}.aqst-special-row-actions{display:flex;gap:4px}.aqst-special-row-actions button{width:32px;height:32px;border:0;border-radius:10px;background:rgba(255,255,255,.06);color:#c9e9f5}.aqst-special-delete{color:#ff9ead!important}
.aqst-special-editor{top:auto!important;bottom:12px!important}.aqst-special-editor input{width:100%;min-height:44px;border:1px solid rgba(255,255,255,.11);border-radius:14px;background:rgba(2,15,24,.72);color:#effaff;padding:10px 12px;outline:none;margin-top:7px}.aqst-special-editor input:focus{border-color:#43c8f5;box-shadow:0 0 0 3px rgba(67,200,245,.12)}#aqst-special-save-go{width:100%;min-height:44px;border:0;border-radius:14px;background:linear-gradient(135deg,#168fc4,#27d2e8);color:#00151e;font-weight:950;margin-top:9px}
.aqst-free-card-actions .aqst-free-save{background:rgba(35,190,239,.14)!important;color:#a7ecff!important;border:1px solid rgba(56,204,247,.18)!important}
.aqst-special-pin{background:transparent!important;border:0!important}.aqst-special-pin span{width:34px;height:34px;border-radius:13px;display:grid;place-items:center;background:rgba(4,28,43,.92);border:1px solid rgba(85,216,255,.7);color:#6de1ff;font-size:1rem;box-shadow:0 6px 18px rgba(0,0,0,.36),0 0 16px rgba(45,199,246,.3)}
@media(max-width:700px){section[x-show*="page==='map'"] .aq-map-frame #mainMap{height:68dvh!important;min-height:500px!important}.aqst-map-float-stack{top:8px;right:8px}.aqst-map-sheet{top:64px;right:8px;left:8px;max-height:calc(100% - 78px);border-radius:19px}.aqst-map-float-btn{min-height:42px;padding:8px 10px}.aqst-map-float-btn>b{font-size:.69rem}#aqst-map-tools-content>.aqst-adopted-actions{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:4px!important}#aqst-map-tools-content>.aqst-adopted-actions button{font-size:.64rem!important;padding:0 4px!important}.aqst-special-editor{bottom:8px!important;top:auto!important}}
@media(prefers-reduced-motion:reduce){.aqst-glow-shell::before{animation:none}.aqst-map-sheet{animation:none}}
'''.strip()


@app_v3.app.after_request
def aqua_map_workspace_assets(response):
    try:
        if response.status_code != 200:
            return response
        if request.path == "/aqua-smart-tour.js":
            response.direct_passthrough = False
            source = response.get_data(as_text=True)
            marker = "function aqMapPageSection()"
            if marker not in source:
                anchor = "\nfunction enhance(){"
                if anchor not in source:
                    raise RuntimeError("Phase 4C helper anchor was not found")
                source = source.replace(anchor, "\n" + _PHASE4C_JS + anchor, 1)
                response.set_data(source)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            marker = "/* Aqua Map Phase 4C — decluttered normal Map workspace + special locations. */"
            if marker not in css:
                css += "\n" + _PHASE4C_CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_map_workspace_asset_failed: %s", str(exc)[:180])
    return response
