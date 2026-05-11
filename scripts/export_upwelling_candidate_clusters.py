#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

BASE_DIR = Path("/home/coastalai/NELAYA-AI-LAB")
IN_JSON = BASE_DIR / "data" / "upwelling" / "upwelling_watch_today.json"

OUT_JSON = BASE_DIR / "data" / "upwelling" / "upwelling_candidate_clusters_today.json"
OUT_GEOJSON = BASE_DIR / "data" / "upwelling" / "upwelling_candidate_clusters_today.geojson"

DEFAULT_RADIUS_KM = 15
CLUSTER_DISTANCE_KM = 45
N_SEGMENTS = 128


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def circle_polygon(lon: float, lat: float, radius_km: float, n: int = N_SEGMENTS):
    earth_radius_km = 6371.0088
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    angular_distance = radius_km / earth_radius_km

    coords = []

    for i in range(n + 1):
        bearing = 2 * math.pi * i / n

        lat2 = math.asin(
            math.sin(lat1) * math.cos(angular_distance)
            + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
        )

        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
            math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
        )

        coords.append([math.degrees(lon2), math.degrees(lat2)])

    return coords


def evidence_color(level: str) -> str:
    colors = {
        "sangat_kuat_belum_konklusif": "#22d3ee",
        "kuat_perlu_verifikasi": "#34d399",
        "sedang_perlu_dipantau": "#fbbf24",
        "awal_parsial": "#94a3b8",
        "lemah": "#64748b",
    }
    return colors.get(level, "#94a3b8")


def evidence_level_from(max_score: float, max_core_support: int) -> tuple[str, str]:
    if max_score >= 85 and max_core_support >= 4:
        return "sangat_kuat_belum_konklusif", "Sangat kuat, belum konklusif"
    if max_score >= 70 and max_core_support >= 3:
        return "kuat_perlu_verifikasi", "Kuat, perlu verifikasi"
    if max_score >= 50 and max_core_support >= 2:
        return "sedang_perlu_dipantau", "Sedang, perlu dipantau"
    if max_score >= 30:
        return "awal_parsial", "Sinyal awal/parsial"
    return "lemah", "Lemah"


def normalize_candidates(payload: dict) -> list[dict]:
    candidates = payload.get("candidate_locations") or []

    out = []

    for c in candidates:
        lat = safe_float(c.get("lat"))
        lon = safe_float(c.get("lon"))

        if lat is None or lon is None:
            continue

        comps = c.get("components") or {}
        core_support = c.get("core_support")
        if core_support is None:
            core_support = safe_float(comps.get("core_support_count"), 0)

        out.append({
            "rank": c.get("rank"),
            "lat": lat,
            "lon": lon,
            "coordinate_text": c.get("coordinate_text") or f"{lat:.4f}, {lon:.4f}",
            "zone_label": c.get("zone_label") or "Zona tidak diketahui",
            "upi_score": safe_float(c.get("upi_score"), 0) or 0,
            "evidence_level": c.get("evidence_level") or "awal_parsial",
            "evidence_label": c.get("evidence_label") or "Sinyal awal/parsial",
            "core_support": int(safe_float(core_support, 0) or 0),
            "core_support_text": c.get("core_support_text") or f"{int(safe_float(core_support, 0) or 0)}/4",
            "coverage_percent": safe_float(c.get("coverage_percent"), None),
            "interpretation_radius_km": safe_float(
                c.get("interpretation_radius_km"),
                payload.get("interpretation_radius_km") or DEFAULT_RADIUS_KM,
            ),
            "drivers": c.get("drivers") or {},
        })

    return out


def cluster_candidates(candidates: list[dict]) -> list[list[dict]]:
    """
    Clustering sederhana:
    - kandidat lebih dulu dipisahkan menurut zone_label
    - dalam zona yang sama, kandidat digabung jika dekat <= CLUSTER_DISTANCE_KM
    """
    by_zone = defaultdict(list)

    for c in candidates:
        by_zone[c["zone_label"]].append(c)

    clusters: list[list[dict]] = []

    for zone, items in by_zone.items():
        items = sorted(items, key=lambda x: x["upi_score"], reverse=True)
        used = set()

        for i, seed in enumerate(items):
            if i in used:
                continue

            cluster = [seed]
            used.add(i)

            changed = True
            while changed:
                changed = False

                for j, other in enumerate(items):
                    if j in used:
                        continue

                    if any(
                        haversine_km(
                            other["lat"], other["lon"],
                            member["lat"], member["lon"],
                        ) <= CLUSTER_DISTANCE_KM
                        for member in cluster
                    ):
                        cluster.append(other)
                        used.add(j)
                        changed = True

            clusters.append(cluster)

    clusters.sort(
        key=lambda cl: (
            max(c["upi_score"] for c in cl),
            len(cl),
        ),
        reverse=True,
    )

    return clusters


