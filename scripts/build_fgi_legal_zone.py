#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SPECIES_GRID = ROOT / "data/fgi/species_grid_today.geojson"
OUT_GEOJSON = ROOT / "data/fgi/species_grid_legal_today.geojson"
OUT_SUMMARY = ROOT / "data/fgi/legal_zone_today.json"

NMI_TO_KM = 1.852


def now_jakarta() -> str:
    return datetime.now(ZoneInfo("Asia/Jakarta")).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0088

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return r * c


def looks_like_coord_pair(value: Any) -> bool:
    if not isinstance(value, list) or len(value) < 2:
        return False

    lon = to_float(value[0])
    lat = to_float(value[1])

    if lon is None or lat is None:
        return False

    return -180 <= lon <= 180 and -90 <= lat <= 90


def collect_coord_pairs(obj: Any) -> list[tuple[float, float]]:
    """
    Mengambil semua pasangan lon/lat dari GeoJSON apa pun:
    Point, LineString, Polygon, MultiPolygon, FeatureCollection.
    Ini pendekatan v0.7: jarak dihitung ke vertex garis pantai.
    Untuk garis pantai yang cukup rapat, hasilnya memadai untuk tagging awal.
    """
    coords: list[tuple[float, float]] = []

    if looks_like_coord_pair(obj):
        lon = float(obj[0])
        lat = float(obj[1])
        coords.append((lon, lat))
        return coords

    if isinstance(obj, dict):
        if "features" in obj and isinstance(obj["features"], list):
            for feature in obj["features"]:
                coords.extend(collect_coord_pairs(feature))
            return coords

        if "geometry" in obj:
            coords.extend(collect_coord_pairs(obj["geometry"]))
            return coords

        if "coordinates" in obj:
            coords.extend(collect_coord_pairs(obj["coordinates"]))
            return coords

        for value in obj.values():
            coords.extend(collect_coord_pairs(value))

        return coords

    if isinstance(obj, list):
        for item in obj:
            coords.extend(collect_coord_pairs(item))

    return coords


def find_coastline_file(cli_path: Optional[str]) -> Path:
    candidates: list[Path] = []

    if cli_path:
        p = Path(cli_path)
        candidates.append(p if p.is_absolute() else ROOT / p)

    env_path = os.getenv("NELAYA_COASTLINE_GEOJSON")
    if env_path:
        p = Path(env_path)
        candidates.append(p if p.is_absolute() else ROOT / p)

    candidates.extend(
        [
            ROOT / "data/coastline/aceh_coastline.geojson",
            ROOT / "data/geo/aceh_coastline.geojson",
            ROOT / "data/gis/aceh_coastline.geojson",
            ROOT / "data/aceh/aceh_coastline.geojson",
            ROOT / "data/aceh/coastline.geojson",
        ]
    )

    for path in candidates:
        if path.exists():
            return path

    raise FileNotFoundError(
        "File coastline/garis pantai Aceh belum ditemukan. "
        "Set path dengan --coastline atau env NELAYA_COASTLINE_GEOJSON. "
        "Contoh: python scripts/build_fgi_legal_zone.py --coastline data/coastline/aceh_coastline.geojson"
    )


def classify_legal_zone(distance_nm: Optional[float]) -> dict[str, Any]:
    if distance_nm is None:
        return {
            "legal_zone": "unknown",
            "legal_zone_label": "Zona belum diketahui",
            "small_fisher_allowed": False,
            "recommended_profiles": [],
            "legal_warning": "Jarak ke pantai belum dapat dihitung.",
        }

    if distance_nm <= 4.0:
        return {
            "legal_zone": "zone_0_4_nm",
            "legal_zone_label": "Zona 0–4 mil laut",
            "small_fisher_allowed": True,
            "recommended_profiles": ["nelayan_kecil", "perahu_kecil"],
            "legal_warning": "Masih dalam zona nelayan kecil. Tetap baca cuaca, arus, gelombang, dan keselamatan.",
        }

    if distance_nm <= 12.0:
        return {
            "legal_zone": "zone_4_12_nm",
            "legal_zone_label": "Zona >4–12 mil laut",
            "small_fisher_allowed": False,
            "recommended_profiles": ["kapal_kecil_menengah_sesuai_izin"],
            "legal_warning": "Di luar zona 0–4 mil. Tidak direkomendasikan untuk nelayan kecil/perahu kecil.",
        }

    return {
        "legal_zone": "beyond_12_nm",
        "legal_zone_label": "Zona >12 mil laut",
        "small_fisher_allowed": False,
        "recommended_profiles": ["kapal_besar_sesuai_izin", "operasi_lepas_pantai"],
        "legal_warning": "Di luar zona nelayan kecil dan menengah dekat pantai. Hanya relevan untuk profil kapal/izin yang sesuai.",
    }


