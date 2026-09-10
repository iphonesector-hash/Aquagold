"""Use Neshan's official VRP/logistics solver for Aqua Smart Tour when possible.

The branch keeps Aqua's existing schedule-aware planner as a deterministic
fallback. Neshan VRP gets the current technician position, today's resolved Bale
jobs, their time windows, service durations and live-traffic duration objective.
No data is mutated and no schema changes are required.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import timedelta

import app_v3
import aqua_neshan_preview as neshan
import aqua_smart_tour as smart


_ORIGINAL_SCHEDULE_ORDER = smart._schedule_order


def _post_json(path: str, body: dict, timeout: int = 9):
    if not neshan.NESHAN_SERVICE_API_KEY:
        raise RuntimeError("Neshan service key is not configured")
    url = f"{neshan.NESHAN_API_BASE}{path}"
    payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Api-Key": neshan.NESHAN_SERVICE_API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "AquaGold-CRM/neshan-vrp",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8") or "{}")
        except Exception:
            detail = {}
        raise RuntimeError(detail.get("message") or detail.get("error") or f"Neshan VRP HTTP {exc.code}") from exc


def _time(value):
    return value.astimezone(smart.TEHRAN).strftime("%H:%M:%S")


def _vrp_body(jobs, origin):
    now = smart._now()
    resolved = [j for j in jobs if (j.get("location") or {}).get("quality") != "unresolved"]
    if len(resolved) < 2:
        return None, resolved

    # An explicit end location avoids forcing a return to the technician's
    # current position. The job with the latest allowed finish is a natural
    # open-route anchor; time windows still decide the feasible visit order.
    last_anchor = max(resolved, key=lambda j: j["_schedule"]["end"])
    vehicle_end = last_anchor["location"]
    vehicle_end_dt = max(now + timedelta(minutes=5), last_anchor["_schedule"]["end"])
    work_end = max(now + timedelta(minutes=30), max(j["_schedule"]["end"] for j in resolved), vehicle_end_dt)

    vrp_jobs = []
    for job in resolved:
        schedule = job["_schedule"]
        start = max(now, schedule["start"])
        end = max(start + timedelta(minutes=5), schedule["end"])
        loc = job["location"]
        vrp_jobs.append({
            "id": str(job["id"]),
            "location": {"latitude": float(loc["lat"]), "longitude": float(loc["lng"])},
            "setUpTime": 0,
            "serviceTime": int(smart.DEFAULT_SERVICE_MINUTES * 60),
            "delivery": 0,
            "pickup": 0,
            # Immediate jobs additionally have a tight time window; priority is
            # kept positive and conservative because the platform's exact
            # priority ordering may evolve independently of this branch.
            "priority": 1,
            "skills": [],
            "timeWindows": [{"from": _time(start), "to": _time(end)}],
        })

    body = {
        "vehicles": [{
            "id": "aqua-tech",
            "capacity": max(1, len(resolved)),
            "skills": [],
            "timeWindow": {"from": _time(now), "to": _time(work_end)},
            "startLocation": {"latitude": float(origin[0]), "longitude": float(origin[1])},
            "endLocation": {"latitude": float(vehicle_end["lat"]), "longitude": float(vehicle_end["lng"])},
        }],
        "jobs": vrp_jobs,
        "depot": {"latitude": float(origin[0]), "longitude": float(origin[1])},
        "planTime": 6500,
        "solutionStrategy": "FAST",
        "costType": "DURATION",
        "explorationLevel": "MEDIUM",
        "routingEngine": "car",
        "balanceWorkload": False,
        "useTimeBalancing": False,
        "useTrafficMultiplier": True,
    }
    return body, resolved


def _extract_order(payload: dict, valid_ids: set[str]):
    order = []

    def add(value):
        value = str(value) if value is not None else ""
        if value in valid_ids and value not in order:
            order.append(value)

    routes = payload.get("routes") or (payload.get("solution") or {}).get("routes") or []
    for route in routes:
        for key in ("steps", "activities", "visits"):
            for step in route.get(key) or []:
                if not isinstance(step, dict):
                    continue
                # VROOM-style Neshan responses use `job`; tolerate newer field
                # names while accepting only IDs from this request.
                for candidate in (step.get("job"), step.get("jobId"), step.get("job_id")):
                    add(candidate)
                if str(step.get("type") or "").lower() in {"job", "service", "delivery", "pickup"}:
                    add(step.get("id"))
        for item in route.get("jobs") or []:
            if isinstance(item, dict):
                add(item.get("id") or item.get("job") or item.get("jobId"))
            else:
                add(item)
    return order


def _neshan_schedule_order(jobs, origin, mode):
    fallback_order, matrix, point_index = _ORIGINAL_SCHEDULE_ORDER(jobs, origin, mode)
    if mode != "car":
        return fallback_order, matrix, point_index
    try:
        body, resolved = _vrp_body(jobs, origin)
        if not body:
            return fallback_order, matrix, point_index
        response = _post_json("/vrp/logistic", body)
        valid = {str(j["id"]) for j in resolved}
        ids = _extract_order(response, valid)
        if len(ids) < 2:
            return fallback_order, matrix, point_index
        rank = {job_id: i for i, job_id in enumerate(ids)}
        fallback_rank = {str(job["id"]): i for i, job in enumerate(fallback_order)}
        ordered = sorted(
            fallback_order,
            key=lambda job: (
                0 if str(job["id"]) in rank else 1,
                rank.get(str(job["id"]), fallback_rank.get(str(job["id"]), 999)),
            ),
        )
        app_v3.logger.info("smart_tour_planner=neshan_vrp jobs=%s", len(ids))
        return ordered, matrix, point_index
    except Exception as exc:
        app_v3.logger.warning("smart_tour_vrp_fallback: %s", str(exc)[:170])
        return fallback_order, matrix, point_index


smart._schedule_order = _neshan_schedule_order
