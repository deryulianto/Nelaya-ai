from __future__ import annotations

import math
from typing import Dict, List

import numpy as np
from sklearn.cluster import DBSCAN

from app.services.behavior_today import get_behavior_today


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def _to_radians(points):
    return np.radians(points)


def compute_behavior_zones(
    *,
    species: str = "medium_pelagic",
    hotspot_threshold: float = 0.55,
    top_k: int = 80,
    eps_km: float = 25.0,
    min_samples: int = 4,
) -> Dict:

    data = get_behavior_today(
        species=species,
        hotspot_threshold=hotspot_threshold,
        top_k=top_k,
    )

    pts = data["points"]

    if not pts:
        return {
            "date": data["date"],
            "zones": [],
            "message": "Tidak ada hotspot yang cukup untuk membentuk zona."
        }

    coords = np.array([[p["lat"], p["lon"]] for p in pts])
    coords_rad = _to_radians(coords)

    # DBSCAN dengan jarak haversine
    kms_per_radian = 6371.0
    db = DBSCAN(
        eps=eps_km / kms_per_radian,
        min_samples=min_samples,
        metric="haversine",
    ).fit(coords_rad)

    labels = db.labels_

    zones = []

    for label in set(labels):
        if label == -1:
            continue

        cluster_idx = np.where(labels == label)[0]
        cluster_pts = [pts[i] for i in cluster_idx]

        lats = np.array([p["lat"] for p in cluster_pts])
        lons = np.array([p["lon"] for p in cluster_pts])
        scores = np.array([p["score"] for p in cluster_pts])

        center_lat = float(lats.mean())
        center_lon = float(lons.mean())

        # radius maksimum dari center
        dists = [
            _haversine_km(center_lat, center_lon, p["lat"], p["lon"])
            for p in cluster_pts
        ]

        radius_km = float(max(dists))

        zones.append({
            "center_lat": center_lat,
            "center_lon": center_lon,
            "radius_km": round(radius_km, 2),
            "point_count": len(cluster_pts),
            "mean_score": float(scores.mean()),
            "max_score": float(scores.max()),
        })

    # urutkan zona terbaik
    zones = sorted(zones, key=lambda z: z["mean_score"], reverse=True)

    return {
        "date": data["date"],
        "species": species,
        "zone_count": len(zones),
        "zones": zones,
    }