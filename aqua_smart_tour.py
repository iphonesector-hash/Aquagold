"""Branch-scoped Aqua Smart Tour.

Builds a live, time-window-aware route from active Bale jobs. Location confidence
is explicit: green=confirmed customer GPS, red=geocoded approximation,
orange=unresolved. No schema migration and no production-only assumptions.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from flask import jsonify, request, send_from_directory

import app_v3
import aqua_neshan_preview as neshan

TEHRAN = ZoneInfo("Asia/Tehran")
MAX_TOUR_JOBS = 12
DEFAULT_SERVICE_MINUTES = 40
MAX_SPECIAL_LOCATIONS = 100
SPECIAL_LOCATION_EMOJIS = ("⭐", "🏦", "🏪", "🏠", "🏢", "📦", "🔧", "💧", "🅿️", "☕", "🏥", "📍")

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_WEEKDAYS = {
    "دوشنبه": 0, "سه شنبه": 1, "سه‌شنبه": 1, "چهارشنبه": 2,
    "پنجشنبه": 3, "پنج‌شنبه": 3, "جمعه": 4, "شنبه": 5, "یکشنبه": 6,
    "یک‌شنبه": 6,
}
_IMMEDIATE_RE = re.compile(r"(?:همین\s*(?:الان|اکنون|آن)|همین\s*الآن|از\s*الان|الانی|فوری)")
_PHONE_RE = re.compile(r"(?<!\d)(09\d{9})(?!\d)")
_RANGE_RE = re.compile(r"(?<!\d)(\d{1,2})(?:\s*[:٫.]\s*(\d{1,2}))?\s*(?:الی|تا|\-|–|—)\s*(\d{1,2})(?:\s*[:٫.]\s*(\d{1,2}))?(?!\d)")
_FROM_NOW_RE = re.compile(r"(?:از\s*)?(?:همین\s*)?(?:الان|الآن|اکنون)\s*(?:الی|تا|\-|–|—)\s*(\d{1,2})(?:\s*[:٫.]\s*(\d{1,2}))?")


def _norm(value):
    return str(value or "").translate(_FA_DIGITS).replace("ي", "ی").replace("ك", "ک")


def _now():
    return datetime.now(TEHRAN)


def _extract_phone(*values):
    for value in values:
        hit = _PHONE_RE.search(_norm(value))
        if hit:
            try:
                return app_v3.normalize_phone(hit.group(1)) or hit.group(1)
            except Exception:
                return hit.group(1)
    return ""


def _looks_like_schedule(value):
    s = _norm(value)
    return bool(_IMMEDIATE_RE.search(s) or _RANGE_RE.search(s) or any(day in s for day in _WEEKDAYS))


def _extract_customer_name(job):
    raw = _norm(job.get("raw_text"))
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        phone_hit = _PHONE_RE.search(line)
        if phone_hit:
            candidate = line[: phone_hit.start()].strip(" -–—،,:؛")
            if candidate and not _looks_like_schedule(candidate):
                return candidate[:160]
    current = str(job.get("customer_name") or "").strip()
    return current if current and not _looks_like_schedule(current) else "مشتری بله"


def _explicit_weekday(text):
    normalized = _norm(text)
    for label, weekday in _WEEKDAYS.items():
        if label in normalized:
            return weekday
    return None


def _hour24(hour, text):
    hour = int(hour)
    s = _norm(text)
    if hour >= 13 or hour == 12:
        return hour
    if "صبح" in s:
        return hour
    if any(word in s for word in ("عصر", "شب", "غروب")):
        return hour + 12 if hour < 12 else hour
    # Aqua field work convention: bare 1..10 means afternoon/evening.
    if 1 <= hour <= 10:
        return hour + 12
    return hour


def _at_today(now, hour, minute=0):
    return now.replace(hour=max(0, min(23, int(hour))), minute=max(0, min(59, int(minute))), second=0, microsecond=0)


def _parse_schedule(job, now=None):
    now = now or _now()
    raw = _norm(job.get("raw_text"))
    weekday = _explicit_weekday(raw)
    if weekday is not None and weekday != now.weekday():
        return None

    immediate = bool(_IMMEDIATE_RE.search(raw))
    from_now = _FROM_NOW_RE.search(raw)
    if from_now:
        end_h = _hour24(from_now.group(1), raw)
        end_m = int(from_now.group(2) or 0)
        end = _at_today(now, end_h, end_m)
        if end <= now:
            end = now + timedelta(hours=1)
        return {"immediate": True, "start": now, "end": end, "label": f"الان تا {end:%H:%M}"}

    match = _RANGE_RE.search(raw)
    if match:
        h1, m1, h2, m2 = int(match.group(1)), int(match.group(2) or 0), int(match.group(3)), int(match.group(4) or 0)
        h1, h2 = _hour24(h1, raw), _hour24(h2, raw)
        start, end = _at_today(now, h1, m1), _at_today(now, h2, m2)
        if end <= start:
            end += timedelta(hours=1)
        return {"immediate": immediate, "start": now if immediate else start, "end": end, "label": "همین الان" if immediate else f"{start:%H:%M} تا {end:%H:%M}"}

    # A single hour immediately after today's weekday, e.g. «سه شنبه 11».
    day_names = "|".join(re.escape(x) for x in _WEEKDAYS)
    single = re.search(rf"(?:{day_names})\s+(\d{{1,2}})(?!\s*(?:الی|تا|\-|–|—))", raw)
    if single:
        hour = _hour24(int(single.group(1)), raw)
        start = _at_today(now, hour, 0)
        return {"immediate": immediate, "start": now if immediate else start, "end": start + timedelta(hours=1), "label": "همین الان" if immediate else f"حدود {start:%H:%M}"}

    received = job.get("received_at")
    try:
        received_local = datetime.fromisoformat(str(received).replace("Z", "+00:00")).astimezone(TEHRAN)
        if weekday is None and received_local.date() != now.date():
            return None
    except Exception:
        pass
    return {"immediate": immediate, "start": now, "end": now.replace(hour=23, minute=59, second=0, microsecond=0), "label": "امروز"}


def _sync_preview_jobs():
    try:
        if (os.getenv("VERCEL_ENV") or "").lower() == "preview":
            import aqua_preview_bale_sync
            aqua_preview_bale_sync._sync_live_bale_inbox()
    except Exception as exc:
        app_v3.logger.warning("smart_tour_preview_sync_failed: %s", str(exc)[:180])


def _active_today_rows():
    _sync_preview_jobs()
    now = _now()
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """select id,customer_id,status,customer_name,phone,address,job_type,raw_text,parsed,received_at,updated_at
               from bale_jobs where status in ('new','review') order by received_at asc limit 100"""
        )
        rows = cur.fetchall()
    result = []
    for raw_row in rows:
        row = app_v3.row_json(raw_row)
        schedule = _parse_schedule(row, now)
        if schedule is None:
            continue
        row["id"] = str(row["id"])
        if row.get("customer_id"):
            row["customer_id"] = str(row["customer_id"])
        row["phone"] = _extract_phone(row.get("phone"), row.get("raw_text"))
        row["display_name"] = _extract_customer_name(row)
        row["schedule"] = {
            "immediate": schedule["immediate"], "label": schedule["label"],
            "start": schedule["start"].isoformat(), "end": schedule["end"].isoformat(),
        }
        row["_schedule"] = schedule
        result.append(row)
        if len(result) >= MAX_TOUR_JOBS:
            break
    return result


def _customer_location(job):
    parsed = job.get("parsed") if isinstance(job.get("parsed"), dict) else {}
    manual = parsed.get("map_location") if isinstance(parsed.get("map_location"), dict) else {}
    try:
        if manual.get("confirmed") and manual.get("latitude") is not None and manual.get("longitude") is not None:
            return {
                "lat": float(manual["latitude"]), "lng": float(manual["longitude"]),
                "quality": "exact", "source": "bale-confirmed", "customer_id": job.get("customer_id"),
            }
    except (TypeError, ValueError):
        pass

    phone = job.get("phone") or _extract_phone(job.get("raw_text"))
    with app_v3.get_db() as db, db.cursor() as cur:
        customer = None
        if job.get("customer_id"):
            cur.execute(
                """select c.id,c.location_source,c.address,
                          case when c.location is null then null else st_y(c.location::geometry) end latitude,
                          case when c.location is null then null else st_x(c.location::geometry) end longitude
                   from customers_v2 c where c.id=%s::uuid and c.archived=false""",
                (job["customer_id"],),
            )
            customer = cur.fetchone()
        if not customer and phone:
            cur.execute(
                """select c.id,c.location_source,c.address,
                          case when c.location is null then null else st_y(c.location::geometry) end latitude,
                          case when c.location is null then null else st_x(c.location::geometry) end longitude
                   from customer_phones p join customers_v2 c on c.id=p.customer_id
                   where p.phone=%s and c.archived=false order by p.is_primary desc limit 1""",
                (phone,),
            )
            customer = cur.fetchone()
    if customer and customer.get("latitude") is not None and customer.get("longitude") is not None:
        source = str(customer.get("location_source") or "")
        quality = "exact" if source in {"gps", "map", "drag", "manual"} else "approximate"
        return {"lat": float(customer["latitude"]), "lng": float(customer["longitude"]), "quality": quality, "source": f"customer-{source or 'saved'}", "customer_id": str(customer["id"])}

    address = str(job.get("address") or "").strip()
    if address:
        try:
            payload = neshan.geocode_address(address, plus=True)
            for item in payload.get("items") or []:
                loc = item.get("location") or {}
                if loc.get("latitude") is not None and loc.get("longitude") is not None:
                    return {
                        "lat": float(loc["latitude"]), "lng": float(loc["longitude"]),
                        "quality": "approximate", "source": "neshan-geocode", "customer_id": str(customer["id"]) if customer else None,
                        "unmatched": str(item.get("unMatchedTerm") or "").strip(),
                    }
        except Exception as exc:
            app_v3.logger.warning("smart_tour_geocode_failed job=%s detail=%s", job.get("id"), str(exc)[:120])
    return {"quality": "unresolved", "source": "unresolved", "customer_id": str(customer["id"]) if customer else None}


def _haversine(a, b):
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6_371_000 * 2 * math.asin(math.sqrt(h))


def _matrix_seconds(points, mode):
    n = len(points)
    fallback = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                meters = _haversine(points[i], points[j])
                speed = 1.35 if mode == "walking" else 8.3
                fallback[i][j] = meters / speed
    try:
        vehicle = "pedestrian" if mode == "walking" else "car"
        payload = neshan.distance_matrix(points, vehicle=vehicle, traffic=(mode != "walking"))
        rows = payload.get("rows") or []
        if len(rows) != n:
            return fallback
        matrix = [[None] * n for _ in range(n)]
        for i, row in enumerate(rows):
            elements = row.get("elements") or []
            for j in range(min(n, len(elements))):
                duration = (elements[j].get("duration") or {}).get("value")
                matrix[i][j] = float(duration) if duration is not None else fallback[i][j]
        return [[fallback[i][j] if matrix[i][j] is None else matrix[i][j] for j in range(n)] for i in range(n)]
    except Exception as exc:
        app_v3.logger.warning("smart_tour_matrix_fallback: %s", str(exc)[:150])
        return fallback


def _priority(job):
    s = job["_schedule"]
    return (0 if s["immediate"] else 1, s["start"], s["end"])


def _schedule_order(jobs, origin, mode):
    resolved = [job for job in jobs if job["location"]["quality"] != "unresolved"]
    point_jobs = [None] + resolved
    points = [origin] + [(job["location"]["lat"], job["location"]["lng"]) for job in resolved]
    matrix = _matrix_seconds(points, mode) if resolved else [[0.0]]
    point_index = {job["id"]: i + 1 for i, job in enumerate(resolved)}

    remaining = jobs[:]
    ordered = []
    current_index = 0
    while remaining:
        best_priority = min(_priority(job) for job in remaining)
        group = [job for job in remaining if _priority(job) == best_priority]
        routable = [job for job in group if job["id"] in point_index]
        if routable:
            chosen = min(routable, key=lambda job: matrix[current_index][point_index[job["id"]]])
            current_index = point_index[chosen["id"]]
        else:
            chosen = group[0]
        ordered.append(chosen)
        remaining.remove(chosen)
    return ordered, matrix, point_index


def _route_legs(ordered, origin, mode):
    routable = [job for job in ordered if job["location"]["quality"] != "unresolved"]
    if not routable:
        return {}, {"distance_m": 0, "duration_s": 0, "points": []}
    coords = [(job["location"]["lat"], job["location"]["lng"]) for job in routable]
    vehicle = "pedestrian" if mode == "walking" else "car"
    try:
        route = neshan.directions(origin, coords[-1], vehicle=vehicle, waypoints=coords[:-1], traffic=(mode != "walking"), timeout=18)
        legs = route.get("legs") or []
        mapped = {job["id"]: (legs[i] if i < len(legs) else {}) for i, job in enumerate(routable)}
        return mapped, route
    except Exception as exc:
        app_v3.logger.warning("smart_tour_direction_failed: %s", str(exc)[:150])
        return {}, {"distance_m": 0, "duration_s": 0, "points": []}


def _public_job(job):
    return {k: v for k, v in job.items() if k != "_schedule"}


def _special_locations_key(user_id=None):
    value = user_id
    if value is None:
        value = (getattr(request, "current_user", {}) or {}).get("user_id")
    value = str(value or "").strip()
    if not value:
        raise RuntimeError("authenticated user is required")
    return f"map_special_locations:{value}"


def _special_coordinate(value, label, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise app_v3.ValidationError(f"{label} نامعتبر است") from None
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise app_v3.ValidationError(f"{label} نامعتبر است")
    return number


def _special_emoji(value, *, strict=True):
    emoji = str(value or "⭐").strip()
    if emoji in SPECIAL_LOCATION_EMOJIS:
        return emoji
    if strict:
        raise app_v3.ValidationError("نشانه موقعیت معتبر نیست")
    return "⭐"


def _clean_special_location(raw):
    if not isinstance(raw, dict):
        return None
    try:
        location_id = str(UUID(str(raw.get("id") or "")))
        name = app_v3.valid_text(raw.get("name"), "نام موقعیت", required=True, max_length=80)
        address = app_v3.valid_text(raw.get("address"), "آدرس", max_length=280) or ""
        lat = _special_coordinate(raw.get("lat"), "عرض جغرافیایی", -90, 90)
        lng = _special_coordinate(raw.get("lng"), "طول جغرافیایی", -180, 180)
        emoji = _special_emoji(raw.get("emoji"), strict=False)
    except (ValueError, TypeError, AttributeError):
        return None
    return {"id": location_id, "name": name, "address": address, "emoji": emoji, "lat": lat, "lng": lng}


def _special_location_payload(raw, existing=None):
    if not isinstance(raw, dict):
        raise app_v3.ValidationError("اطلاعات موقعیت معتبر نیست")
    current = existing or {}
    name = app_v3.valid_text(raw.get("name", current.get("name")), "نام موقعیت", required=True, max_length=80)
    address = app_v3.valid_text(raw.get("address", current.get("address")), "آدرس", max_length=280) or ""
    emoji = _special_emoji(raw.get("emoji", current.get("emoji", "⭐")))
    if existing:
        lat = current["lat"]
        lng = current["lng"]
    else:
        lat = _special_coordinate(raw.get("lat"), "عرض جغرافیایی", -90, 90)
        lng = _special_coordinate(raw.get("lng"), "طول جغرافیایی", -180, 180)
    return {"id": str(current.get("id") or uuid4()), "name": name, "address": address, "emoji": emoji, "lat": lat, "lng": lng}


def _read_special_locations(cur, key, lock=False):
    cur.execute("select value from app_settings where key=%s" + (" for update" if lock else ""), (key,))
    row = cur.fetchone()
    value = (row or {}).get("value") if row else None
    if isinstance(value, dict):
        value = value.get("items")
    if not isinstance(value, list):
        return []
    items = []
    seen = set()
    for raw in value[:MAX_SPECIAL_LOCATIONS]:
        item = _clean_special_location(raw)
        if not item or item["id"] in seen:
            continue
        seen.add(item["id"])
        items.append(item)
    return items


def _lock_special_locations(cur, key):
    cur.execute("select pg_advisory_xact_lock(hashtext(%s))", (key,))


def _write_special_locations(cur, key, items):
    cur.execute(
        """insert into app_settings(key,value,updated_at) values(%s,%s,now())
           on conflict(key) do update set value=excluded.value,updated_at=now()""",
        (key, app_v3.Jsonb({"version": 1, "items": items[:MAX_SPECIAL_LOCATIONS]})),
    )


@app_v3.app.get("/api/map/special-locations")
@app_v3.roles_required("technician")
def special_locations_list():
    key = _special_locations_key()
    with app_v3.get_db() as db, db.cursor() as cur:
        items = _read_special_locations(cur, key)
    return jsonify({"items": items, "count": len(items)})


@app_v3.app.post("/api/map/special-locations")
@app_v3.roles_required("technician")
def special_locations_create():
    item = _special_location_payload(request.get_json(silent=True))
    key = _special_locations_key()
    with app_v3.get_db() as db, db.cursor() as cur:
        _lock_special_locations(cur, key)
        items = _read_special_locations(cur, key, lock=True)
        if len(items) >= MAX_SPECIAL_LOCATIONS:
            return jsonify({"error": "حداکثر ۱۰۰ موقعیت خاص قابل ذخیره است"}), 409
        items.insert(0, item)
        _write_special_locations(cur, key, items)
        app_v3.audit(cur, "map_special_location", item["id"], "create", after=item)
    return jsonify(item), 201


@app_v3.app.patch("/api/map/special-locations/<uuid:location_id>")
@app_v3.roles_required("technician")
def special_locations_update(location_id):
    key = _special_locations_key()
    with app_v3.get_db() as db, db.cursor() as cur:
        _lock_special_locations(cur, key)
        items = _read_special_locations(cur, key, lock=True)
        index = next((i for i, item in enumerate(items) if item["id"] == str(location_id)), -1)
        if index < 0:
            return jsonify({"error": "موقعیت پیدا نشد"}), 404
        before = dict(items[index])
        item = _special_location_payload(request.get_json(silent=True), existing=before)
        items[index] = item
        _write_special_locations(cur, key, items)
        app_v3.audit(cur, "map_special_location", item["id"], "update", before=before, after=item)
    return jsonify(item)


@app_v3.app.delete("/api/map/special-locations/<uuid:location_id>")
@app_v3.roles_required("technician")
def special_locations_delete(location_id):
    key = _special_locations_key()
    with app_v3.get_db() as db, db.cursor() as cur:
        _lock_special_locations(cur, key)
        items = _read_special_locations(cur, key, lock=True)
        before = next((item for item in items if item["id"] == str(location_id)), None)
        if not before:
            return jsonify({"error": "موقعیت پیدا نشد"}), 404
        items = [item for item in items if item["id"] != str(location_id)]
        _write_special_locations(cur, key, items)
        app_v3.audit(cur, "map_special_location", str(location_id), "delete", before=before)
    return jsonify({"ok": True, "id": str(location_id)})


@app_v3.app.get("/api/map/smart-tour/jobs")
@app_v3.token_required
def smart_tour_jobs():
    jobs = _active_today_rows()
    signature_source = "|".join(f"{j['id']}:{j.get('status')}:{j.get('updated_at')}" for j in jobs)
    return jsonify({"count": len(jobs), "signature": hashlib.sha256(signature_source.encode()).hexdigest()[:18], "jobs": [_public_job(j) for j in jobs]})


@app_v3.app.get("/api/map/smart-tour/plan")
@app_v3.token_required
@app_v3.limiter.limit("20 per hour")
def smart_tour_plan():
    try:
        lat = float(request.args.get("lat")); lng = float(request.args.get("lng"))
    except Exception:
        return jsonify({"error": "موقعیت فعلی معتبر نیست"}), 400
    mode = "walking" if request.args.get("mode") == "walking" else "car"
    jobs = _active_today_rows()
    for job in jobs:
        job["location"] = _customer_location(job)
    ordered, matrix, point_index = _schedule_order(jobs, (lat, lng), mode)
    leg_map, route = _route_legs(ordered, (lat, lng), mode)

    cursor_time = _now()
    current_index = 0
    drive_seconds = 0
    for number, job in enumerate(ordered, 1):
        job["order"] = number
        loc = job["location"]
        if loc["quality"] == "unresolved":
            job["eta"] = None; job["travel_s"] = None; job["late_minutes"] = None; job["route_leg"] = None
            continue
        idx = point_index[job["id"]]
        travel = int(matrix[current_index][idx])
        drive_seconds += travel
        arrival = cursor_time + timedelta(seconds=travel)
        start = job["_schedule"]["start"]
        if arrival < start and not job["_schedule"]["immediate"]:
            arrival = start
        late = max(0, int((arrival - job["_schedule"]["end"]).total_seconds() // 60))
        job["eta"] = arrival.isoformat(); job["travel_s"] = travel; job["late_minutes"] = late
        leg = leg_map.get(job["id"]) or {}
        job["route_leg"] = {**leg, "color": "green" if loc["quality"] == "exact" else "red"}
        cursor_time = arrival + timedelta(minutes=DEFAULT_SERVICE_MINUTES)
        current_index = idx

    exact = sum(1 for j in ordered if j["location"]["quality"] == "exact")
    approximate = sum(1 for j in ordered if j["location"]["quality"] == "approximate")
    unresolved = sum(1 for j in ordered if j["location"]["quality"] == "unresolved")
    signature_source = "|".join(f"{j['id']}:{j.get('status')}:{j.get('updated_at')}" for j in ordered)
    return jsonify({
        "provider": "neshan", "mode": mode, "generated_at": _now().isoformat(),
        "signature": hashlib.sha256(signature_source.encode()).hexdigest()[:18],
        "summary": {"jobs": len(ordered), "exact": exact, "approximate": approximate, "unresolved": unresolved,
                    "drive_seconds": int(route.get("duration_s") or drive_seconds), "distance_m": int(route.get("distance_m") or 0),
                    "finish_at": cursor_time.isoformat() if ordered else None},
        "jobs": [_public_job(j) for j in ordered],
    })


@app_v3.app.get("/api/map/smart-tour/route")
@app_v3.token_required
@app_v3.limiter.limit("60 per hour")
def smart_tour_route():
    try:
        origin = tuple(float(x) for x in str(request.args.get("origin") or "").split(",", 1))
        destination = tuple(float(x) for x in str(request.args.get("destination") or "").split(",", 1))
        if len(origin) != 2 or len(destination) != 2:
            raise ValueError
    except Exception:
        return jsonify({"error": "مبدأ یا مقصد معتبر نیست"}), 400
    mode = "walking" if request.args.get("mode") == "walking" else "car"
    vehicle = "pedestrian" if mode == "walking" else "car"
    try:
        route = neshan.directions(origin, destination, vehicle=vehicle, traffic=(mode != "walking"), timeout=16)
        return jsonify({"provider": "neshan", "mode": mode, **route})
    except Exception as exc:
        return jsonify({"error": str(exc)[:180]}), 502


@app_v3.app.get("/api/map/smart-tour/place-search")
@app_v3.token_required
@app_v3.limiter.limit("60 per hour")
def smart_tour_place_search():
    q = app_v3.valid_text(request.args.get("q"), "جست‌وجوی مکان", required=True, max_length=180)
    try:
        lat = float(request.args.get("lat")); lng = float(request.args.get("lng"))
    except Exception:
        lat, lng = 35.6892, 51.3890
    query = json.dumps({"term": q, "center": {"latitude": lat, "longitude": lng}}, ensure_ascii=False, separators=(",", ":"))
    try:
        payload = neshan._neshan_get("/v3/search", {"q": query}, timeout=10)
    except Exception as exc:
        return jsonify({"error": str(exc)[:180]}), 502
    items = []
    for item in payload.get("items") or []:
        loc = item.get("location") or {}
        ilat = loc.get("latitude", loc.get("y")); ilng = loc.get("longitude", loc.get("x"))
        if ilat is None or ilng is None: continue
        items.append({"title": item.get("title") or item.get("name") or q, "address": item.get("address") or item.get("neighbourhood") or "", "latitude": float(ilat), "longitude": float(ilng)})
    return jsonify({"items": items[:10]})


@app_v3.app.patch("/api/map/smart-tour/jobs/<uuid:job_id>/location")
@app_v3.roles_required("technician")
def smart_tour_confirm_location(job_id):
    data = request.get_json(silent=True) or {}
    lat, lng = app_v3.valid_coordinates(data.get("latitude"), data.get("longitude"), required=True)
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select id,customer_id,phone,raw_text,parsed from bale_jobs where id=%s for update", (job_id,))
        job = cur.fetchone()
        if not job:
            return jsonify({"error": "کار بله پیدا نشد"}), 404
        parsed = dict(job.get("parsed") or {})
        parsed["map_location"] = {"latitude": lat, "longitude": lng, "confirmed": True, "source": "manual-map", "confirmed_at": _now().isoformat()}
        cur.execute("update bale_jobs set parsed=%s,updated_at=now() where id=%s", (app_v3.Jsonb(parsed), job_id))
        customer_id = job.get("customer_id")
        phone = _extract_phone(job.get("phone"), job.get("raw_text"))
        if not customer_id and phone:
            cur.execute("select customer_id from customer_phones where phone=%s order by is_primary desc limit 1", (phone,))
            hit = cur.fetchone(); customer_id = hit.get("customer_id") if hit else None
        if customer_id:
            cur.execute("""update customers_v2 set location=st_setsrid(st_makepoint(%s,%s),4326)::geography,
                           location_accuracy_m=null,location_source='manual',updated_at=now() where id=%s""", (lng, lat, customer_id))
        app_v3.audit(cur, "bale_job", job_id, "map_location_confirm", after={"latitude": lat, "longitude": lng, "customer_id": str(customer_id) if customer_id else None})
    return jsonify({"ok": True, "latitude": lat, "longitude": lng, "customer_id": str(customer_id) if customer_id else None})


@app_v3.app.after_request
def smart_tour_propagate_confirmed_location(response):
    try:
        if request.method != "POST" or request.path != "/api/smart/register" or response.status_code >= 300 or not response.is_json:
            return response
        body = request.get_json(silent=True) or {}; bale_job_id = body.get("bale_job_id")
        result = response.get_json(silent=True) or {}; customer_id = result.get("customer_id")
        if not bale_job_id or not customer_id:
            return response
        with app_v3.get_db() as db, db.cursor() as cur:
            cur.execute("select parsed from bale_jobs where id=%s::uuid", (str(bale_job_id),)); row = cur.fetchone()
            parsed = dict(row.get("parsed") or {}) if row else {}; loc = parsed.get("map_location") if isinstance(parsed.get("map_location"), dict) else {}
            if not loc.get("confirmed"):
                return response
            lat, lng = app_v3.valid_coordinates(loc.get("latitude"), loc.get("longitude"), required=True)
            cur.execute("""update customers_v2 set location=st_setsrid(st_makepoint(%s,%s),4326)::geography,
                           location_accuracy_m=null,location_source='manual',updated_at=now() where id=%s::uuid""", (lng, lat, str(customer_id)))
            app_v3.audit(cur, "customer", customer_id, "location_from_bale_tour", after={"latitude": lat, "longitude": lng})
    except Exception as exc:
        app_v3.logger.warning("smart_tour_location_propagate_failed: %s", str(exc)[:180])
    return response


@app_v3.app.get("/aqua-smart-tour.js")
def aqua_smart_tour_js():
    return send_from_directory(".", "aqua-smart-tour.js", mimetype="application/javascript", max_age=0)


@app_v3.app.get("/aqua-smart-tour.css")
def aqua_smart_tour_css():
    return send_from_directory(".", "aqua-smart-tour.css", mimetype="text/css", max_age=0)


@app_v3.app.after_request
def inject_aqua_smart_tour(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response
        response.direct_passthrough = False
        html = response.get_data(as_text=True)
        if "aqua-smart-tour.css" not in html:
            html = html.replace("</head>", '<link rel="stylesheet" href="/aqua-smart-tour.css?v=20260908-t1"></head>', 1)
        if "aqua-smart-tour.js" not in html:
            html = html.replace("</body>", '<script defer src="/aqua-smart-tour.js?v=20260908-t1"></script></body>', 1)
        response.set_data(html)
        response.headers["Content-Length"] = str(len(response.get_data()))
    except Exception as exc:
        app_v3.logger.warning("smart_tour_injection_failed: %s", str(exc)[:180])
    return response
