"""Map-only routing geometry hardening for the current AquaGold preview branch.

Neshan's overview polyline may be simplified enough to visually cut corners at
street scale.  The professional normalizer already preserves each maneuver's
polyline, so prefer the concatenated per-leg/per-step geometry whenever it is
available.  This changes only route geometry; ETA, traffic duration, maneuvers
and provider selection remain untouched.
"""
from __future__ import annotations

import aqua_neshan_preview as neshan


_base_normalize_direction = neshan.normalize_direction


def _append_points(target, points):
    for raw in points or []:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        try:
            point = [float(raw[0]), float(raw[1])]
        except (TypeError, ValueError):
            continue
        if not target or target[-1] != point:
            target.append(point)


def _detailed_normalize_direction(payload: dict):
    data = _base_normalize_direction(payload)
    detailed = []

    # The professional normalizer builds each leg from the maneuver polylines.
    # Those points are significantly safer for street-level drawing than the
    # simplified overview polyline returned for route summaries.
    for leg in data.get("legs") or []:
        _append_points(detailed, leg.get("points"))

    if len(detailed) < 2:
        for step in data.get("steps") or []:
            _append_points(detailed, step.get("points"))

    if len(detailed) >= 2:
        data["points"] = detailed
        data["geometry_source"] = "step-polylines"
    else:
        data["geometry_source"] = "overview-polyline"
    return data


# directions() resolves normalize_direction from the module at call time.
neshan.normalize_direction = _detailed_normalize_direction
