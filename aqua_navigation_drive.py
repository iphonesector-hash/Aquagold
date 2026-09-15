"""Map/Navigation-only drive mode support for the Aqua preview branch.

Adds Neshan Web SDK CSP allowances, a correct place-search adapter and reverse
geocoding for long-press destinations. No schema changes and no production-only
state.
"""
from __future__ import annotations

from flask import jsonify, request

import app_v3
import aqua_neshan_preview as neshan
from aquagold_validation import text as valid_text


def _coord(value, fallback=None):
    try:
        return float(value)
    except Exception:
        return fallback


@app_v3.token_required
def _drive_place_search():
    q = valid_text(request.args.get("q"), "جست‌وجوی مکان", required=True, max_length=180)
    lat = _coord(request.args.get("lat"), 35.6892)
    lng = _coord(request.args.get("lng"), 51.3890)
    try:
        payload = neshan.place_search(q, lat, lng, timeout=10)
    except Exception as exc:
        return jsonify({"error": str(exc)[:180]}), 502
    items = []
    for item in payload.get("items") or []:
        loc = item.get("location") or {}
        ilat = loc.get("latitude", loc.get("y"))
        ilng = loc.get("longitude", loc.get("x"))
        if ilat is None or ilng is None:
            continue
        items.append({
            "title": item.get("title") or item.get("name") or q,
            "address": item.get("address") or item.get("neighbourhood") or "",
            "type": item.get("type") or "",
            "region": item.get("region") or item.get("city") or "",
            "latitude": float(ilat),
            "longitude": float(ilng),
        })
    return jsonify({"provider": "neshan", "items": items[:10]})


# Replace the older branch-only place-search implementation with the canonical
# Neshan term/lat/lng request shape.
if "smart_tour_place_search" in app_v3.app.view_functions:
    app_v3.app.view_functions["smart_tour_place_search"] = _drive_place_search


@app_v3.app.get("/api/map/neshan/reverse")
@app_v3.token_required
@app_v3.limiter.limit("90 per hour")
def aqua_neshan_reverse():
    lat = _coord(request.args.get("lat"))
    lng = _coord(request.args.get("lng"))
    if lat is None or lng is None or not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return jsonify({"error": "مختصات معتبر نیست"}), 400
    try:
        payload = neshan._neshan_get("/v2/reverse", {"lat": lat, "lng": lng}, timeout=10)
    except Exception as exc:
        return jsonify({"error": str(exc)[:180]}), 502
    address = payload.get("formatted_address") or payload.get("address") or ""
    return jsonify({
        "provider": "neshan",
        "address": address,
        "route_name": payload.get("route_name") or payload.get("routeName") or "",
        "neighbourhood": payload.get("neighbourhood") or "",
        "city": payload.get("city") or "",
        "state": payload.get("state") or "",
        "municipality_zone": payload.get("municipality_zone") or "",
        "in_traffic_zone": payload.get("in_traffic_zone"),
        "in_odd_even_zone": payload.get("in_odd_even_zone"),
    })


@app_v3.app.after_request
def aqua_navigation_drive_csp(response):
    """Permit only Neshan's official browser SDK/tile hosts for this branch."""
    try:
        csp = response.headers.get("Content-Security-Policy") or (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
            "img-src 'self' data: blob: https:; font-src 'self'; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "connect-src 'self' https://tile.openstreetmap.org; worker-src 'self' blob:; manifest-src 'self'"
        )
        csp = csp.replace(
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://static.neshan.org",
        )
        csp = csp.replace(
            "style-src 'self' 'unsafe-inline'",
            "style-src 'self' 'unsafe-inline' https://static.neshan.org",
        )
        csp = csp.replace(
            "font-src 'self'",
            "font-src 'self' data: https://static.neshan.org",
        )
        csp = csp.replace(
            "connect-src 'self' https://tile.openstreetmap.org",
            "connect-src 'self' https://tile.openstreetmap.org https://static.neshan.org https://*.neshan.org",
        )
        response.headers["Content-Security-Policy"] = csp
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_drive_csp_failed: %s", str(exc)[:160])
    return response
