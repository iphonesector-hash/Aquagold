"""Branch-only Map place search with safe provider fallback."""
import urllib.parse

from flask import jsonify, request

import app_routing
import app_v3
import aqua_neshan_preview as neshan
import aqua_navigation_polish as polish
from aquagold_validation import text as valid_text


def _provider_fallback_items(query: str):
    """Reuse AquaGold's existing Iran geocoder when the Neshan key lacks Search."""
    params = urllib.parse.urlencode({
        "q": query,
        "format": "jsonv2",
        "limit": 8,
        "countrycodes": "ir",
        "addressdetails": 1,
    })
    raw = app_routing._fetch_json(f"{app_routing.GEOCODING_URL}?{params}", timeout=10)
    items = []
    for item in (raw or [])[:8]:
        lat = item.get("lat")
        lng = item.get("lon")
        if lat is None or lng is None:
            continue
        display = str(item.get("display_name") or query).strip()
        address = item.get("address") or {}
        region = str(
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("county")
            or address.get("state")
            or ""
        ).strip()
        title = str(item.get("name") or display.split(",", 1)[0] or query).strip()
        items.append({
            "title": title,
            "address": display,
            "region": region,
            "type": item.get("type") or "geocode",
            "latitude": float(lat),
            "longitude": float(lng),
        })
    return items


def _place_search_payload(query: str, lat: float, lng: float):
    search_error = ""
    geocode_error = ""
    try:
        payload = neshan._neshan_get("/v3/search", {"term": query, "lat": lat, "lng": lng}, timeout=10)
        items = polish._search_items(payload, query)
        if items:
            return {"provider": "neshan-search-v3", "items": items[:10]}, 200
    except Exception as exc:
        search_error = str(exc)[:160]

    try:
        payload = neshan.geocode_address(query, plus=True, timeout=10)
        items = polish._geocode_items(payload, query)
        if items:
            return {"provider": "neshan-geocoding-plus", "fallback": True, "items": items[:10]}, 200
    except Exception as exc:
        geocode_error = str(exc)[:140]

    try:
        items = _provider_fallback_items(query)
        return {"provider": "aquagold-geocoder", "fallback": True, "items": items[:8]}, 200
    except Exception as exc:
        app_v3.logger.warning(
            "aqua_map_search_v3_failed search=%s geocode=%s fallback=%s",
            search_error,
            geocode_error,
            str(exc)[:140],
        )
        return {
            "error": "جستجوی آدرس موقتاً در دسترس نیست؛ می‌توانی مقصد را مستقیم روی نقشه انتخاب کنی."
        }, 502


@app_v3.token_required
@app_v3.limiter.limit("60 per hour")
def _v3_place_search():
    query = valid_text(request.args.get("q"), "جست‌وجوی مکان", required=True, max_length=180)
    lat = polish._coord(request.args.get("lat"), 35.6892)
    lng = polish._coord(request.args.get("lng"), 51.3890)
    payload, status = _place_search_payload(query, lat, lng)
    return jsonify(payload), status


if "smart_tour_place_search" in app_v3.app.view_functions:
    app_v3.app.view_functions["smart_tour_place_search"] = _v3_place_search
