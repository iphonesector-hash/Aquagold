"""Safe branch-only Today Tour built from active Bale jobs and existing map providers."""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import jsonify, request

import app_routing
import app_v3


TEHRAN = ZoneInfo("Asia/Tehran")
MAX_JOBS = 12
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_WEEKDAYS = {
    "دوشنبه": 0, "سه شنبه": 1, "سه‌شنبه": 1, "چهارشنبه": 2,
    "پنجشنبه": 3, "پنج‌شنبه": 3, "جمعه": 4, "شنبه": 5,
    "یکشنبه": 6, "یک‌شنبه": 6,
}
_IMMEDIATE_RE = re.compile(r"(?:همین\s*(?:الان|اکنون)|همین\s*الآن|از\s*الان|فوری)")
_RANGE_RE = re.compile(r"(?<!\d)(\d{1,2})(?:\s*[:٫.]\s*(\d{1,2}))?\s*(?:الی|تا|\-|–|—)\s*(\d{1,2})(?:\s*[:٫.]\s*(\d{1,2}))?(?!\d)")


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "").translate(_FA_DIGITS).replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")).strip()


def _now():
    return datetime.now(TEHRAN)


def _hour24(hour, text):
    hour = int(hour)
    value = _norm(text)
    if hour >= 12:
        return hour
    if "صبح" in value:
        return hour
    if any(word in value for word in ("عصر", "شب", "غروب")) or 1 <= hour <= 10:
        return hour + 12
    return hour


def _today_schedule(row, now=None):
    now = now or _now()
    raw = _norm(row.get("raw_text"))
    for label, weekday in _WEEKDAYS.items():
        if label in raw and weekday != now.weekday():
            return None
    immediate = bool(_IMMEDIATE_RE.search(raw))
    match = _RANGE_RE.search(raw)
    if match:
        h1, m1 = _hour24(match.group(1), raw), int(match.group(2) or 0)
        h2, m2 = _hour24(match.group(3), raw), int(match.group(4) or 0)
        start = now.replace(hour=min(h1, 23), minute=min(m1, 59), second=0, microsecond=0)
        end = now.replace(hour=min(h2, 23), minute=min(m2, 59), second=0, microsecond=0)
        if end <= start:
            end += timedelta(hours=1)
        return {"immediate": immediate, "start": now if immediate else start, "end": end, "label": "همین الان" if immediate else f"{start:%H:%M} تا {end:%H:%M}"}
    received = row.get("received_at")
    try:
        local = datetime.fromisoformat(str(received).replace("Z", "+00:00")).astimezone(TEHRAN)
        if local.date() != now.date() and not any(label in raw for label in _WEEKDAYS):
            return None
    except Exception:
        pass
    return {"immediate": immediate, "start": now, "end": now.replace(hour=23, minute=59, second=0, microsecond=0), "label": "همین الان" if immediate else "امروز"}


def _haversine(a, b):
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6_371_000 * 2 * math.asin(math.sqrt(h))


def _active_rows():
    now = _now()
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """select id,customer_id,status,customer_name,phone,address,job_type,raw_text,parsed,received_at,updated_at
               from bale_jobs where status in ('new','review') order by received_at asc limit 100"""
        )
        rows = cur.fetchall()
    result = []
    for raw in rows:
        row = app_v3.row_json(raw)
        schedule = _today_schedule(row, now)
        if schedule is None:
            continue
        row["schedule"] = {"immediate": schedule["immediate"], "label": schedule["label"], "start": schedule["start"].isoformat(), "end": schedule["end"].isoformat()}
        row["_schedule"] = schedule
        result.append(row)
        if len(result) >= MAX_JOBS:
            break
    return result


def _saved_customer_location(cur, row):
    customer = None
    if row.get("customer_id"):
        cur.execute(
            """select c.id,c.location_source,c.address,c.map_label,
                      case when c.location is null then null else st_y(c.location::geometry) end latitude,
                      case when c.location is null then null else st_x(c.location::geometry) end longitude
               from customers_v2 c where c.id=%s::uuid and c.archived=false""",
            (str(row["customer_id"]),),
        )
        customer = cur.fetchone()
    phone = app_v3.normalize_phone(row.get("phone"))
    if not customer and phone:
        cur.execute(
            """select c.id,c.location_source,c.address,c.map_label,
                      case when c.location is null then null else st_y(c.location::geometry) end latitude,
                      case when c.location is null then null else st_x(c.location::geometry) end longitude
               from customer_phones p join customers_v2 c on c.id=p.customer_id
               where p.phone=%s and c.archived=false order by p.is_primary desc limit 1""",
            (phone,),
        )
        customer = cur.fetchone()
    return customer