def summarize_cluster(cluster: list[dict], cluster_id: int) -> dict:
    scores = [c["upi_score"] for c in cluster]
    lats = [c["lat"] for c in cluster]
    lons = [c["lon"] for c in cluster]
    core_values = [c["core_support"] for c in cluster]

    centroid_lat = sum(lats) / len(lats)
    centroid_lon = sum(lons) / len(lons)

    max_distance = max(
        haversine_km(centroid_lat, centroid_lon, c["lat"], c["lon"])
        for c in cluster
    )

    # Radius klaster = radius titik + jarak titik terjauh dari centroid.
    interpretation_radius_km = round(max(DEFAULT_RADIUS_KM, max_distance + DEFAULT_RADIUS_KM), 1)

    max_score = max(scores)
    mean_score = sum(scores) / len(scores)
    max_core_support = max(core_values)

    level, label = evidence_level_from(max_score, max_core_support)

    # Driver dominan dari semua kandidat dalam klaster.
    driver_counter = defaultdict(int)
    for c in cluster:
        drivers = c.get("drivers") or {}
        for d in drivers.get("strong_drivers") or []:
            driver_counter[d] += 2
        for d in drivers.get("moderate_drivers") or []:
            driver_counter[d] += 1

    dominant_drivers = [
        k for k, _ in sorted(driver_counter.items(), key=lambda item: item[1], reverse=True)
    ][:5]

    zone_counts = defaultdict(int)
    for c in cluster:
        zone_counts[c["zone_label"]] += 1

    primary_zone = sorted(zone_counts.items(), key=lambda item: item[1], reverse=True)[0][0]

    ranks = [c.get("rank") for c in cluster if c.get("rank") is not None]

    if len(cluster) >= 3:
        cluster_type = "klaster_utama"
    elif len(cluster) == 2:
        cluster_type = "klaster_kecil"
    else:
        cluster_type = "kandidat_tunggal"

    interpretation = (
        f"Klaster ini merangkum {len(cluster)} kandidat grid di sekitar {primary_zone}. "
        f"UPI maksimum {max_score:.1f}, rata-rata {mean_score:.1f}, "
        f"dengan bukti inti maksimum {max_core_support}/4. "
        "Zona ini adalah area interpretasi, bukan batas pasti kejadian upwelling."
    )

    return {
        "cluster_id": cluster_id,
        "cluster_type": cluster_type,
        "candidate_count": len(cluster),
        "candidate_ranks": ranks,
        "primary_zone": primary_zone,
        "centroid": {
            "lat": round(centroid_lat, 4),
            "lon": round(centroid_lon, 4),
            "coordinate_text": f"{centroid_lat:.4f}, {centroid_lon:.4f}",
        },
        "upi_score_max": round(max_score, 1),
        "upi_score_mean": round(mean_score, 1),
        "core_support_max": int(max_core_support),
        "core_support_text": f"{int(max_core_support)}/4",
        "evidence_level": level,
        "evidence_label": label,
        "dominant_drivers": dominant_drivers,
        "interpretation_radius_km": interpretation_radius_km,
        "marker_color": evidence_color(level),
        "interpretation": interpretation,
        "members": cluster,
    }


def build_clusters(payload: dict) -> list[dict]:
    candidates = normalize_candidates(payload)
    raw_clusters = cluster_candidates(candidates)

    clusters = [
        summarize_cluster(cluster, idx + 1)
        for idx, cluster in enumerate(raw_clusters)
    ]

    return clusters


def build_cluster_geojson(clusters: list[dict]) -> dict:
    features = []

    for cluster in clusters:
        lat = cluster["centroid"]["lat"]
        lon = cluster["centroid"]["lon"]
        radius_km = cluster["interpretation_radius_km"]

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [circle_polygon(lon, lat, radius_km)],
            },
            "properties": {
                "cluster_id": cluster["cluster_id"],
                "cluster_type": cluster["cluster_type"],
                "candidate_count": cluster["candidate_count"],
                "candidate_ranks": ",".join(str(x) for x in cluster["candidate_ranks"]),
                "primary_zone": cluster["primary_zone"],
                "centroid_text": cluster["centroid"]["coordinate_text"],
                "upi_score_max": cluster["upi_score_max"],
                "upi_score_mean": cluster["upi_score_mean"],
                "core_support_text": cluster["core_support_text"],
                "evidence_level": cluster["evidence_level"],
                "evidence_label": cluster["evidence_label"],
                "dominant_drivers": ", ".join(cluster["dominant_drivers"]),
                "interpretation_radius_km": cluster["interpretation_radius_km"],
                "marker_color": cluster["marker_color"],
                "interpretation": cluster["interpretation"],
                "note": (
                    "Polygon klaster adalah area interpretasi beberapa kandidat UPI, "
                    "bukan batas pasti kejadian upwelling."
                ),
            },
        })

    return {
        "type": "FeatureCollection",
        "name": "NELAYA-AI Upwelling Candidate Clusters",
        "generated_at": now_iso(),
        "features": features,
    }


def main():
    if not IN_JSON.exists():
        raise SystemExit(f"Input tidak ditemukan: {IN_JSON}")

    payload = json.loads(IN_JSON.read_text())

    clusters = build_clusters(payload)

    summary = {
        "module": "upwelling_candidate_clusters",
        "version": "0.5",
        "generated_at": now_iso(),
        "source_json": str(IN_JSON),
        "cluster_distance_km": CLUSTER_DISTANCE_KM,
        "cluster_count": len(clusters),
        "clusters": clusters,
        "scientific_caution": (
            "Klaster UPI merangkum kandidat grid yang berdekatan secara spasial. "
            "Klaster ini adalah zona indikatif upwelling/mixing lokal, bukan batas pasti kejadian."
        ),
    }

    geojson = build_cluster_geojson(clusters)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    OUT_GEOJSON.write_text(json.dumps(geojson, indent=2, ensure_ascii=False))

    print(f"Wrote: {OUT_JSON}")
    print(f"Wrote: {OUT_GEOJSON}")
    print(f"Clusters: {len(clusters)}")


if __name__ == "__main__":
    main()
