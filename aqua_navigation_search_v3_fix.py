"""Final branch-only Neshan place-search endpoint using the current v3 API."""
from flask import jsonify, request

import app_v3
import aqua_neshan_preview as neshan
import aqua_navigation_polish as polish
from aquagold_validation import text as valid_text


@app_v3.token_required
@app_v3.limiter.limit("60 per hour")
def _v3_place_search():
    query = valid_text(request.args.get("q"), "جست‌وجوی مکان", required=True, max_length=180)
    lat = polish._coord(request.args.get("lat"), 35.6892)
    lng = polish._coord(request.args.get("lng"), 51.3890)
    search_error = ""
    try:
        payload = neshan._neshan_get("/v3/search", {"term": query, "lat": lat, "lng": lng}, timeout=10)
        items = polish._search_items(payload, query)
        if items:
            return jsonify({"provider": "neshan-search-v3", "items": items[:10]})
    except Exception as exc:
        search_error = str(exc)[:160]
    try:
        payload = neshan.geocode_address(query, plus=True, timeout=10)
        return jsonify({"provider": "neshan-geocoding-plus", "fallback": True, "items": polish._geocode_items(payload, query)[:10]})
    except Exception as exc:
        app_v3.logger.warning("aqua_map_search_v3_failed search=%s geocode=%s", search_error, str(exc)[:140])
        return jsonify({"error": "این عبارت در سرویس‌های فعال نشان پیدا نشد؛ روی نقشه نگه دار تا همان نقطه مقصد شود."}), 502


if "smart_tour_place_search" in app_v3.app.view_functions:
    app_v3.app.view_functions["smart_tour_place_search"] = _v3_place_search