def nearest_coast_distance(lon: float, lat: float, coast_points: list[tuple[float, float]]) -> dict[str, Any]:
    min_km = None
    nearest = None

    for c_lon, c_lat in coast_points:
        d = haversine_km(lon, lat, c_lon, c_lat)
        if min_km is None or d < min_km:
            min_km = d
            nearest = (c_lon, c_lat)

    if min_km is None:
        return {
            "distance_to_coast_km": None,
            "distance_to_coast_nm": None,
            "nearest_coast_lon": None,
            "nearest_coast_lat": None,
        }

    return {
        "distance_to_coast_km": round(min_km, 3),
        "distance_to_coast_nm": round(min_km / NMI_TO_KM, 3),
        "nearest_coast_lon": nearest[0] if nearest else None,
        "nearest_coast_lat": nearest[1] if nearest else None,
    }


def fisher_relevance(props: dict[str, Any], legal: dict[str, Any]) -> dict[str, Any]:
    small_score = to_float(props.get("small_pelagic_score"))
    medium_score = to_float(props.get("medium_pelagic_score"))

    best_score = None
    best_group = None

    candidates = [
        ("small_pelagic", small_score),
        ("medium_pelagic", medium_score),
    ]

    valid = [(name, score) for name, score in candidates if score is not None]
    if valid:
        best_group, best_score = max(valid, key=lambda x: x[1])

    if not legal.get("small_fisher_allowed"):
        return {
            "small_fisher_relevant_score": None,
            "small_fisher_relevant_group": None,
            "small_fisher_recommendation": "di_luar_zona_nelayan_kecil",
            "small_fisher_message": "Titik ini tidak direkomendasikan untuk nelayan kecil karena berada di luar zona 0–4 mil laut.",
        }

    if best_score is None:
        return {
            "small_fisher_relevant_score": None,
            "small_fisher_relevant_group": None,
            "small_fisher_recommendation": "data_belum_cukup",
            "small_fisher_message": "Titik berada dalam zona nelayan kecil, tetapi skor pelagis belum tersedia.",
        }

    if best_score >= 0.70:
        rec = "menarik_dipantau"
    elif best_score >= 0.55:
        rec = "observasi_hati_hati"
    elif best_score >= 0.45:
        rec = "indikatif_rendah"
    else:
        rec = "tidak_prioritas"

    return {
        "small_fisher_relevant_score": round(best_score, 4),
        "small_fisher_relevant_group": best_group,
        "small_fisher_recommendation": rec,
        "small_fisher_message": "Titik berada dalam zona 0–4 mil. Gunakan sebagai observasi awal, bukan kepastian ikan.",
    }