def _resolve_location(row):
    with app_v3.get_db() as db, db.cursor() as cur:
        customer = _saved_customer_location(cur, row)
    if customer and customer.get("latitude") is not None and customer.get("longitude") is not None:
        return {
            "latitude": float(customer["latitude"]), "longitude": float(customer["longitude"]),
            "quality": "exact", "source": str(customer.get("location_source") or "saved"),
            "customer_id": str(customer["id"]),
        }
    address = str(row.get("address") or (customer or {}).get("address") or "").strip()
    if address:
        try:
            results = app_routing.geocode_provider(address, 1)
            if results:
                hit = results[0]
                return {
                    "latitude": hit["latitude"], "longitude": hit["longitude"],
                    "quality": "approximate", "source": "geocode",
                    "customer_id": str(customer["id"]) if customer else None,
                    "formatted_address": hit.get("formatted_address"),
                }
        except Exception:
            app_v3.app.logger.warning("today_tour_geocode_failed", exc_info=True)
    return {"quality": "unresolved", "source": "unresolved", "customer_id": str(customer["id"]) if customer else None}


def _priority(row):
    schedule = row["_schedule"]
    return (0 if schedule["immediate"] else 1, schedule["start"])


def _order(rows, origin):
    remaining = list(rows)
    ordered = []
    current = origin
    while remaining:
        top = min(_priority(row) for row in remaining)
        group = [row for row in remaining if _priority(row) == top]
        resolved = [row for row in group if row["location"].get("latitude") is not None]
        if resolved:
            chosen = min(resolved, key=lambda row: _haversine(current, (row["location"]["latitude"], row["location"]["longitude"])))
            current = (chosen["location"]["latitude"], chosen["location"]["longitude"])
        else:
            chosen = group[0]
        ordered.append(chosen)
        remaining.remove(chosen)
    return ordered


def _route_geometry(origin, ordered):
    points = [origin] + [(row["location"]["latitude"], row["location"]["longitude"]) for row in ordered if row["location"].get("latitude") is not None]
    if len(points) < 2:
        return {"provider": "none", "geometry": None, "distance_m": 0, "duration_s": 0}
    coord_text = ";".join(f"{lng},{lat}" for lat, lng in points)
    try:
        payload = app_routing._fetch_json(f"{app_routing.ROUTING_URL}/route/v1/driving/{coord_text}?overview=full&geometries=geojson&steps=false")
        route = (payload.get("routes") or [])[0]
        return {"provider": "osrm", "geometry": route.get("geometry"), "distance_m": round(route.get("distance", 0)), "duration_s": round(route.get("duration", 0))}
    except Exception:
        return {"provider": "straight-fallback", "geometry": {"type": "LineString", "coordinates": [[lng, lat] for lat, lng in points]}, "distance_m": round(sum(_haversine(points[i - 1], points[i]) for i in range(1, len(points)))), "duration_s": 0}


def _public(row):
    return {key: value for key, value in row.items() if key != "_schedule"}


@app_v3.app.get("/api/map/today-tour/jobs")
@app_v3.roles_required("technician")
def today_tour_jobs():
    rows = _active_rows()
    signature = "|".join(f"{row['id']}:{row.get('status')}:{row.get('updated_at')}" for row in rows)
    return jsonify({"count": len(rows), "signature": hashlib.sha256(signature.encode()).hexdigest()[:18], "jobs": [_public(row) for row in rows]})


@app_v3.app.get("/api/map/today-tour/plan")
@app_v3.roles_required("technician")
@app_v3.limiter.limit("20 per hour")
def today_tour_plan():
    try:
        lat = float(request.args.get("lat")); lng = float(request.args.get("lng"))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError
    except Exception:
        return jsonify({"error": "موقعیت فعلی معتبر نیست"}), 400
    rows = _active_rows()
    for row in rows:
        row["location"] = _resolve_location(row)
    ordered = _order(rows, (lat, lng))
    for index, row in enumerate(ordered, 1):
        row["order"] = index
    route = _route_geometry((lat, lng), ordered)
    exact = sum(row["location"]["quality"] == "exact" for row in ordered)
    approximate = sum(row["location"]["quality"] == "approximate" for row in ordered)
    unresolved = sum(row["location"]["quality"] == "unresolved" for row in ordered)
    return jsonify({
        "generated_at": _now().isoformat(), "jobs": [_public(row) for row in ordered],
        "summary": {"jobs": len(ordered), "exact": exact, "approximate": approximate, "unresolved": unresolved,
                    "distance_m": route["distance_m"], "duration_s": route["duration_s"]},
        "route": route,
    })


@app_v3.app.get("/aqua-today-tour.js")
def aqua_today_tour_js():
    return app_v3.send_from_directory(".", "aqua-today-tour.js", mimetype="application/javascript", max_age=0)


@app_v3.app.after_request
def inject_today_tour(response):
    if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        if "/aqua-today-tour.js" not in body:
            body = body.replace("</body>", '<script src="/aqua-today-tour.js?v=20260914-1"></script></body>', 1)
            response.set_data(body)
            response.headers["Content-Length"] = str(len(response.get_data()))
    return response
