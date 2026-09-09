"""Map-only search fallback and compact mobile layout repair.

Keeps the current Finance/Map integration isolated while restoring the map UI
that was previously validated on iPhone: resilient Persian place search,
three primary map controls on one row, and compact customer/address search.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

from flask import jsonify, request

import app_v3
import aqua_navigation_polish as polish
import aqua_neshan_preview as neshan
from aquagold_validation import text as valid_text

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_LOCK = threading.Lock()
_NOMINATIM_LAST_AT = 0.0


def _coord(value, fallback):
    try:
        value = float(value)
        return value if value == value else fallback
    except Exception:
        return fallback


def _nominatim_items(payload, query):
    items = []
    for raw in payload if isinstance(payload, list) else []:
        try:
            lat = float(raw.get("lat"))
            lng = float(raw.get("lon"))
        except (TypeError, ValueError):
            continue
        named = raw.get("namedetails") if isinstance(raw.get("namedetails"), dict) else {}
        address = raw.get("address") if isinstance(raw.get("address"), dict) else {}
        display = str(raw.get("display_name") or "").strip()
        title = (
            str(named.get("name:fa") or named.get("name") or raw.get("name") or "").strip()
            or (display.split(",", 1)[0].strip() if display else query)
        )
        region = str(
            address.get("city")
            or address.get("town")
            or address.get("municipality")
            or address.get("county")
            or address.get("state")
            or ""
        ).strip()
        items.append(
            {
                "title": title or query,
                "address": display or region or query,
                "type": str(raw.get("type") or raw.get("category") or "search"),
                "region": region,
                "latitude": lat,
                "longitude": lng,
            }
        )
    return items


def _nominatim_search(query, lat, lng, timeout=9):
    global _NOMINATIM_LAST_AT
    params = {
        "format": "jsonv2",
        "q": query,
        "limit": "10",
        "countrycodes": "ir",
        "addressdetails": "1",
        "namedetails": "1",
        "accept-language": "fa",
        "viewbox": f"{lng - 0.45:.6f},{lat + 0.35:.6f},{lng + 0.45:.6f},{lat - 0.35:.6f}",
        "bounded": "0",
    }
    url = _NOMINATIM_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Language": "fa",
            "User-Agent": "AquaGold-CRM/1.0 (map-search-fallback)",
        },
    )
    with _NOMINATIM_LOCK:
        wait = 1.05 - (time.monotonic() - _NOMINATIM_LAST_AT)
        if wait > 0:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8") or "[]")
        finally:
            _NOMINATIM_LAST_AT = time.monotonic()
    return _nominatim_items(payload, query)


def _neshan_geocode_items(query, lat, lng):
    errors = []
    attempts = (
        (
            "/geocoding/v1/plus",
            {"address": query, "bias_lat": lat, "bias_lng": lng},
            "neshan-geocoding-plus",
        ),
        ("/geocoding/v1", {"address": query}, "neshan-geocoding"),
    )
    for path, params, provider in attempts:
        try:
            payload = neshan._neshan_get(path, params, timeout=9)
            items = polish._geocode_items(payload, query)
            if items:
                return provider, items, errors
        except Exception as exc:
            errors.append(f"{path}:{str(exc)[:100]}")
    return "", [], errors


@app_v3.token_required
@app_v3.limiter.limit("60 per hour")
def _resilient_place_search():
    query = valid_text(request.args.get("q"), "جست‌وجوی مکان", required=True, max_length=180)
    lat = _coord(request.args.get("lat"), 35.6892)
    lng = _coord(request.args.get("lng"), 51.3890)
    errors = []

    try:
        payload = neshan._neshan_get(
            "/v3/search", {"term": query, "lat": lat, "lng": lng}, timeout=8
        )
        items = polish._search_items(payload, query)
        if items:
            return jsonify({"provider": "neshan-search", "items": items[:10]})
    except Exception as exc:
        errors.append(f"search:{str(exc)[:110]}")

    provider, items, geocode_errors = _neshan_geocode_items(query, lat, lng)
    errors.extend(geocode_errors)
    if items:
        return jsonify({"provider": provider, "fallback": True, "items": items[:10]})

    try:
        items = _nominatim_search(query, lat, lng)
        if items:
            return jsonify(
                {"provider": "osm-nominatim", "fallback": True, "items": items[:10]}
            )
    except Exception as exc:
        errors.append(f"osm:{str(exc)[:110]}")

    app_v3.logger.warning("aqua_map_resilient_search_failed %s", " | ".join(errors)[:500])
    return jsonify({"error": "برای این عبارت نتیجه‌ای پیدا نشد. نام خیابان یا مکان را کمی کامل‌تر بنویس."}), 404


if "smart_tour_place_search" in app_v3.app.view_functions:
    app_v3.app.view_functions["smart_tour_place_search"] = _resilient_place_search


_LAYOUT_JS = r'''
;(()=>{
 if(window.__aquaMapLayoutFix20260909)return;window.__aquaMapLayoutFix20260909=true;
 const has=(b,t)=>String(b?.textContent||'').replace(/\s+/g,' ').includes(t);
 function tidy(){
  const map=document.getElementById('mainMap');if(!map)return;
  const root=map.closest('section')||map.parentElement?.parentElement||document;
  const buttons=[...root.querySelectorAll('button')];
  const locate=buttons.find(b=>has(b,'موقعیت من'));
  const near=buttons.find(b=>has(b,'اطراف من'));
  const opt=buttons.find(b=>has(b,'بهینه‌سازی مسیر'));
  if(!locate||!near||!opt)return;
  let group=root.querySelector('.aq-map-primary-actions');
  if(!group){
   const holder=locate.parentElement;if(!holder)return;
   group=document.createElement('div');
   group.className='aq-map-primary-actions aqst-route-pair';
   holder.insertBefore(group,locate);
  }
  [locate,near,opt].forEach(b=>{if(b.parentElement!==group)group.appendChild(b)});
 }
 let timer=0;const schedule=()=>{clearTimeout(timer);timer=setTimeout(tidy,30)};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',tidy,{once:true});else tidy();
 new MutationObserver(schedule).observe(document.documentElement,{subtree:true,childList:true});
 setTimeout(tidy,250);setTimeout(tidy,900);setTimeout(tidy,1800);
})();
'''.strip()

_LAYOUT_CSS = r'''
/* Aqua map compact regression guard — 20260909 */
.aq-map-primary-actions.aqst-route-pair{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:5px!important;width:100%!important;align-items:stretch!important}
.aq-map-primary-actions.aqst-route-pair>.btn,.aq-map-primary-actions.aqst-route-pair>button{width:100%!important;min-width:0!important;margin:0!important;justify-content:center!important;align-items:center!important;padding:.62rem .18rem!important;gap:4px!important;white-space:nowrap!important;line-height:1.2!important;font-size:.70rem!important;border-radius:13px!important}
.aq-map-primary-actions.aqst-route-pair svg{width:16px!important;height:16px!important;flex:0 0 16px!important}
#aq-smart-tour .aqst-search{margin-bottom:7px!important}
#aq-smart-tour .aqst-searchbar{gap:6px!important;align-items:center!important}
#aq-smart-tour .aqst-searchbar input{height:44px!important;min-height:44px!important;padding:0 11px!important;margin:0!important;font-size:16px!important}
#aq-smart-tour .aqst-iconbtn{width:44px!important;height:44px!important;min-height:44px!important;margin:0!important}
#aq-smart-tour .aqst-selected{display:grid!important;grid-template-columns:minmax(0,1fr) auto!important;align-items:center!important;gap:7px!important;height:auto!important;min-height:0!important;margin:7px 0 0!important;padding:8px 9px!important}
#aq-smart-tour .aqst-selected-copy{min-width:0!important;flex:none!important}
#aq-smart-tour .aqst-selected-copy b{margin:0!important;line-height:1.35!important}
#aq-smart-tour .aqst-selected-copy small{margin-top:1px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;max-width:48vw!important;line-height:1.35!important}
#aq-smart-tour .aqst-selected>div:last-child{display:flex!important;align-items:center!important;gap:5px!important;width:auto!important;margin:0!important}
#aq-smart-tour .aqst-selected .aqst-btn{padding:6px 8px!important;border-radius:11px!important;font-size:.68rem!important;line-height:1.15!important;min-height:34px!important}
#aqst-free-search{margin-top:7px!important}
#aqst-free-search .aqst-free-searchbar{gap:6px!important;align-items:center!important}
#aqst-free-search .aqst-free-searchbar input,#aqst-free-search .aqst-free-searchbar button{height:43px!important;min-height:43px!important;margin:0!important}
#aqst-free-search .aqst-free-searchbar button{padding:0 10px!important;font-size:.74rem!important}
#aqst-free-search .aqst-free-hint{padding-top:4px!important;font-size:.68rem!important}
@media(max-width:390px){.aq-map-primary-actions.aqst-route-pair{gap:4px!important}.aq-map-primary-actions.aqst-route-pair>.btn,.aq-map-primary-actions.aqst-route-pair>button{font-size:.64rem!important;padding:.58rem .08rem!important}.aq-map-primary-actions.aqst-route-pair svg{width:15px!important;height:15px!important}}
'''.strip()


@app_v3.app.after_request
def aqua_map_search_layout_assets(response):
    try:
        if response.status_code != 200:
            return response
        if request.path == "/aqua-smart-tour.js":
            response.direct_passthrough = False
            source = response.get_data(as_text=True)
            if "__aquaMapLayoutFix20260909" not in source:
                source += "\n" + _LAYOUT_JS + "\n"
                response.set_data(source)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            if "Aqua map compact regression guard — 20260909" not in css:
                css += "\n" + _LAYOUT_CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_map_search_layout_asset_failed: %s", str(exc)[:180])
    return response
