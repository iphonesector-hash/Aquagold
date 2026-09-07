"""Branch-scoped professional navigation layer for Aqua Smart Tour.

Keeps the existing map/tour architecture intact while upgrading the served
navigation runtime with real Neshan maneuvers and Aria TTS. No production-only
state and no schema changes.
"""
from pathlib import Path

from flask import request

import app_v3
import aqua_neshan_preview as neshan


def _normalize_direction_pro(payload: dict):
    routes = payload.get("routes") or []
    if not routes:
        return {"points": [], "steps": [], "legs": [], "distance_m": 0, "duration_s": 0, "summary": ""}
    route = routes[0]
    overview = route.get("overview_polyline") or {}
    points = neshan.decode_polyline(overview.get("points") if isinstance(overview, dict) else overview)
    legs_out, all_steps = [], []
    total_distance = total_duration = 0
    summaries = []
    for leg in route.get("legs") or []:
        distance_obj = leg.get("distance") or {}
        duration_obj = leg.get("duration") or {}
        distance = int(distance_obj.get("value") or 0)
        duration = int(duration_obj.get("value") or 0)
        total_distance += distance
        total_duration += duration
        summary = str(leg.get("summary") or "").strip()
        if summary:
            summaries.append(summary)
        leg_points, steps_out = [], []
        for step in leg.get("steps") or []:
            raw_start = step.get("start_location") or []
            start = [raw_start[1], raw_start[0]] if len(raw_start) >= 2 else None
            step_points = neshan.decode_polyline(step.get("polyline"))
            if step_points:
                leg_points.extend(step_points[1:] if leg_points and leg_points[-1] == step_points[0] else step_points)
            step_distance = step.get("distance") or {}
            step_duration = step.get("duration") or {}
            item = {
                "instruction": step.get("instruction") or step.get("name") or "ادامه مسیر",
                "name": step.get("name") or "",
                "type": step.get("type") or "continue",
                "modifier": step.get("modifier") or "straight",
                "bearing_after": step.get("bearing_after"),
                "exit": step.get("exit"),
                "rotary_name": step.get("rotary_name"),
                "distance_m": int(step_distance.get("value") or 0),
                "distance_text": step_distance.get("text") or "",
                "duration_s": int(step_duration.get("value") or 0),
                "duration_text": step_duration.get("text") or "",
                "start": start,
                "points": step_points,
            }
            steps_out.append(item)
            all_steps.append(item)
        legs_out.append({
            "summary": summary,
            "distance_m": distance,
            "distance_text": distance_obj.get("text") or "",
            "duration_s": duration,
            "duration_text": duration_obj.get("text") or "",
            "points": leg_points,
            "steps": steps_out,
        })
    return {
        "points": points,
        "steps": all_steps,
        "legs": legs_out,
        "distance_m": total_distance,
        "duration_s": total_duration,
        "summary": " - ".join(dict.fromkeys(summaries)),
    }


# directions() resolves this module global at call time, so replacing it here
# preserves the existing endpoints while retaining maneuver metadata.
neshan.normalize_direction = _normalize_direction_pro

_NAV_FRAGMENT = Path(__file__).with_name("aqua-navigation-pro-fragment.js")
_NAV_CSS = Path(__file__).with_name("aqua-navigation-pro.css")


@app_v3.app.after_request
def aqua_navigation_pro_assets(response):
    try:
        if request.path == "/aqua-smart-tour.js" and response.status_code == 200:
            response.direct_passthrough = False
            source = response.get_data(as_text=True)
            start = source.find("function createNav(){")
            end = source.find("\n\nfunction enhance()", start)
            if start >= 0 and end > start:
                replacement = _NAV_FRAGMENT.read_text(encoding="utf-8").strip()
                source = source[:start] + replacement + source[end:]
                response.set_data(source)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
        elif request.path == "/aqua-smart-tour.css" and response.status_code == 200:
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            marker = "/* aqua-navigation-pro */"
            if marker not in css:
                css += "\n" + marker + "\n" + _NAV_CSS.read_text(encoding="utf-8")
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_pro_asset_failed: %s", str(exc)[:180])
    return response
