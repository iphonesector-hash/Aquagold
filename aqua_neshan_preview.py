"""Neshan provider adapter for AquaGold map/navigation preview.

Secrets are read only from deployment environment variables. The service key is
never returned to logs or HTML. The web key is returned only to an authenticated
Aqua session because browser map SDKs necessarily receive that browser-scoped key.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from flask import jsonify, request

from app_v3 import app, limiter, token_required
from aquagold_validation import text

NESHAN_API_BASE = os.getenv("NESHAN_API_BASE", "https://api.neshan.org").rstrip("/")
NESHAN_SERVICE_API_KEY = os.getenv("NESHAN_SERVICE_API_KEY", "").strip()
NESHAN_WEB_API_KEY = os.getenv("NESHAN_WEB_API_KEY", "").strip()


def configuration_status():
    return {"service": bool(NESHAN_SERVICE_API_KEY), "web": bool(NESHAN_WEB_API_KEY), "provider": "neshan"}


def _neshan_get(path: str, params: dict | None = None, timeout: int = 12):
    if not NESHAN_SERVICE_API_KEY:
        raise RuntimeError("کلید سرویس نشان برای این محیط تنظیم نشده است")
    query = urllib.parse.urlencode(params or {}, safe="|,{}[]:\"")
    url = f"{NESHAN_API_BASE}{path}" + (("?" + query) if query else "")
    req = urllib.request.Request(url, headers={"Api-Key": NESHAN_SERVICE_API_KEY, "Accept": "application/json", "User-Agent": "AquaGold-CRM/neshan"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8") or "{}")
        except Exception:
            detail = {}
        app.logger.warning("neshan_http_error status=%s path=%s", exc.code, path)
        raise RuntimeError(detail.get("message") or detail.get("error") or f"Neshan HTTP {exc.code}") from exc
    except Exception as exc:
        app.logger.warning("neshan_request_failed path=%s", path, exc_info=True)
        raise RuntimeError("سرویس نشان موقتاً در دسترس نیست") from exc


def decode_polyline(encoded: str | None):
    if not encoded:
        return []
    index = lat = lng = 0
    out = []
    try:
        while index < len(encoded):
            values = []
            for _ in range(2):
                result = shift = 0
                while True:
                    b = ord(encoded[index]) - 63
                    index += 1
                    result |= (b & 31) << shift
                    shift += 5
                    if b < 32:
                        break
                values.append(~(result >> 1) if result & 1 else result >> 1)
            lat += values[0]
            lng += values[1]
            out.append([lat / 1e5, lng / 1e5])
    except Exception:
        return []
    return out


def normalize_direction(payload: dict):
    routes = payload.get("routes") or []
    if not routes:
        return {"points": [], "steps": [], "legs": [], "distance_m": 0, "duration_s": 0}
    route = routes[0]
    overview = route.get("overview_polyline") or {}
    points = decode_polyline(overview.get("points") if isinstance(overview, dict) else overview)
    legs_out, all_steps = [], []
    total_distance = total_duration = 0
    for leg in route.get("legs") or []:
        distance = int((leg.get("distance") or {}).get("value") or 0)
        duration = int((leg.get("duration") or {}).get("value") or 0)
        total_distance += distance
        total_duration += duration
        leg_points, steps_out = [], []
        for step in leg.get("steps") or []:
            raw_start = step.get("start_location") or []
            start = [raw_start[1], raw_start[0]] if len(raw_start) >= 2 else None
            step_points = decode_polyline(step.get("polyline"))
            if step_points:
                leg_points.extend(step_points[1:] if leg_points and leg_points[-1] == step_points[0] else step_points)
            item = {
                "instruction": step.get("instruction") or step.get("name") or "ادامه مسیر",
                "name": step.get("name") or "",
                "type": step.get("type"), "modifier": step.get("modifier"),
                "distance_m": int((step.get("distance") or {}).get("value") or 0),
                "duration_s": int((step.get("duration") or {}).get("value") or 0),
                "start": start, "points": step_points,
            }
            steps_out.append(item); all_steps.append(item)
        legs_out.append({"summary": leg.get("summary") or "", "distance_m": distance, "duration_s": duration, "points": leg_points, "steps": steps_out})
    return {"points": points, "steps": all_steps, "legs": legs_out, "distance_m": total_distance, "duration_s": total_duration}


def directions(origin, destination, *, vehicle="car", waypoints=None, traffic=True, timeout=16):
    if vehicle not in {"car", "motorcycle", "pedestrian"}:
        vehicle = "car"
    params = {
        "type": vehicle,
        "origin": f"{origin[0]},{origin[1]}",
        "destination": f"{destination[0]},{destination[1]}",
        "avoidTrafficZone": "false", "avoidOddEvenZone": "false", "alternative": "false",
    }
    if waypoints:
        params["waypoints"] = "|".join(f"{p[0]},{p[1]}" for p in waypoints)
    path = "/v4/direction" if traffic and vehicle != "pedestrian" else "/v4/direction/no-traffic"
    return normalize_direction(_neshan_get(path, params, timeout=timeout))


def distance_matrix(points, *, vehicle="car", traffic=True, timeout=16):
    if vehicle not in {"car", "motorcycle", "pedestrian"}:
        vehicle = "car"
    encoded = "|".join(f"{p[0]},{p[1]}" for p in points)
    path = "/v1/distance-matrix" if traffic and vehicle != "pedestrian" else "/v1/distance-matrix/no-traffic"
    params = {"origins": encoded, "destinations": encoded}
    if vehicle != "car":
        params["type"] = vehicle
    return _neshan_get(path, params, timeout=timeout)


def place_search(term, lat, lng, timeout=10):
    return _neshan_get("/v3/search", {"term": term, "lat": lat, "lng": lng}, timeout=timeout)


def geocode_address(address, *, city=None, province=None, plus=True, timeout=10):
    data = {"address": address}
    if city: data["city"] = city
    if province: data["province"] = province
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if plus:
        try:
            return _neshan_get("/geocoding/v1/plus", {"json": encoded}, timeout=timeout)
        except RuntimeError:
            pass
    return _neshan_get("/geocoding/v1", {"json": encoded}, timeout=timeout)


@app.get("/api/map/neshan/status")
@token_required
def neshan_status():
    return jsonify(configuration_status())


@app.get("/api/map/neshan/web-config")
@token_required
def neshan_web_config():
    return jsonify({"provider": "neshan", "configured": bool(NESHAN_WEB_API_KEY), "web_key": NESHAN_WEB_API_KEY or None})


@app.get("/api/map/neshan/geocode")
@token_required
@limiter.limit("60 per hour")
def neshan_geocode():
    query = text(request.args.get("q"), "آدرس", required=True, max_length=700)
    payload = geocode_address(query, city=text(request.args.get("city"), "شهر", max_length=120), province=text(request.args.get("province"), "استان", max_length=120))
    items = []
    for item in payload.get("items") or []:
        location = item.get("location") or {}
        if location.get("latitude") is None or location.get("longitude") is None: continue
        items.append({"latitude": float(location["latitude"]), "longitude": float(location["longitude"]), "province": item.get("province"), "city": item.get("city"), "neighbourhood": item.get("neighbourhood"), "unmatched": str(item.get("unMatchedTerm") or "").strip(), "source": "neshan"})
    return jsonify({"provider": "neshan", "items": items[:5]})


@app.get("/api/map/neshan/direction")
@token_required
@limiter.limit("60 per hour")
def neshan_direction():
    origin = text(request.args.get("origin"), "مبدأ", required=True, max_length=80)
    destination = text(request.args.get("destination"), "مقصد", required=True, max_length=80)
    vehicle = (request.args.get("type") or "car").strip().lower()
    try:
        o = tuple(float(x) for x in origin.split(",", 1)); d = tuple(float(x) for x in destination.split(",", 1))
    except Exception:
        return jsonify({"error": "مبدأ یا مقصد معتبر نیست"}), 400
    traffic = request.args.get("traffic", "1") != "0"
    data = directions(o, d, vehicle=vehicle, traffic=traffic)
    return jsonify({"provider": "neshan", "vehicle": vehicle, "traffic": traffic, **data})
