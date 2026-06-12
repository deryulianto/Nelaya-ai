from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse


router = APIRouter(prefix="/api/v1/grid", tags=["grid"])

BASE = Path("data/grid")


def _latest(pattern: str) -> Optional[Path]:
    files = sorted(Path(".").glob(pattern))
    if not files:
        return None
    return files[-1]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(k): _jsonable(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    if pd.isna(v) if not isinstance(v, (dict, list, tuple)) else False:
        return None
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _read_csv_top(path: Path, sort_col: str, limit: int, cols: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    df = pd.read_csv(path)

    if sort_col in df.columns:
        df = df.sort_values(sort_col, ascending=True)

    keep = [c for c in cols if c in df.columns]
    return _jsonable(df[keep].head(limit).to_dict(orient="records"))


@router.get("/health")
def grid_health() -> dict[str, Any]:
    master = BASE / "master" / "aceh_grid_0083_ocean.csv"
    scoring = _latest("data/grid/daily/grid_scoring_*_calibrated_v011_summary.json")
    hotspot = _latest("data/grid/hotspots/grid_hotspot_????-??-??_v010_summary.json")
    zones = _latest_any(["data/grid/hotspots/grid_hotspot_zones_*_v012_summary.json", "data/grid/hotspots/grid_hotspot_zones_*_v011_summary.json", "data/grid/hotspots/grid_hotspot_zones_*_v010_summary.json"])

    return {
        "module": "nelaya_ai_grid",
        "version": "0.1.0-api",
        "status": "ok" if master.exists() else "missing_master_grid",
        "master_ocean_grid_exists": master.exists(),
        "latest_scoring_summary": str(scoring) if scoring else None,
        "latest_hotspot_summary": str(hotspot) if hotspot else None,
        "latest_zone_summary": str(zones) if zones else None,
        "scientific_note": (
            "Grid endpoints expose experimental suitability, hotspot, and zone layers. "
            "They are not biomass estimates and require field validation."
        ),
    }


@router.get("/scoring/today")
def grid_scoring_today() -> dict[str, Any]:
    path = _latest("data/grid/daily/grid_scoring_*_calibrated_v011_summary.json")
    if path is None:
        path = _latest("data/grid/daily/grid_scoring_*_summary.json")
    if path is None:
        raise HTTPException(status_code=404, detail="No grid scoring summary found")

    data = _read_json(path)
    data["served_from"] = str(path)
    return _jsonable(data)


@router.get("/hotspots/today")
def grid_hotspots_today() -> dict[str, Any]:
    path = _latest("data/grid/hotspots/grid_hotspot_????-??-??_v010_summary.json")
    if path is None:
        raise HTTPException(status_code=404, detail="No grid hotspot summary found")

    data = _read_json(path)
    data["served_from"] = str(path)
    return _jsonable(data)


@router.get("/hotspots/top")
def grid_hotspots_top(limit: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
    path = _latest("data/grid/hotspots/grid_hotspot_????-??-??_v010.csv")
    if path is None:
        raise HTTPException(status_code=404, detail="No grid hotspot CSV found")

    cols = [
        "rank_hotspot_v010",
        "cell_id",
        "lon_center",
        "lat_center",
        "depth_m",
        "depth_class",
        "operational_score_v011",
        "operational_priority_label_v011",
        "safety_label_v011",
        "overall_confidence_v011",
        "local_mean_operational_3x3",
        "local_high_count_3x3",
        "local_core_count_3x3",
        "gi_star_zscore",
        "hotspot_class",
        "hotspot_rank_score",
    ]

    return {
        "module": "nelaya_ai_grid_hotspots_top",
        "version": "0.1.0-api",
        "served_from": str(path),
        "limit": limit,
        "items": _read_csv_top(path, "rank_hotspot_v010", limit, cols),
        "scientific_note": "Top hotspot cells are daily spatial clustering signals, not biomass estimates.",
    }


@router.get("/hotspots/geojson")
def grid_hotspots_geojson():
    path = _latest("data/grid/hotspots/grid_hotspot_????-??-??_v010.geojson")
    if path is None:
        raise HTTPException(status_code=404, detail="No grid hotspot GeoJSON found")

    return FileResponse(
        path,
        media_type="application/geo+json",
        filename=path.name,
    )


@router.get("/hotspots/zones/today")
def grid_hotspot_zones_today() -> dict[str, Any]:
    path = _latest_any(["data/grid/hotspots/grid_hotspot_zones_*_v012_summary.json", "data/grid/hotspots/grid_hotspot_zones_*_v011_summary.json", "data/grid/hotspots/grid_hotspot_zones_*_v010_summary.json"])
    if path is None:
        raise HTTPException(status_code=404, detail="No hotspot zones summary found")

    data = _read_json(path)
    data["served_from"] = str(path)
    return _jsonable(data)


@router.get("/hotspots/zones/top")
def grid_hotspot_zones_top(limit: int = Query(10, ge=1, le=100)) -> dict[str, Any]:
    path = _latest_any(["data/grid/hotspots/grid_hotspot_zones_*_v012.csv", "data/grid/hotspots/grid_hotspot_zones_*_v011.csv", "data/grid/hotspots/grid_hotspot_zones_*_v010.csv"])
    if path is None:
        raise HTTPException(status_code=404, detail="No hotspot zones CSV found")

    cols = [
        "rank_zone",
        "zone_id",
        "date",
        "zone_level",
        "cell_count",
        "core_count",
        "strong_count",
        "candidate_count",
        "lon_center",
        "lat_center",
        "lon_min",
        "lon_max",
        "lat_min",
        "lat_max",
        "depth_mean_m",
        "depth_min_m",
        "depth_max_m",
        "dominant_depth_class",
        "mean_operational_score",
        "max_operational_score",
        "mean_overall_confidence",
        "mean_gi_star_zscore",
        "max_gi_star_zscore",
        "zone_score",
        "safety_counts_json",
    ]

    return {
        "module": "nelaya_ai_grid_hotspot_zones_top",
        "version": "0.1.0-api",
        "served_from": str(path),
        "limit": limit,
        "items": _read_csv_top(path, "rank_zone", limit, cols),
        "scientific_note": (
            "Zones are connected clusters of daily hotspot cells. "
            "They indicate spatially coherent operational suitability signals."
        ),
    }


@router.get("/cell/{cell_id}/today")
def grid_cell_today(cell_id: str) -> dict[str, Any]:
    scoring_path = _latest("data/grid/daily/grid_scoring_*_calibrated_v011.csv")
    hotspot_path = _latest("data/grid/hotspots/grid_hotspot_????-??-??_v010.csv")

    if scoring_path is None:
        raise HTTPException(status_code=404, detail="No calibrated scoring CSV found")

    scoring_df = pd.read_csv(scoring_path)
    scoring_match = scoring_df[scoring_df["cell_id"].astype(str) == cell_id]

    if scoring_match.empty:
        raise HTTPException(status_code=404, detail=f"Cell not found: {cell_id}")

    hotspot_record = None
    if hotspot_path is not None and hotspot_path.exists():
        hotspot_df = pd.read_csv(hotspot_path)
        hotspot_match = hotspot_df[hotspot_df["cell_id"].astype(str) == cell_id]
        if not hotspot_match.empty:
            hotspot_record = hotspot_match.iloc[0].to_dict()

    return _jsonable({
        "module": "nelaya_ai_grid_cell_today",
        "version": "0.1.0-api",
        "cell_id": cell_id,
        "scoring_served_from": str(scoring_path),
        "hotspot_served_from": str(hotspot_path) if hotspot_path else None,
        "scoring": scoring_match.iloc[0].to_dict(),
        "hotspot": hotspot_record,
        "scientific_note": "Cell-level data is experimental suitability information, not confirmed fish biomass.",
    })


@router.get("/brief/today")
def grid_brief_today() -> dict[str, Any]:
    scoring_path = _latest("data/grid/daily/grid_scoring_*_calibrated_v011_summary.json")
    hotspot_path = _latest("data/grid/hotspots/grid_hotspot_????-??-??_v010_summary.json")
    zones_path = _latest_any(["data/grid/hotspots/grid_hotspot_zones_*_v012_summary.json", "data/grid/hotspots/grid_hotspot_zones_*_v011_summary.json", "data/grid/hotspots/grid_hotspot_zones_*_v010_summary.json"])

    if hotspot_path is None:
        raise HTTPException(status_code=404, detail="No grid hotspot summary found")

    hotspot = _read_json(hotspot_path)
    zones = _read_json(zones_path) if zones_path else {}
    scoring = _read_json(scoring_path) if scoring_path else {}

    date = hotspot.get("date") or zones.get("date") or scoring.get("date")

    hotspot_counts = hotspot.get("hotspot_class_counts", {}) or {}
    zone_counts = zones.get("zone_level_counts", {}) or {}
    top_zones = zones.get("top_zones", []) or []
    top_hotspots = hotspot.get("top_hotspots", []) or []

    safety_counts = scoring.get("safety_label_counts_v011", {}) or {}
    coverage = scoring.get("coverage", {}) or {}

    core = int(hotspot_counts.get("hotspot_core", 0) or 0)
    strong = int(hotspot_counts.get("hotspot_strong", 0) or 0)
    candidate = int(hotspot_counts.get("hotspot_candidate", 0) or 0)
    data_limited = int(hotspot_counts.get("data_limited", 0) or 0)

    zones_count = int(zones.get("zones_count", 0) or 0)

    if zones_count > 0 and top_zones:
        z = top_zones[0]
        main_reading = (
            f"NELAYA-AI mendeteksi {zones_count} zona hotspot operasional harian. "
            f"Zona utama berada sekitar {z.get('lon_center')} BT dan {z.get('lat_center')} LU, "
            f"dengan {z.get('cell_count')} grid cell, kedalaman rata-rata sekitar "
            f"{z.get('depth_mean_m')} m, dan kelas dominan {z.get('dominant_depth_class')}."
        )
    elif top_hotspots:
        h = top_hotspots[0]
        main_reading = (
            f"NELAYA-AI mendeteksi sinyal hotspot harian pada grid {h.get('cell_id')} "
            f"di sekitar {h.get('lon_center')} BT dan {h.get('lat_center')} LU, "
            f"dengan skor operasional {h.get('operational_score_v011')}."
        )
    else:
        main_reading = (
            "NELAYA-AI belum mendeteksi zona hotspot utama yang cukup kuat untuk hari ini."
        )

    if core > 0:
        status_label = "hotspot_detected"
        status_text = (
            "Terdapat klaster grid dengan sinyal operasional kuat. "
            "Area ini layak menjadi prioritas pemantauan, bukan klaim kepastian ikan."
        )
    elif strong > 0 or candidate > 0:
        status_label = "candidate_signal"
        status_text = (
            "Terdapat sinyal kandidat hotspot, tetapi perlu dibaca bersama kondisi keselamatan "
            "dan keterbatasan data."
        )
    else:
        status_label = "weak_or_no_signal"
        status_text = (
            "Sinyal hotspot belum kuat. Informasi hari ini sebaiknya dibaca sebagai pemantauan umum."
        )

    cautions = []

    if data_limited > 0:
        cautions.append(
            f"{data_limited} grid cell masuk kategori data_limited, sehingga tidak boleh dibaca sebagai rekomendasi operasional penuh."
        )

    if safety_counts.get("unknown", 0):
        cautions.append(
            f"Sebagian grid memiliki data keselamatan belum lengkap. Safety unknown: {safety_counts.get('unknown')} cell."
        )

    chl_cov = None
    if isinstance(coverage.get("chl"), dict):
        chl_cov = coverage["chl"].get("coverage_pct")

    if chl_cov is not None and chl_cov < 30:
        cautions.append(
            f"Cakupan CHL hari ini masih rendah sekitar {chl_cov}%, sehingga interpretasi produktivitas perlu hati-hati."
        )

    cautions.append(
        "Layer ini adalah experimental operational suitability, bukan estimasi biomassa ikan dan bukan Species Distribution Model final."
    )

    return _jsonable({
        "module": "nelaya_ai_grid_public_brief",
        "version": "0.1.0-api",
        "date": date,
        "status_label": status_label,
        "status_text": status_text,
        "public_reading": main_reading,
        "hotspot_counts": hotspot_counts,
        "zone_counts": zone_counts,
        "zones_count": zones_count,
        "top_zones": top_zones[:5],
        "top_hotspots": top_hotspots[:5],
        "safety_counts": safety_counts,
        "data_coverage": coverage,
        "cautions": cautions,
        "served_from": {
            "scoring": str(scoring_path) if scoring_path else None,
            "hotspot": str(hotspot_path) if hotspot_path else None,
            "zones": str(zones_path) if zones_path else None,
        },
        "scientific_note": (
            "Public brief summarizes grid-cell hotspot intelligence in human-readable form. "
            "It must be paired with field validation, safety checks, and local knowledge."
        ),
    })


def _latest_zone_summary() -> Optional[Path]:
    return _latest_any([
        "data/grid/hotspots/grid_hotspot_zones_*_v012_summary.json",
        "data/grid/hotspots/grid_hotspot_zones_*_v011_summary.json",
        "data/grid/hotspots/grid_hotspot_zones_*_v010_summary.json",
    ])


def _latest_zone_csv() -> Optional[Path]:
    return _latest_any([
        "data/grid/hotspots/grid_hotspot_zones_*_v012.csv",
        "data/grid/hotspots/grid_hotspot_zones_*_v011.csv",
        "data/grid/hotspots/grid_hotspot_zones_*_v010.csv",
    ])


@router.get("/hotspots/zones/latest")
def grid_hotspot_zones_latest() -> dict[str, Any]:
    path = _latest_zone_summary()
    if path is None:
        raise HTTPException(status_code=404, detail="No hotspot zones summary found")

    data = _read_json(path)
    data["served_from"] = str(path)
    return _jsonable(data)


# ---------------------------------------------------------------------
# HOTFIX: robust latest helper for grid hotspot zones
# Added to ensure older endpoint definitions can resolve _latest_any.
# ---------------------------------------------------------------------
def _latest_any(patterns: list[str]) -> Optional[Path]:
    for pattern in patterns:
        files = sorted(Path(".").glob(pattern))
        if files:
            return files[-1]
    return None


def _latest_zone_summary() -> Optional[Path]:
    return _latest_any([
        "data/grid/hotspots/grid_hotspot_zones_*_v012_summary.json",
        "data/grid/hotspots/grid_hotspot_zones_*_v011_summary.json",
        "data/grid/hotspots/grid_hotspot_zones_*_v010_summary.json",
    ])


def _latest_zone_csv() -> Optional[Path]:
    return _latest_any([
        "data/grid/hotspots/grid_hotspot_zones_*_v012.csv",
        "data/grid/hotspots/grid_hotspot_zones_*_v011.csv",
        "data/grid/hotspots/grid_hotspot_zones_*_v010.csv",
    ])


@router.get("/hotspots/zones/geojson")
def grid_hotspot_zones_geojson():
    patterns = [
        "data/grid/hotspots/grid_hotspot_zones_*_v012.geojson",
        "data/grid/hotspots/grid_hotspot_zones_*_v011.geojson",
        "data/grid/hotspots/grid_hotspot_zones_*_v010.geojson",
    ]

    selected = None
    for pattern in patterns:
        files = sorted(Path(".").glob(pattern))
        if files:
            selected = files[-1]
            break

    if selected is None:
        raise HTTPException(status_code=404, detail="No hotspot zones GeoJSON found")

    return FileResponse(
        selected,
        media_type="application/geo+json",
        filename=selected.name,
    )


@router.get("/hotspots/zones/cells/geojson")
def grid_hotspot_zone_cells_geojson():
    patterns = [
        "data/grid/hotspots/grid_hotspot_zone_cells_*_v012.geojson",
    ]

    selected = None
    for pattern in patterns:
        files = sorted(Path(".").glob(pattern))
        if files:
            selected = files[-1]
            break

    if selected is None:
        raise HTTPException(status_code=404, detail="No hotspot zone cells GeoJSON found")

    return FileResponse(
        selected,
        media_type="application/geo+json",
        filename=selected.name,
    )


@router.get("/hotspots/zones/cells/geojson")
def grid_hotspot_zone_cells_geojson():
    patterns = [
        "data/grid/hotspots/grid_hotspot_zone_cells_*_v012.geojson",
    ]

    selected = None
    for pattern in patterns:
        files = sorted(Path(".").glob(pattern))
        if files:
            selected = files[-1]
            break

    if selected is None:
        raise HTTPException(status_code=404, detail="No hotspot zone cells GeoJSON found")

    return FileResponse(
        selected,
        media_type="application/geo+json",
        filename=selected.name,
    )


def _public_depth_label(depth_mean_m: float | None) -> str:
    if depth_mean_m is None:
        return "kedalaman belum terbaca lengkap"

    try:
        d = float(depth_mean_m)
    except Exception:
        return "kedalaman belum terbaca lengkap"

    if d < 50:
        return "perairan dangkal pesisir"
    if d < 200:
        return "paparan benua/shelf"
    if d < 1000:
        return "koridor lereng laut"
    if d < 3000:
        return "laut dalam awal"
    return "laut sangat dalam"


def _zone_level_public_label(zone_level: str | None) -> str:
    mapping = {
        "operational_core_zone": "zona inti operasional",
        "operational_strong_zone": "zona operasional kuat",
        "operational_watch_zone": "zona pantauan operasional",
        "core_zone": "zona inti",
        "strong_zone": "zona kuat",
        "watch_zone": "zona pantauan",
        "candidate_zone": "zona kandidat",
    }
    return mapping.get(str(zone_level), "zona pemantauan")


@router.get("/brief/public/today")
def grid_brief_public_today() -> dict[str, Any]:
    scoring_path = _latest("data/grid/daily/grid_scoring_*_calibrated_v011_summary.json")
    hotspot_path = _latest("data/grid/hotspots/grid_hotspot_????-??-??_v010_summary.json")

    zone_path = None
    for pattern in [
        "data/grid/hotspots/grid_hotspot_zones_*_v012_summary.json",
        "data/grid/hotspots/grid_hotspot_zones_*_v011_summary.json",
        "data/grid/hotspots/grid_hotspot_zones_*_v010_summary.json",
    ]:
        files = sorted(Path(".").glob(pattern))
        if files:
            zone_path = files[-1]
            break

    if zone_path is None:
        raise HTTPException(status_code=404, detail="No hotspot zones summary found")

    scoring = _read_json(scoring_path) if scoring_path else {}
    hotspot = _read_json(hotspot_path) if hotspot_path else {}
    zones = _read_json(zone_path)

    date = zones.get("date") or hotspot.get("date") or scoring.get("date")
    top_zones = zones.get("top_zones", []) or []
    zone_counts = zones.get("zone_level_counts", {}) or {}
    hotspot_counts = hotspot.get("hotspot_class_counts", {}) or {}
    coverage = scoring.get("coverage", {}) or {}
    safety_counts = scoring.get("safety_label_counts_v011", {}) or {}

    if top_zones:
        z = top_zones[0]
        depth_label = _public_depth_label(z.get("depth_mean_m"))
        zone_label = _zone_level_public_label(z.get("zone_level"))

        public_reading = (
            f"NELAYA-AI mendeteksi {zones.get('zones_count', len(top_zones))} zona hotspot operasional harian. "
            f"Zona utama merupakan {zone_label} di sekitar {z.get('lon_center')} BT dan {z.get('lat_center')} LU. "
            f"Zona ini tersusun dari {z.get('cell_count')} grid cell, seluruhnya berada pada status keselamatan favorable, "
            f"dengan skor operasional rata-rata {z.get('mean_operational_score')}, confidence rata-rata "
            f"{z.get('mean_overall_confidence')}, dan berada pada {depth_label}."
        )
    else:
        public_reading = (
            "NELAYA-AI belum mendeteksi zona hotspot operasional yang cukup kuat untuk hari ini."
        )

    interpretation = (
        "Bacaan ini menunjukkan klaster kesesuaian operasional berbasis grid cell, bukan kepastian keberadaan ikan "
        "dan bukan estimasi biomassa. Informasi perlu dipadukan dengan keselamatan melaut, pengalaman nelayan, "
        "dan validasi lapangan."
    )

    cautions = []

    unknown_safety = safety_counts.get("unknown", 0)
    if unknown_safety:
        cautions.append(
            f"Sebagian grid masih memiliki data keselamatan belum lengkap: {unknown_safety} cell berstatus safety unknown."
        )

    chl_cov = None
    if isinstance(coverage.get("chl"), dict):
        chl_cov = coverage["chl"].get("coverage_pct")

    if chl_cov is not None and chl_cov < 30:
        cautions.append(
            f"Cakupan CHL hari ini masih rendah sekitar {chl_cov}%, sehingga pembacaan produktivitas perlu hati-hati."
        )

    cautions.append(
        "Zona hotspot operasional ini adalah sinyal probabilistik berbasis data oseanografi, bukan rekomendasi tunggal untuk melaut."
    )

    return _jsonable({
        "module": "nelaya_ai_grid_public_brief",
        "version": "0.1.1-public-language",
        "date": date,
        "status_label": "hotspot_detected" if top_zones else "no_strong_hotspot",
        "public_reading": public_reading,
        "interpretation": interpretation,
        "zone_counts": zone_counts,
        "hotspot_counts": hotspot_counts,
        "zones_count": zones.get("zones_count"),
        "top_zones": top_zones[:3],
        "cautions": cautions,
        "served_from": {
            "scoring": str(scoring_path) if scoring_path else None,
            "hotspot": str(hotspot_path) if hotspot_path else None,
            "zones": str(zone_path),
        },
        "scientific_note": (
            "Public language brief for NELAYA-AI grid hotspot operational nucleus. "
            "This is not biomass estimation and must be validated with field data."
        ),
    })


@router.get("/manifest/today")
def grid_manifest_today() -> dict[str, Any]:
    files = sorted(Path(".").glob("data/grid/grid_run_manifest_*.json"))
    if not files:
        raise HTTPException(status_code=404, detail="No grid run manifest found")

    path = files[-1]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["served_from"] = str(path)
    return _jsonable(data)


@router.get("/source-audit/today")
def grid_source_audit_today() -> dict[str, Any]:
    files = sorted(Path(".").glob("data/grid/grid_source_audit_*.json"))
    if not files:
        raise HTTPException(status_code=404, detail="No grid source audit found")

    path = files[-1]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["served_from"] = str(path)
    return _jsonable(data)


@router.get("/persistence/public/today")
def grid_persistence_public_today(window: int = 7) -> dict[str, Any]:
    files = sorted(Path(".").glob(f"data/grid/persistence/grid_hotspot_persistence_*_w{window}_v010_summary.json"))
    if not files:
        raise HTTPException(status_code=404, detail=f"No persistence summary found for window {window}")

    path = files[-1]
    data = json.loads(path.read_text(encoding="utf-8"))

    days_available = int(data.get("days_available") or 0)
    unique_cells = int(data.get("unique_cells") or 0)
    counts = data.get("persistence_label_counts", {}) or {}

    if days_available < 3:
        status_label = "insufficient_history"
        public_reading = (
            f"Riwayat hotspot baru tersedia {days_available} hari dalam jendela {window} hari. "
            f"Sistem mencatat {unique_cells} grid cell sebagai sinyal awal, tetapi belum cukup untuk disebut hotspot menetap."
        )
    elif counts.get("persistent_hotspot", 0) > 0:
        status_label = "persistent_hotspot_detected"
        public_reading = (
            f"NELAYA-AI mendeteksi {counts.get('persistent_hotspot', 0)} grid cell dengan pola hotspot menetap "
            f"dalam jendela {window} hari."
        )
    elif counts.get("recurrent_hotspot", 0) > 0:
        status_label = "recurrent_hotspot_detected"
        public_reading = (
            f"NELAYA-AI mendeteksi {counts.get('recurrent_hotspot', 0)} grid cell yang berulang muncul "
            f"sebagai hotspot dalam jendela {window} hari."
        )
    elif counts.get("emerging_hotspot", 0) > 0:
        status_label = "emerging_hotspot_detected"
        public_reading = (
            f"NELAYA-AI mendeteksi {counts.get('emerging_hotspot', 0)} grid cell dengan sinyal hotspot mulai muncul "
            f"dalam jendela {window} hari."
        )
    else:
        status_label = "no_persistent_signal"
        public_reading = (
            f"Belum ada pola hotspot menetap dalam jendela {window} hari."
        )

    return _jsonable({
        "module": "nelaya_ai_hotspot_persistence_public_brief",
        "version": "0.1.0-public",
        "target_date": data.get("target_date"),
        "window_days": window,
        "status_label": status_label,
        "public_reading": public_reading,
        "days_available": days_available,
        "unique_cells": unique_cells,
        "persistence_label_counts": counts,
        "quality_note": data.get("quality_note"),
        "top_cells": data.get("top_cells", [])[:5],
        "served_from": str(path),
        "scientific_note": (
            "Persistence shows repeated appearance of operational hotspot cells across available daily outputs. "
            "It is not biomass persistence."
        ),
    })


@router.get("/persistence/public/today")
def grid_persistence_public_today(window: int = 7) -> dict[str, Any]:
    files = sorted(Path(".").glob(f"data/grid/persistence/grid_hotspot_persistence_*_w{window}_v010_summary.json"))
    if not files:
        raise HTTPException(status_code=404, detail=f"No persistence summary found for window {window}")

    path = files[-1]
    data = json.loads(path.read_text(encoding="utf-8"))

    days_available = int(data.get("days_available") or 0)
    unique_cells = int(data.get("unique_cells") or 0)
    counts = data.get("persistence_label_counts", {}) or {}

    if days_available < 3:
        status_label = "insufficient_history"
        public_reading = (
            f"Riwayat hotspot baru tersedia {days_available} hari dalam jendela {window} hari. "
            f"Sistem mencatat {unique_cells} grid cell sebagai sinyal awal, tetapi belum cukup untuk disebut hotspot menetap."
        )
    elif counts.get("persistent_hotspot", 0) > 0:
        status_label = "persistent_hotspot_detected"
        public_reading = (
            f"NELAYA-AI mendeteksi {counts.get('persistent_hotspot', 0)} grid cell dengan pola hotspot menetap "
            f"dalam jendela {window} hari."
        )
    elif counts.get("recurrent_hotspot", 0) > 0:
        status_label = "recurrent_hotspot_detected"
        public_reading = (
            f"NELAYA-AI mendeteksi {counts.get('recurrent_hotspot', 0)} grid cell yang berulang muncul "
            f"sebagai hotspot dalam jendela {window} hari."
        )
    elif counts.get("emerging_hotspot", 0) > 0:
        status_label = "emerging_hotspot_detected"
        public_reading = (
            f"NELAYA-AI mendeteksi {counts.get('emerging_hotspot', 0)} grid cell dengan sinyal hotspot mulai muncul "
            f"dalam jendela {window} hari."
        )
    else:
        status_label = "no_persistent_signal"
        public_reading = (
            f"Belum ada pola hotspot menetap dalam jendela {window} hari."
        )

    return _jsonable({
        "module": "nelaya_ai_hotspot_persistence_public_brief",
        "version": "0.1.0-public",
        "target_date": data.get("target_date"),
        "window_days": window,
        "status_label": status_label,
        "public_reading": public_reading,
        "days_available": days_available,
        "unique_cells": unique_cells,
        "persistence_label_counts": counts,
        "quality_note": data.get("quality_note"),
        "top_cells": data.get("top_cells", [])[:5],
        "served_from": str(path),
        "scientific_note": (
            "Persistence shows repeated appearance of operational hotspot cells across available daily outputs. "
            "It is not biomass persistence."
        ),
    })


@router.get("/dashboard/today")
def grid_dashboard_today() -> dict[str, Any]:
    """
    One-stop dashboard summary for NELAYA-AI Grid Hotspot Intelligence.
    This endpoint is designed for frontend cards and map layer control.
    """

    def latest_file(pattern: str) -> Path | None:
        files = sorted(Path(".").glob(pattern))
        return files[-1] if files else None

    def latest_any(patterns: list[str]) -> Path | None:
        for pattern in patterns:
            path = latest_file(pattern)
            if path is not None:
                return path
        return None

    def read_json_safe(path: Path | None) -> dict[str, Any] | None:
        if path is None:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def persistence_public_from_summary(window: int) -> dict[str, Any] | None:
        p = latest_file(f"data/grid/persistence/grid_hotspot_persistence_*_w{window}_v010_summary.json")
        data = read_json_safe(p)
        if not data:
            return None

        days_available = int(data.get("days_available") or 0)
        unique_cells = int(data.get("unique_cells") or 0)
        counts = data.get("persistence_label_counts", {}) or {}

        if days_available < 3:
            status_label = "insufficient_history"
            public_reading = (
                f"Riwayat hotspot baru tersedia {days_available} hari dalam jendela {window} hari. "
                f"Sistem mencatat {unique_cells} grid cell sebagai sinyal awal, tetapi belum cukup "
                f"untuk disebut hotspot menetap."
            )
        elif counts.get("persistent_hotspot", 0) > 0:
            status_label = "persistent_hotspot_detected"
            public_reading = (
                f"NELAYA-AI mendeteksi {counts.get('persistent_hotspot', 0)} grid cell dengan pola "
                f"hotspot menetap dalam jendela {window} hari."
            )
        elif counts.get("recurrent_hotspot", 0) > 0:
            status_label = "recurrent_hotspot_detected"
            public_reading = (
                f"NELAYA-AI mendeteksi {counts.get('recurrent_hotspot', 0)} grid cell yang berulang "
                f"muncul sebagai hotspot dalam jendela {window} hari."
            )
        elif counts.get("emerging_hotspot", 0) > 0:
            status_label = "emerging_hotspot_detected"
            public_reading = (
                f"NELAYA-AI mendeteksi {counts.get('emerging_hotspot', 0)} grid cell dengan sinyal "
                f"hotspot mulai muncul dalam jendela {window} hari."
            )
        else:
            status_label = "no_persistent_signal"
            public_reading = f"Belum ada pola hotspot menetap dalam jendela {window} hari."

        return {
            "window_days": window,
            "status_label": status_label,
            "public_reading": public_reading,
            "days_available": days_available,
            "unique_cells": unique_cells,
            "persistence_label_counts": counts,
            "quality_note": data.get("quality_note"),
            "top_cells": (data.get("top_cells") or [])[:5],
            "served_from": str(p) if p else None,
        }

    # Core files
    scoring_path = latest_file("data/grid/daily/grid_scoring_*_calibrated_v011_summary.json")
    hotspot_path = latest_file("data/grid/hotspots/grid_hotspot_????-??-??_v010_summary.json")
    zone_path = latest_any([
        "data/grid/hotspots/grid_hotspot_zones_*_v012_summary.json",
        "data/grid/hotspots/grid_hotspot_zones_*_v011_summary.json",
        "data/grid/hotspots/grid_hotspot_zones_*_v010_summary.json",
    ])
    manifest_path = latest_file("data/grid/grid_run_manifest_*.json")
    source_audit_path = latest_file("data/grid/grid_source_audit_*.json")

    scoring = read_json_safe(scoring_path) or {}
    hotspot = read_json_safe(hotspot_path) or {}
    zones = read_json_safe(zone_path) or {}
    manifest = read_json_safe(manifest_path) or {}
    source_audit = read_json_safe(source_audit_path) or {}

    # Date priority: zones > manifest > hotspot > scoring
    date = (
        zones.get("date")
        or manifest.get("date")
        or hotspot.get("date")
        or scoring.get("date")
    )

    top_zones = zones.get("top_zones", []) or []
    zone_counts = zones.get("zone_level_counts", {}) or {}
    zones_count = zones.get("zones_count", 0) or 0

    # Public reading from current public brief logic, reconstructed here for one-call dashboard.
    if top_zones:
        z = top_zones[0]
        depth_label = _public_depth_label(z.get("depth_mean_m"))
        zone_label = _zone_level_public_label(z.get("zone_level"))
        public_reading = (
            f"NELAYA-AI mendeteksi {zones_count} zona hotspot operasional harian. "
            f"Zona utama merupakan {zone_label} di sekitar {z.get('lon_center')} BT dan {z.get('lat_center')} LU. "
            f"Zona ini tersusun dari {z.get('cell_count')} grid cell, seluruhnya berada pada status keselamatan favorable, "
            f"dengan skor operasional rata-rata {z.get('mean_operational_score')}, confidence rata-rata "
            f"{z.get('mean_overall_confidence')}, dan berada pada {depth_label}."
        )
        hotspot_status = "hotspot_detected"
    else:
        public_reading = "NELAYA-AI belum mendeteksi zona hotspot operasional yang cukup kuat untuk hari ini."
        hotspot_status = "no_strong_hotspot"

    quality_label = manifest.get("quality_label")
    quality_flags = manifest.get("quality_flags", []) or []
    public_quality_note = manifest.get("public_quality_note")

    source_status_counts = source_audit.get("source_status_counts", {}) or {}
    fallback_count = int(source_status_counts.get("fallback_or_mismatch", 0) or 0)

    persistence = {
        "w7": persistence_public_from_summary(7),
        "w14": persistence_public_from_summary(14),
        "w30": persistence_public_from_summary(30),
    }

    # Compact card status for frontend.
    if quality_label == "usable":
        dashboard_level = "normal"
    elif quality_label == "usable_with_caution":
        dashboard_level = "caution"
    elif quality_label == "usable_with_strong_caution":
        dashboard_level = "strong_caution"
    else:
        dashboard_level = "unknown"

    headline_parts = []
    if zones_count:
        headline_parts.append(f"{zones_count} zona hotspot operasional")
    else:
        headline_parts.append("belum ada zona hotspot kuat")

    if quality_label:
        headline_parts.append(f"mutu data: {quality_label}")

    if persistence["w7"]:
        headline_parts.append(f"persistence W7: {persistence['w7']['status_label']}")

    dashboard_headline = " | ".join(headline_parts)

    map_layers = {
        "zone_polygon_geojson": "/api/v1/grid/hotspots/zones/geojson",
        "zone_cells_geojson": "/api/v1/grid/hotspots/zones/cells/geojson",
        "persistence_w7_geojson": "/api/v1/grid/persistence/geojson?window=7",
        "persistence_w14_geojson": "/api/v1/grid/persistence/geojson?window=14",
        "persistence_w30_geojson": "/api/v1/grid/persistence/geojson?window=30",
    }

    related_endpoints = {
        "health": "/api/v1/grid/health",
        "public_brief": "/api/v1/grid/brief/public/today",
        "manifest": "/api/v1/grid/manifest/today",
        "source_audit": "/api/v1/grid/source-audit/today",
        "zones": "/api/v1/grid/hotspots/zones/today",
        "persistence_public_w7": "/api/v1/grid/persistence/public/today?window=7",
        "persistence_public_w14": "/api/v1/grid/persistence/public/today?window=14",
        "persistence_public_w30": "/api/v1/grid/persistence/public/today?window=30",
    }

    cautions = []

    if public_quality_note:
        cautions.append(public_quality_note)

    if fallback_count:
        cautions.append(
            f"Terdapat {fallback_count} sumber data yang memakai fallback atau tanggal tidak persis sama dengan tanggal target."
        )

    if persistence["w7"] and persistence["w7"]["status_label"] == "insufficient_history":
        cautions.append(
            "Riwayat hotspot belum cukup untuk membaca pola menetap. Persistence masih sinyal awal."
        )

    cautions.append(
        "Semua bacaan grid hotspot adalah sinyal kesesuaian operasional berbasis data oseanografi, bukan estimasi biomassa ikan."
    )

    return _jsonable({
        "module": "nelaya_ai_grid_dashboard_summary",
        "version": "0.1.0-dashboard",
        "date": date,
        "dashboard_level": dashboard_level,
        "dashboard_headline": dashboard_headline,
        "hotspot_status": hotspot_status,
        "public_reading": public_reading,
        "quality": {
            "quality_label": quality_label,
            "quality_flags": quality_flags,
            "public_quality_note": public_quality_note,
        },
        "source_audit": {
            "source_status_counts": source_status_counts,
            "sources": source_audit.get("sources", {}),
        },
        "zones": {
            "zones_count": zones_count,
            "zone_level_counts": zone_counts,
            "top_zones": top_zones[:5],
        },
        "persistence": persistence,
        "map_layers": map_layers,
        "related_endpoints": related_endpoints,
        "cautions": cautions,
        "served_from": {
            "scoring": str(scoring_path) if scoring_path else None,
            "hotspot": str(hotspot_path) if hotspot_path else None,
            "zones": str(zone_path) if zone_path else None,
            "manifest": str(manifest_path) if manifest_path else None,
            "source_audit": str(source_audit_path) if source_audit_path else None,
        },
        "scientific_note": (
            "Dashboard summary combines public brief, operational hotspot zones, data quality manifest, "
            "source-date audit, and hotspot persistence. Outputs are operational suitability signals, "
            "not biomass estimates."
        ),
    })
