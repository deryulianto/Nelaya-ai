#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path.home() / "NELAYA-AI-LAB"
IN_JSON = BASE_DIR / "data" / "upwelling" / "upwelling_watch_today.json"
OUT_GEOJSON = BASE_DIR / "data" / "upwelling" / "upwelling_candidates_today.geojson"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def evidence_color(level: str) -> str:
    colors = {
        "sangat_kuat_belum_konklusif": "#22d3ee",
        "kuat_perlu_verifikasi": "#34d399",
        "sedang_perlu_dipantau": "#fbbf24",
        "awal_parsial": "#94a3b8",
        "lemah": "#64748b",
    }
    return colors.get(level, "#94a3b8")


def safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def build_from_candidate_locations(payload: dict) -> list[dict]:
    features = []

    for c in payload.get("candidate_locations", []) or []:
        lat = safe_float(c.get("lat"))
        lon = safe_float(c.get("lon"))

        if lat is None or lon is None:
            continue

        level = c.get("evidence_level") or "awal_parsial"
        drivers = c.get("drivers") or {}

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],
            },
            "properties": {
                "rank": c.get("rank"),
                "coordinate_text": c.get("coordinate_text") or f"{lat:.4f}, {lon:.4f}",
                "zone_label": c.get("zone_label"),
                "upi_score": c.get("upi_score"),
                "evidence_level": level,
                "evidence_label": c.get("evidence_label"),
                "core_support_text": c.get("core_support_text"),
                "coverage_percent": c.get("coverage_percent"),
                "interpretation_radius_km": c.get("interpretation_radius_km") or payload.get("interpretation_radius_km") or 15,
                "interpretation": c.get("interpretation"),
                "strong_drivers": ", ".join(drivers.get("strong_drivers") or []),
                "moderate_drivers": ", ".join(drivers.get("moderate_drivers") or []),
                "marker_color": evidence_color(level),
            },
        })

    return features


def build_from_top_cells(payload: dict) -> list[dict]:
    """
    Fallback kalau candidate_locations belum ada.
    """
    features = []

    for c in payload.get("top_cells", []) or []:
        lat = safe_float(c.get("lat"))
        lon = safe_float(c.get("lon"))

        if lat is None or lon is None:
            continue

        score = safe_float(c.get("upi_score")) or 0
        comps = c.get("components") or {}
        core_support = int(safe_float(comps.get("core_support_count")) or 0)

        if score >= 85 and core_support >= 4:
            level = "sangat_kuat_belum_konklusif"
            label = "Sangat kuat, belum konklusif"
        elif score >= 70 and core_support >= 3:
            level = "kuat_perlu_verifikasi"
            label = "Kuat, perlu verifikasi"
        elif score >= 50 and core_support >= 2:
            level = "sedang_perlu_dipantau"
            label = "Sedang, perlu dipantau"
        elif score >= 30:
            level = "awal_parsial"
            label = "Sinyal awal/parsial"
        else:
            level = "lemah"
            label = "Lemah"

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],
            },
            "properties": {
                "rank": c.get("rank"),
                "coordinate_text": f"{lat:.4f}, {lon:.4f}",
                "zone_label": c.get("zone_label"),
                "upi_score": round(score, 1),
                "evidence_level": level,
                "evidence_label": label,
                "core_support_text": f"{core_support}/4",
                "coverage_percent": comps.get("coverage_percent"),
                "interpretation_radius_km": payload.get("interpretation_radius_km") or 15,
                "interpretation": "Titik ini adalah kandidat grid indikatif dan perlu dibaca bersama komponen pendukung.",
                "strong_drivers": "",
                "moderate_drivers": "",
                "marker_color": evidence_color(level),
            },
        })

    return features


def main():
    if not IN_JSON.exists():
        raise SystemExit(f"Input tidak ditemukan: {IN_JSON}")

    payload = json.loads(IN_JSON.read_text())

    features = build_from_candidate_locations(payload)

    if not features:
        features = build_from_top_cells(payload)

    geojson = {
        "type": "FeatureCollection",
        "name": "NELAYA-AI Upwelling Candidate Locations",
        "generated_at": now_iso(),
        "version": payload.get("version") or "0.3",
        "source_json": str(IN_JSON),
        "features": features,
    }

    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEOJSON.write_text(json.dumps(geojson, indent=2, ensure_ascii=False))

    print(f"Wrote: {OUT_GEOJSON}")
    print(f"Features: {len(features)}")


if __name__ == "__main__":
    main()
