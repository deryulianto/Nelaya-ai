#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path.home() / "NELAYA-AI-LAB"
IN_JSON = BASE_DIR / "data" / "upwelling" / "upwelling_watch_today.json"
OUT_GEOJSON = BASE_DIR / "data" / "upwelling" / "upwelling_candidate_buffers_today.geojson"

DEFAULT_RADIUS_KM = 15
N_SEGMENTS = 96


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def evidence_color(level: str) -> str:
    colors = {
        "sangat_kuat_belum_konklusif": "#22d3ee",
        "kuat_perlu_verifikasi": "#34d399",
        "sedang_perlu_dipantau": "#fbbf24",
        "awal_parsial": "#94a3b8",
        "lemah": "#64748b",
    }
    return colors.get(level, "#94a3b8")


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


def level_from_score(score: float, core_support: int) -> tuple[str, str]:
    if score >= 85 and core_support >= 4:
        return "sangat_kuat_belum_konklusif", "Sangat kuat, belum konklusif"
    if score >= 70 and core_support >= 3:
        return "kuat_perlu_verifikasi", "Kuat, perlu verifikasi"
    if score >= 50 and core_support >= 2:
        return "sedang_perlu_dipantau", "Sedang, perlu dipantau"
    if score >= 30:
        return "awal_parsial", "Sinyal awal/parsial"
    return "lemah", "Lemah"


def normalize_candidates(payload: dict) -> list[dict]:
    candidates = payload.get("candidate_locations") or []

    if candidates:
        return candidates

    # Fallback dari top_cells kalau candidate_locations belum ada.
    out = []

    for cell in payload.get("top_cells", []) or []:
        comps = cell.get("components") or {}
        score = safe_float(cell.get("upi_score"), 0) or 0
        core_support = int(safe_float(comps.get("core_support_count"), 0) or 0)
        level, label = level_from_score(score, core_support)

        out.append({
            "rank": cell.get("rank"),
            "lat": cell.get("lat"),
            "lon": cell.get("lon"),
            "coordinate_text": (
                f"{safe_float(cell.get('lat'), 0):.4f}, {safe_float(cell.get('lon'), 0):.4f}"
            ),
            "zone_label": cell.get("zone_label"),
            "upi_score": round(score, 1),
            "evidence_level": level,
            "evidence_label": label,
            "core_support_text": f"{core_support}/4",
            "coverage_percent": comps.get("coverage_percent"),
            "interpretation_radius_km": payload.get("interpretation_radius_km") or DEFAULT_RADIUS_KM,
            "interpretation": (
                "Titik ini adalah kandidat grid indikatif dan perlu dibaca bersama komponen pendukung."
            ),
        })

    return out


def build_buffer_features(payload: dict):
    features = []

    candidates = normalize_candidates(payload)

    for c in candidates:
        lat = safe_float(c.get("lat"))
        lon = safe_float(c.get("lon"))

        if lat is None or lon is None:
            continue

        radius_km = safe_float(
            c.get("interpretation_radius_km"),
            payload.get("interpretation_radius_km") or DEFAULT_RADIUS_KM,
        )

        score = safe_float(c.get("upi_score"), 0) or 0
        level = c.get("evidence_level") or "awal_parsial"
        label = c.get("evidence_label") or level

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [circle_polygon(lon, lat, radius_km)],
            },
            "properties": {
                "rank": c.get("rank"),
                "coordinate_text": c.get("coordinate_text") or f"{lat:.4f}, {lon:.4f}",
                "zone_label": c.get("zone_label"),
                "upi_score": round(score, 1),
                "evidence_level": level,
                "evidence_label": label,
                "core_support_text": c.get("core_support_text"),
                "coverage_percent": c.get("coverage_percent"),
                "interpretation_radius_km": radius_km,
                "marker_color": c.get("marker_color") or evidence_color(level),
                "note": (
                    "Polygon ini adalah radius interpretasi kandidat UPI, "
                    "bukan batas pasti kejadian upwelling."
                ),
            },
        })

    return features


def main():
    if not IN_JSON.exists():
        raise SystemExit(f"Input tidak ditemukan: {IN_JSON}")

    payload = json.loads(IN_JSON.read_text())
    features = build_buffer_features(payload)

    geojson = {
        "type": "FeatureCollection",
        "name": "NELAYA-AI Upwelling Candidate Interpretation Buffers",
        "generated_at": now_iso(),
        "version": payload.get("version") or "0.4",
        "source_json": str(IN_JSON),
        "features": features,
    }

    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEOJSON.write_text(json.dumps(geojson, indent=2, ensure_ascii=False))

    print(f"Wrote: {OUT_GEOJSON}")
    print(f"Features: {len(features)}")


if __name__ == "__main__":
    main()