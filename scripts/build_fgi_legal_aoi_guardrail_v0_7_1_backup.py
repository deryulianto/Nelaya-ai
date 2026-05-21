#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]

INPUT_LEGAL_GRID = ROOT / "data/fgi/species_grid_legal_today.geojson"
INPUT_REGIONS = ROOT / "data/regions/aceh_regions.json"

OUT_GEOJSON = ROOT / "data/fgi/species_grid_legal_aoi_today.geojson"
OUT_SUMMARY = ROOT / "data/fgi/legal_zone_aoi_today.json"


def now_jakarta() -> str:
    return datetime.now(ZoneInfo("Asia/Jakarta")).isoformat()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def bbox_area(bbox: list[float]) -> float:
    min_lon, min_lat, max_lon, max_lat = bbox
    return abs((max_lon - min_lon) * (max_lat - min_lat))


def point_in_bbox(lon: float, lat: float, bbox: list[float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def region_priority(region: dict[str, Any]) -> tuple[int, float]:
    """
    Prioritas:
    - island lebih spesifik daripada sea
    - bbox lebih kecil lebih spesifik
    """
    rtype = region.get("type")
    type_rank = 0 if rtype == "island" else 1
    area = bbox_area(region.get("bbox") or [0, 0, 999, 999])
    return type_rank, area


def match_region(lon: float, lat: float, regions: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    matches = []

    for region in regions:
        bbox = region.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue

        if point_in_bbox(lon, lat, [float(x) for x in bbox]):
            matches.append(region)

    if not matches:
        return None

    matches.sort(key=region_priority)
    return matches[0]


def aoi_confidence(region: Optional[dict[str, Any]]) -> str:
    if not region:
        return "none"

    if region.get("type") == "island":
        return "medium"

    # sea bbox masih luas, jadi confidence rendah
    return "low"


def classify_aoi(
    props: dict[str, Any],
    region: Optional[dict[str, Any]],
) -> dict[str, Any]:
    legal_zone = props.get("legal_zone")
    small_allowed = bool(props.get("small_fisher_allowed"))

    if region is None:
        if legal_zone == "zone_0_4_nm":
            return {
                "aceh_relevance": "needs_check",
                "aceh_region_name": None,
                "aceh_region_type": None,
                "aceh_aoi_confidence": "none",
                "small_fisher_mode_visible": False,
                "aoi_warning": (
                    "Titik dekat pantai, tetapi belum masuk AOI Aceh yang dikenali "
                    "dari file region. Perlu verifikasi coastline/AOI resmi."
                ),
            }

        return {
            "aceh_relevance": "outside_known_aoi",
            "aceh_region_name": None,
            "aceh_region_type": None,
            "aceh_aoi_confidence": "none",
            "small_fisher_mode_visible": False,
            "aoi_warning": (
                "Titik berada di luar AOI Aceh yang dikenali dari file region sementara."
            ),
        }

    confidence = aoi_confidence(region)
    rtype = region.get("type")
    rname = region.get("name")

    visible = small_allowed and legal_zone == "zone_0_4_nm"

    if visible:
        warning = (
            f"Titik berada dalam zona 0–4 mil dan berada dalam konteks {rname}. "
            "Tetap gunakan sebagai observasi awal, bukan keputusan legal final."
        )
    elif legal_zone == "zone_0_4_nm":
        warning = (
            f"Titik dekat pantai dan berada dalam konteks {rname}, tetapi status nelayan kecil "
            "perlu dicek ulang."
        )
    else:
        warning = (
            f"Titik berada dalam konteks {rname}, tetapi di luar zona 0–4 mil untuk nelayan kecil."
        )

    if rtype == "sea":
        warning += (
            " Catatan: region laut berbasis bbox masih luas, sehingga perlu validasi AOI lebih rinci."
        )

    return {
        "aceh_relevance": "aceh_context",
        "aceh_region_name": rname,
        "aceh_region_type": rtype,
        "aceh_aoi_confidence": confidence,
        "small_fisher_mode_visible": visible,
        "aoi_warning": warning,
    }


def compact_feature(feat: dict[str, Any]) -> dict[str, Any]:
    coords = (feat.get("geometry") or {}).get("coordinates") or [None, None]
    props = feat.get("properties") or {}

    return {
        "lon": coords[0],
        "lat": coords[1],
        "distance_to_coast_nm": props.get("distance_to_coast_nm"),
        "legal_zone": props.get("legal_zone"),
        "small_fisher_allowed": props.get("small_fisher_allowed"),
        "small_fisher_mode_visible": props.get("small_fisher_mode_visible"),
        "aceh_region_name": props.get("aceh_region_name"),
        "aceh_region_type": props.get("aceh_region_type"),
        "aceh_aoi_confidence": props.get("aceh_aoi_confidence"),
        "small_fisher_relevant_score": props.get("small_fisher_relevant_score"),
        "small_fisher_recommendation": props.get("small_fisher_recommendation"),
        "aoi_warning": props.get("aoi_warning"),
    }


def count_by(features: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}

    for feat in features:
        props = feat.get("properties") or {}
        value = str(props.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1

    return counts


def main() -> None:
    if not INPUT_LEGAL_GRID.exists():
        raise FileNotFoundError(
            f"Legal grid belum ada: {INPUT_LEGAL_GRID}. "
            "Jalankan scripts/build_fgi_legal_zone.py dulu."
        )

    if not INPUT_REGIONS.exists():
        raise FileNotFoundError(
            f"File region belum ada: {INPUT_REGIONS}. "
            "Simpan aceh_regions.json ke data/regions/aceh_regions.json."
        )

    legal_grid = read_json(INPUT_LEGAL_GRID)
    regions = read_json(INPUT_REGIONS)

    features = legal_grid.get("features") or []
    out_features = []

    for feat in features:
        geometry = feat.get("geometry") or {}
        coords = geometry.get("coordinates") or []

        props = dict(feat.get("properties") or {})

        lon = to_float(coords[0]) if isinstance(coords, list) and len(coords) >= 2 else None
        lat = to_float(coords[1]) if isinstance(coords, list) and len(coords) >= 2 else None

        region = match_region(lon, lat, regions) if lon is not None and lat is not None else None
        aoi = classify_aoi(props, region)

        props.update(
            {
                "legal_aoi_version": "0.7.1",
                **aoi,
                "aoi_note": (
                    "Aceh AOI Guardrail v0.7.1 memakai bbox region sementara. "
                    "Ini bukan batas hukum final dan perlu diganti dengan AOI resmi/validasi lokal."
                ),
            }
        )

        out_features.append(
            {
                **feat,
                "properties": props,
            }
        )

    out_geojson = {
        **legal_grid,
        "module": "fgi_legal_aware_species_grid_aoi",
        "version": "0.7.1",
        "generated_at": now_jakarta(),
        "source_legal_grid": str(INPUT_LEGAL_GRID.relative_to(ROOT)),
        "source_regions": str(INPUT_REGIONS.relative_to(ROOT)),
        "feature_count": len(out_features),
        "features": out_features,
        "limitations": [
            "AOI guardrail memakai bbox region sementara, bukan batas hukum resmi.",
            "Region laut seperti Selat Malaka dan Laut Andaman masih terlalu luas.",
            "Coastline masih proxy GEBCO jika legal grid dibangun dari GEBCO.",
            "Gunakan sebagai filter awal small-fisher mode, bukan keputusan hukum final.",
        ],
    }

    visible_small_fisher = [
        f for f in out_features
        if (f.get("properties") or {}).get("small_fisher_mode_visible") is True
    ]

    top_visible = sorted(
        visible_small_fisher,
        key=lambda f: to_float((f.get("properties") or {}).get("small_fisher_relevant_score")) or -1,
        reverse=True,
    )[:10]

    summary = {
        "module": "fgi_legal_aoi_summary",
        "version": "0.7.1",
        "generated_at": out_geojson["generated_at"],
        "source_legal_grid": out_geojson["source_legal_grid"],
        "source_regions": out_geojson["source_regions"],
        "output_geojson": str(OUT_GEOJSON.relative_to(ROOT)),
        "feature_count": len(out_features),
        "aoi_counts": count_by(out_features, "aceh_relevance"),
        "region_counts": count_by(out_features, "aceh_region_name"),
        "legal_zone_counts": count_by(out_features, "legal_zone"),
        "small_fisher_visible_count": len(visible_small_fisher),
        "top_small_fisher_visible": [compact_feature(f) for f in top_visible],
        "message": (
            "Aceh AOI Guardrail v0.7.1 berhasil dibuat. "
            "Titik nelayan kecil hanya dianggap visible jika berada di zona 0–4 mil "
            "dan masuk konteks AOI Aceh sementara."
        ),
        "limitations": out_geojson["limitations"],
    }

    write_json(OUT_GEOJSON, out_geojson)
    write_json(OUT_SUMMARY, summary)

    print(f"OK: wrote {OUT_GEOJSON}")
    print(f"OK: wrote {OUT_SUMMARY}")
    print(f"INFO: features={len(out_features)}")
    print(f"INFO: small_fisher_visible={len(visible_small_fisher)}")


if __name__ == "__main__":
    main()
