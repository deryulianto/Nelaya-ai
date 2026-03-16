from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import math


ROOT_DIR = Path(__file__).resolve().parents[2]
RUMPON_DIR = ROOT_DIR / "data" / "rumpon"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _pick_number(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        n = float(v)
        if math.isfinite(n):
            return n
    except Exception:
        return None
    return None


@lru_cache(maxsize=8)
def load_rumpon_points(filename: str = "rumpon_571_572.geojson") -> List[Dict[str, Any]]:
    path = RUMPON_DIR / filename
    if not path.exists():
        return []

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        feats = obj.get("features") or []
        rows: List[Dict[str, Any]] = []

        for f in feats:
            geom = f.get("geometry") or {}
            if geom.get("type") != "Point":
                continue
            coords = geom.get("coordinates") or []
            if not isinstance(coords, list) or len(coords) < 2:
                continue

            lon = _pick_number(coords[0])
            lat = _pick_number(coords[1])
            if lon is None or lat is None:
                continue

            props = f.get("properties") or {}
            rows.append(
                {
                    "id": props.get("id") or props.get("id_rumpon") or props.get("rumpon_id"),
                    "wpp": str(props.get("wpp") or props.get("wppnri") or ""),
                    "lon": lon,
                    "lat": lat,
                    "legal_score": _pick_number(props.get("legal_score")) or 1.0,
                    "source": props.get("source") or "Kepmen KP 7/2022",
                }
            )
        return rows
    except Exception:
        return []


def nearest_rumpon(
    lat: float,
    lon: float,
    rumpon_points: List[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Optional[float]]:
    best = None
    best_d = None
    for r in rumpon_points:
        d = haversine_km(lat, lon, float(r["lat"]), float(r["lon"]))
        if best_d is None or d < best_d:
            best = r
            best_d = d
    return best, best_d


def count_rumpon_within_radius(
    lat: float,
    lon: float,
    rumpon_points: List[Dict[str, Any]],
    radius_km: float,
) -> int:
    n = 0
    for r in rumpon_points:
        d = haversine_km(lat, lon, float(r["lat"]), float(r["lon"]))
        if d <= radius_km:
            n += 1
    return n


def distance_score(distance_km: Optional[float], lambda_km: float = 15.0) -> float:
    if distance_km is None:
        return 0.0
    lambda_km = max(1e-6, float(lambda_km))
    return float(max(0.0, min(1.0, math.exp(-float(distance_km) / lambda_km))))


def density_score(count_in_radius: int, n_ref: int = 3) -> float:
    if n_ref <= 0:
        return 0.0
    return float(max(0.0, min(1.0, float(count_in_radius) / float(n_ref))))


def legal_score_from_rumpon(r: Optional[Dict[str, Any]]) -> float:
    if not r:
        return 0.0
    try:
        return float(max(0.0, min(1.0, float(r.get("legal_score", 1.0)))))
    except Exception:
        return 1.0


def compute_rumpon_influence(
    lat: float,
    lon: float,
    rumpon_points: List[Dict[str, Any]],
    *,
    lambda_km: float = 15.0,
    radius_km: float = 20.0,
    n_ref: int = 3,
    w_distance: float = 0.7,
    w_density: float = 0.2,
    w_legal: float = 0.1,
) -> Dict[str, Any]:
    nearest, nearest_km = nearest_rumpon(lat, lon, rumpon_points)
    count20 = count_rumpon_within_radius(lat, lon, rumpon_points, radius_km)

    rd = distance_score(nearest_km, lambda_km=lambda_km)
    rn = density_score(count20, n_ref=n_ref)

    # legal score baru: hanya aktif kalau rumpon cukup dekat
    rl = 1.0 if (nearest_km is not None and nearest_km <= radius_km) else 0.0

    total_w = max(1e-6, w_distance + w_density + w_legal)
    wd = w_distance / total_w
    wn = w_density / total_w
    wl = w_legal / total_w

    rii = float(max(0.0, min(1.0, wd * rd + wn * rn + wl * rl)))

    return {
        "nearest_rumpon_id": nearest.get("id") if nearest else None,
        "nearest_rumpon_km": None if nearest_km is None else round(float(nearest_km), 3),
        "rumpon_count_radius": int(count20),
        "distance_score": round(rd, 6),
        "density_score": round(rn, 6),
        "legal_score": round(rl, 6),
        "rumpon_influence": round(rii, 6),
    }