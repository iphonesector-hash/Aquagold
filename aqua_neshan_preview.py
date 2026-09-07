"""Neshan provider adapter for AquaGold map/navigation preview.

Secrets are read only from deployment environment variables. The service key is
never returned to the browser or written into application logs.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from flask import jsonify, request

from app_v3 import app, token_required
from aquagold_validation import text


NESHAN_API_BASE = os.getenv("NESHAN_API_BASE", "https://api.neshan.org").rstrip("/")
NESHAN_SERVICE_API_KEY = os.getenv("NESHAN_SERVICE_API_KEY", "").strip()
NESHAN_WEB_API_KEY = os.getenv("NESHAN_WEB_API_KEY", "").strip()


def configuration_status():
    return {
        "service": bool(NESHAN_SERVICE_API_KEY),
        "web": bool(NESHAN_WEB_API_KEY),
        "provider": "neshan",
    }


def _neshan_get(path: str, params: dict | None = None, timeout: int = 12):
    if not NESHAN_SERVICE_API_KEY:
        raise RuntimeError("NESHAN_SERVICE_API_KEY is not configured")
    query = urllib.parse.urlencode(params or {}, safe="|,{}[]:\"")
    url = f"{NESHAN_API_BASE}{path}"
    if query:
        url += "?" + query
    req = urllib.request.Request(
        url,
        headers={
            "Api-Key": NESHAN_SERVICE_API_KEY,
            "Accept": "application/json",
            "User-Agent": "AquaGold-CRM/neshan-preview",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body or "{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8") or "{}")
        except Exception:
            detail = {"status": exc.code}
        app.logger.warning("neshan_http_error status=%s", exc.code)
        raise RuntimeError(detail.get("message") or detail.get("error") or f"Neshan HTTP {exc.code}") from exc
    except Exception as exc:
        app.logger.warning("neshan_request_failed", exc_info=True)
        raise RuntimeError("سرویس نشان موقتاً در دسترس نیست") from exc


@app.get("/api/map/neshan/status")
@token_required
def neshan_status():
    """Safe configuration probe; never exposes the service key."""
    return jsonify(configuration_status())


@app.get("/api/map/neshan/web-config")
@token_required
def neshan_web_config():
    """Return the browser-scoped web key only to an authenticated Aqua session."""
    return jsonify({
        "provider": "neshan",
        "configured": bool(NESHAN_WEB_API_KEY),
        "web_key": NESHAN_WEB_API_KEY if NESHAN_WEB_API_KEY else None,
    })


@app.get("/api/map/neshan/geocode")
@token_required
def neshan_geocode():
    """Geocode a customer address, preferring Neshan Plus for plaque/POI support."""
    query = text(request.args.get("q"), "آدرس", required=True, max_length=700)
    city = text(request.args.get("city"), "شهر", max_length=120)
    province = text(request.args.get("province"), "استان", max_length=120)
    data: dict = {"address": query}
    if city:
        data["city"] = city
    if province:
        data["province"] = province
    try:
        lat = request.args.get("lat")
        lng = request.args.get("lng")
        if lat not in (None, "") and lng not in (None, ""):
            data["location"] = {"latitude": float(lat), "longitude": float(lng)}
    except (TypeError, ValueError):
        pass

    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    try:
        payload = _neshan_get("/geocoding/v1/plus", {"json": encoded})
    except RuntimeError:
        payload = _neshan_get("/geocoding/v1", {"json": encoded})

    items = []
    for item in payload.get("items") or []:
        location = item.get("location") or {}
        if location.get("latitude") is None or location.get("longitude") is None:
            continue
        unmatched = str(item.get("unMatchedTerm") or "").strip()
        items.append({
            "latitude": float(location["latitude"]),
            "longitude": float(location["longitude"]),
            "province": item.get("province"),
            "city": item.get("city"),
            "neighbourhood": item.get("neighbourhood"),
            "unmatched": unmatched,
            "precision": "exact" if not unmatched else "approximate",
            "source": "neshan-plus",
        })
    return jsonify({"provider": "neshan", "items": items[:5]})


@app.get("/api/map/neshan/direction")
@token_required
def neshan_direction():
    """Traffic-aware turn-by-turn directions for a single active destination."""
    origin = text(request.args.get("origin"), "مبدأ", required=True, max_length=80)
    destination = text(request.args.get("destination"), "مقصد", required=True, max_length=80)
    vehicle = (request.args.get("type") or "car").strip().lower()
    if vehicle not in {"car", "motorcycle"}:
        vehicle = "car"
    params = {
        "type": vehicle,
        "origin": origin,
        "destination": destination,
        "alternative": "true" if request.args.get("alternative") == "true" else "false",
        "avoidTrafficZone": "true" if request.args.get("avoidTrafficZone") == "true" else "false",
        "avoidOddEvenZone": "true" if request.args.get("avoidOddEvenZone") == "true" else "false",
    }
    waypoints = (request.args.get("waypoints") or "").strip()
    if waypoints:
        params["waypoints"] = waypoints
    payload = _neshan_get("/v4/direction", params)
    return jsonify({"provider": "neshan", **payload})
