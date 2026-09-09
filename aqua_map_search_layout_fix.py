"""Map-only resilient place search for PR #29.

The final Map/Navigation guard owns all compact mobile layout behavior. This
module intentionally owns only the place-search endpoint so two independent
MutationObservers cannot move the same map controls back and forth.
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


# This module must be imported after aqua_smart_tour so the endpoint exists.
if "smart_tour_place_search" in app_v3.app.view_functions:
    app_v3.app.view_functions["smart_tour_place_search"] = _resilient_place_search