def zone_counts(features: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}

    for feat in features:
        zone = (feat.get("properties") or {}).get("legal_zone", "unknown")
        counts[zone] = counts.get(zone, 0) + 1

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Legal-Aware FGI v0.7")
    parser.add_argument("--species-grid", default=str(DEFAULT_SPECIES_GRID), help="Input species grid GeoJSON")
    parser.add_argument("--coastline", default=None, help="Aceh coastline GeoJSON")
    args = parser.parse_args()

    species_grid_path = Path(args.species_grid)
    if not species_grid_path.is_absolute():
        species_grid_path = ROOT / species_grid_path

    if not species_grid_path.exists():
        raise FileNotFoundError(f"Species grid tidak ditemukan: {species_grid_path}")

    coastline_path = find_coastline_file(args.coastline)

    species_grid = read_json(species_grid_path)
    coastline = read_json(coastline_path)

    coast_points = collect_coord_pairs(coastline)
    if not coast_points:
        raise ValueError(f"Tidak ada koordinat lon/lat yang dapat dibaca dari coastline: {coastline_path}")

    features = species_grid.get("features") or []
    out_features = []

    for feat in features:
        geometry = feat.get("geometry") or {}
        coords = geometry.get("coordinates") or []

        if not looks_like_coord_pair(coords):
            props = dict(feat.get("properties") or {})
            props.update(
                {
                    "legal_zone_version": "0.7",
                    "distance_to_coast_km": None,
                    "distance_to_coast_nm": None,
                    "legal_zone": "unknown",
                    "legal_zone_label": "Zona belum diketahui",
                    "small_fisher_allowed": False,
                    "recommended_profiles": [],
                    "legal_warning": "Geometry titik tidak valid.",
                }
            )

            out_features.append({**feat, "properties": props})
            continue

        lon = float(coords[0])
        lat = float(coords[1])

        distance = nearest_coast_distance(lon, lat, coast_points)
        legal = classify_legal_zone(distance.get("distance_to_coast_nm"))

        props = dict(feat.get("properties") or {})
        relevance = fisher_relevance(props, legal)

        props.update(
            {
                "legal_zone_version": "0.7",
                **distance,
                **legal,
                **relevance,
                "legal_note": "Legal-Aware FGI v0.7 memakai jarak titik grid ke vertex garis pantai. Ini alat bantu awal, bukan penetapan hukum final.",
            }
        )

        out_features.append({**feat, "properties": props})

    out_geojson = {
        **species_grid,
        "module": "fgi_legal_aware_species_grid",
        "version": "0.7",
        "generated_at": now_jakarta(),
        "source_species_grid": str(species_grid_path.relative_to(ROOT)),
        "source_coastline": str(coastline_path.relative_to(ROOT)),
        "coastline_point_count": len(coast_points),
        "feature_count": len(out_features),
        "features": out_features,
        "limitations": [
            "Jarak ke pantai dihitung dari titik grid ke vertex GeoJSON garis pantai.",
            "Akurasi bergantung pada kualitas dan kerapatan file garis pantai.",
            "Grid FGI saat ini masih kasar untuk kebutuhan 0–4 mil nelayan kecil.",
            "Gunakan sebagai filter awal legal-operasional, bukan keputusan hukum final.",
        ],
    }

    counts = zone_counts(out_features)
    nearshore_features = [
        f for f in out_features
        if (f.get("properties") or {}).get("legal_zone") == "zone_0_4_nm"
    ]

    top_small_fisher = sorted(
        nearshore_features,
        key=lambda f: to_float((f.get("properties") or {}).get("small_fisher_relevant_score")) or -1,
        reverse=True,
    )[:10]

    def compact(feat: dict[str, Any]) -> dict[str, Any]:
        geometry = feat.get("geometry") or {}
        coords = geometry.get("coordinates") or [None, None]
        props = feat.get("properties") or {}

        return {
            "lon": coords[0],
            "lat": coords[1],
            "distance_to_coast_nm": props.get("distance_to_coast_nm"),
            "legal_zone": props.get("legal_zone"),
            "legal_zone_label": props.get("legal_zone_label"),
            "small_fisher_allowed": props.get("small_fisher_allowed"),
            "small_fisher_relevant_score": props.get("small_fisher_relevant_score"),
            "small_fisher_relevant_group": props.get("small_fisher_relevant_group"),
            "small_fisher_recommendation": props.get("small_fisher_recommendation"),
            "small_fisher_message": props.get("small_fisher_message"),
            "drivers": props.get("drivers"),
            "cautions": props.get("cautions"),
        }

    summary_message = (
        "Legal-Aware FGI berhasil dibuat. "
        "Gunakan layer ini untuk memfilter titik FGI berdasarkan jarak dari pantai dan profil nelayan."
    )

    if counts.get("zone_0_4_nm", 0) == 0:
        summary_message += (
            " Tidak ada titik grid yang jatuh dalam zona 0–4 mil. "
            "Ini menandakan grid saat ini terlalu kasar untuk nelayan kecil; perlu Coastal FGI resolusi lebih halus."
        )

    summary = {
        "module": "fgi_legal_zone_summary",
        "version": "0.7",
        "generated_at": out_geojson["generated_at"],
        "source_species_grid": out_geojson["source_species_grid"],
        "source_coastline": out_geojson["source_coastline"],
        "output_geojson": str(OUT_GEOJSON.relative_to(ROOT)),
        "feature_count": len(out_features),
        "zone_counts": counts,
        "nearshore_0_4_nm_count": counts.get("zone_0_4_nm", 0),
        "zone_4_12_nm_count": counts.get("zone_4_12_nm", 0),
        "beyond_12_nm_count": counts.get("beyond_12_nm", 0),
        "top_small_fisher_cells": [compact(f) for f in top_small_fisher],
        "message": summary_message,
        "limitations": out_geojson["limitations"],
    }

    write_json(OUT_GEOJSON, out_geojson)
    write_json(OUT_SUMMARY, summary)

    print(f"OK: wrote {OUT_GEOJSON}")
    print(f"OK: wrote {OUT_SUMMARY}")
    print(f"INFO: species_grid={species_grid_path}")
    print(f"INFO: coastline={coastline_path}")
    print(f"INFO: coast_points={len(coast_points)}")


if __name__ == "__main__":
    main()
