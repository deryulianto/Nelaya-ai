from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def distance_km(p1: Dict[str, Any], p2: Dict[str, Any]) -> float:
    lat1, lon1 = float(p1["lat"]), float(p1["lon"])
    lat2, lon2 = float(p2["lat"]), float(p2["lon"])

    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def total_distance_km(points: List[Dict[str, Any]]) -> float:
    if len(points) < 2:
        return 0.0
    return sum(distance_km(points[i - 1], points[i]) for i in range(1, len(points)))


def duration_hours(trip: Dict[str, Any]) -> Optional[float]:
    start = parse_dt(trip.get("start_time"))
    end_obj = trip.get("end") or {}
    end = parse_dt(end_obj.get("end_time"))

    if not start or not end:
        return None

    return max(0.0, (end - start).total_seconds() / 3600)


def movement_label(points: List[Dict[str, Any]], min_distance_km: float = 0.3) -> str:
    d = total_distance_km(points)
    if len(points) < 2:
        return "single_point"
    if d < min_distance_km:
        return "static_or_test"
    return "active_movement"


def data_quality_score(trip: Dict[str, Any]) -> float:
    points = trip.get("points") or []
    score = 0.0

    if len(points) >= 1:
        score += 0.25
    if len(points) >= 3:
        score += 0.25

    d = total_distance_km(points)
    if d >= 0.3:
        score += 0.25

    if trip.get("status") == "completed" and trip.get("end"):
        score += 0.25

    return round(min(score, 1.0), 4)


def fgi_bias_label(trip: Dict[str, Any]) -> str:
    ctx = trip.get("fgi_context") or {}
    end = trip.get("end") or {}

    p = ctx.get("trip_success_probability")
    success = end.get("trip_success")

    if p is None or success is None:
        return "no_fgi_calibration_context"

    p = float(p)
    success = int(success)

    if success == 1 and p < 0.5:
        return "model_underestimate"
    if success == 0 and p > 0.65:
        return "model_overestimate"
    return "model_consistent_or_uncertain"


def enrich_trip_metrics(trip: Dict[str, Any]) -> Dict[str, Any]:
    points = trip.get("points") or []

    metrics = {
        "points_count": len(points),
        "distance_km": round(total_distance_km(points), 4),
        "duration_hours": duration_hours(trip),
        "movement": movement_label(points),
        "data_quality": data_quality_score(trip),
        "fgi_bias": fgi_bias_label(trip),
    }

    return metrics
