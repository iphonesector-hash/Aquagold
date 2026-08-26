"""Server-side geocoding and road-route optimization for field visits."""

from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.parse
import urllib.request

from flask import jsonify, request
from psycopg.types.json import Jsonb

from app_v3 import app, get_db, limiter, roles_required, row_json, token_required
from aquagold_validation import ValidationError, coordinates, text, uuid


GEOCODING_URL = os.getenv("GEOCODING_PROVIDER_URL", "https://nominatim.openstreetmap.org/search").rstrip("/")
ROUTING_URL = os.getenv("ROUTING_PROVIDER_URL", "https://router.project-osrm.org").rstrip("/")
PROVIDER_USER_AGENT = os.getenv("AQUAGOLD_MAP_USER_AGENT", "AquaGold-CRM/1.0")


def _fetch_json(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": PROVIDER_USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Map provider returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _haversine(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_000 * 2 * math.asin(math.sqrt(h))


def _nearest_neighbor(matrix):
    remaining = set(range(1, len(matrix)))
    order, current = [], 0
    while remaining:
        nxt = min(remaining, key=lambda idx: matrix[current][idx] if matrix[current][idx] is not None else float("inf"))
        if matrix[current][nxt] is None:
            break
        order.append(nxt)
        remaining.remove(nxt)
        current = nxt
    order.extend(sorted(remaining))
    return order


@app.get("/api/geocode")
@token_required
@limiter.limit("1 per second; 60 per hour")
def geocode():
    query = text(request.args.get("q"), "آدرس", required=True, max_length=500)
    normalized = " ".join(query.lower().split())
    cache_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    with get_db() as db, db.cursor() as cur:
        cur.execute("select response from geocode_cache where query_hash=%s and expires_at>now()", (cache_key,))
        cached = cur.fetchone()
    if cached:
        return jsonify({"items": cached["response"], "provider": "cache"})

    params = urllib.parse.urlencode({"q": query, "format": "jsonv2", "limit": 5, "countrycodes": "ir", "addressdetails": 1})
    try:
        raw = _fetch_json(f"{GEOCODING_URL}?{params}")
    except Exception:
        app.logger.exception("geocoding_provider_failed")
        return jsonify({"error": "سرویس تبدیل آدرس موقتاً در دسترس نیست"}), 503
    items = [
        {
            "display_name": text(item.get("display_name"), "نشانی نتیجه", max_length=1000),
            "latitude": float(item["lat"]), "longitude": float(item["lon"]),
            "type": item.get("type"), "importance": item.get("importance"),
        }
        for item in raw[:5] if item.get("lat") and item.get("lon")
    ]
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            """insert into geocode_cache(query_hash,normalized_query,response,expires_at)
               values(%s,%s,%s,now()+interval '30 days')
               on conflict(query_hash) do update set response=excluded.response,created_at=now(),expires_at=excluded.expires_at""",
            (cache_key, normalized, Jsonb(items)),
        )
    return jsonify({"items": items, "provider": "nominatim"})


@app.post("/api/route/optimize")
@roles_required("technician")
@limiter.limit("30 per hour")
def optimize_route():
    data = request.get_json() or {}
    start_lat, start_lng = coordinates(data.get("latitude"), data.get("longitude"), required=True)
    raw_ids = data.get("customer_ids") or []
    if not isinstance(raw_ids, list) or not 1 <= len(raw_ids) <= 12:
        raise ValidationError("برای مسیر باید بین ۱ تا ۱۲ مشتری انتخاب شود")
    customer_ids = list(dict.fromkeys(uuid(value, "شناسه مشتری") for value in raw_ids))
    with get_db() as db, db.cursor() as cur:
        cur.execute(
            """select c.id,trim(concat_ws(' ',c.first_name,c.last_name)) name,c.map_label,c.address,
                      st_y(c.location::geometry) latitude,st_x(c.location::geometry) longitude,
                      (select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone
               from customers_v2 c where c.id=any(%s) and c.location is not null and c.archived=false""",
            (customer_ids,),
        )
        rows = cur.fetchall()
    by_id = {str(row["id"]): row for row in rows}
    stops = [by_id[str(cid)] for cid in customer_ids if str(cid) in by_id]
    if len(stops) != len(customer_ids):
        return jsonify({"error": "یکی از مشتری‌ها موقعیت GPS معتبر ندارد"}), 400

    points = [(start_lat, start_lng)] + [(float(row["latitude"]), float(row["longitude"])) for row in stops]
    coord_text = ";".join(f"{lng},{lat}" for lat, lng in points)
    provider = "haversine-fallback"
    matrix = [[_haversine(a, b) for b in points] for a in points]
    try:
        table = _fetch_json(f"{ROUTING_URL}/table/v1/driving/{coord_text}?annotations=duration,distance")
        durations = table.get("durations") or []
        valid_matrix = len(durations) == len(points) and all(
            isinstance(row, list) and len(row) == len(points)
            and all(value is None or isinstance(value, (int, float)) for value in row)
            for row in durations
        )
        if table.get("code") == "Ok" and valid_matrix:
            matrix = durations
            provider = "osrm"
    except Exception:
        app.logger.warning("routing_table_fallback", exc_info=True)

    order = _nearest_neighbor(matrix)
    ordered_stops = [stops[index - 1] for index in order]
    ordered_points = [points[0]] + [points[index] for index in order]
    geometry, total_distance, total_duration = None, 0, 0
    if provider == "osrm":
        ordered_coords = ";".join(f"{lng},{lat}" for lat, lng in ordered_points)
        try:
            route = _fetch_json(f"{ROUTING_URL}/route/v1/driving/{ordered_coords}?overview=full&geometries=geojson&steps=false")
            best = route.get("routes", [])[0]
            geometry = best.get("geometry")
            total_distance = round(best.get("distance", 0))
            total_duration = round(best.get("duration", 0))
        except Exception:
            app.logger.warning("routing_geometry_fallback", exc_info=True)
    if not total_distance:
        total_distance = round(sum(_haversine(ordered_points[i - 1], ordered_points[i]) for i in range(1, len(ordered_points))))

    items = []
    previous = ordered_points[0]
    for row, point in zip(ordered_stops, ordered_points[1:]):
        item = row_json(row)
        item["distance_from_previous_m"] = round(_haversine(previous, point))
        items.append(item)
        previous = point
    return jsonify({
        "provider": provider, "distance_m": total_distance, "duration_s": total_duration,
        "geometry": geometry, "stops": items,
    })
