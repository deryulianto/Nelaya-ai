# app/routers/fgi_physics_support.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse


router = APIRouter(
    prefix="/fgi/physics-support",
    tags=["FGI Physics Support"],
)

LAB_ROOT = Path(os.getenv("NELAYA_AI_LAB_ROOT", ".")).resolve()
DATA_ROOT = Path(os.getenv("NELAYA_AI_DATA_ROOT", LAB_ROOT / "data")).resolve()

PHYSICS_DIR = DATA_ROOT / "physics"
SUMMARY_FILE = PHYSICS_DIR / "fgi_physics_support_today.json"
GEOJSON_FILE = PHYSICS_DIR / "fgi_physics_support_preview.geojson"

DEFAULT_METRIC = "fgi_physics_support_confidence_adjusted"

ALLOWED_TOP_CELL_METRICS = {
    "fgi_physics_support_score",
    "fgi_physics_support_confidence_adjusted",
    "dynamic_structure_score",
    "topographic_structure_score",
}


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "file_not_found",
                "file": str(path),
                "hint": (
                    "Run: python scripts/build_physics_informed_fgi_v06.py "
                    "--species-group medium_pelagic --threshold 0.22"
                ),
            },
        )

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "json_read_failed",
                "file": str(path),
                "message": str(exc),
            },
        )


def scientific_caution() -> str:
    return (
        "FGI Physics Support adalah lapisan pendukung berbasis fisika laut, "
        "bukan prediksi langsung jumlah ikan atau hasil tangkapan. Layer ini "
        "menggabungkan bathymetry, shelf-break, front, arus, convergence, "
        "vorticity, wave/wind support, dan confidence data. Validasi lapangan "
        "tetap diperlukan."
    )


def compact_status(data: Dict[str, Any]) -> Dict[str, Any]:
    geojson = data.get("outputs", {}).get("geojson", {})

    return {
        "module": data.get("module"),
        "version": data.get("version"),
        "status": data.get("status"),
        "region": data.get("region"),
        "species_group": data.get("species_group"),
        "geojson_created": geojson.get("created"),
        "geojson_point_count": geojson.get("point_count"),
        "summary_file_exists": SUMMARY_FILE.exists(),
        "geojson_file_exists": GEOJSON_FILE.exists(),
    }


def get_top_cells(
    data: Dict[str, Any],
    metric: str = DEFAULT_METRIC,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    rows = data.get("top_cells", {}).get(metric, [])
    if not isinstance(rows, list):
        return []
    return rows[: max(1, min(limit, 100))]


@router.get("/health")
def health() -> Dict[str, Any]:
    data = read_json(SUMMARY_FILE) if SUMMARY_FILE.exists() else {}

    return {
        "api": "fgi_physics_support_health",
        "ok": bool(SUMMARY_FILE.exists() and GEOJSON_FILE.exists()),
        "summary_file": str(SUMMARY_FILE),
        "summary_file_exists": SUMMARY_FILE.exists(),
        "geojson_file": str(GEOJSON_FILE),
        "geojson_file_exists": GEOJSON_FILE.exists(),
        "status": compact_status(data) if data else None,
    }


@router.get("/summary")
def summary() -> Dict[str, Any]:
    data = read_json(SUMMARY_FILE)
    top = get_top_cells(data, metric=DEFAULT_METRIC, limit=1)
    best_cell = top[0] if top else None

    return {
        "api": "fgi_physics_support_summary",
        "status": compact_status(data),
        "summary_metrics": data.get("summary_metrics", {}),
        "best_cell": best_cell,
        "ui_message": (
            "Physics-informed FGI Support aktif. Sistem membaca struktur dasar laut, "
            "shelf-break, front permukaan, arus, convergence, vorticity, wave/wind, "
            "dan confidence untuk mendukung interpretasi FGI."
        ),
        "scientific_caution": scientific_caution(),
    }


@router.get("/today")
def today(
    include_top_cells: bool = Query(True),
    top_limit: int = Query(10, ge=1, le=100),
) -> Dict[str, Any]:
    data = read_json(SUMMARY_FILE)

    response: Dict[str, Any] = {
        "api": "fgi_physics_support_today",
        "status": compact_status(data),
        "summary_metrics": data.get("summary_metrics", {}),
        "stats": data.get("stats", {}),
        "weights": data.get("weights", {}),
        "grid": data.get("grid", {}),
        "outputs": data.get("outputs", {}),
        "interpretation": data.get("interpretation", {}),
        "scientific_caution": scientific_caution(),
    }

    if include_top_cells:
        response["top_cells"] = {
            DEFAULT_METRIC: get_top_cells(
                data,
                metric=DEFAULT_METRIC,
                limit=top_limit,
            )
        }

    return response


@router.get("/top-cells")
def top_cells(
    metric: str = Query(DEFAULT_METRIC),
    limit: int = Query(10, ge=1, le=100),
) -> Dict[str, Any]:
    if metric not in ALLOWED_TOP_CELL_METRICS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_metric",
                "metric": metric,
                "allowed_metrics": sorted(ALLOWED_TOP_CELL_METRICS),
            },
        )

    data = read_json(SUMMARY_FILE)
    rows = get_top_cells(data, metric=metric, limit=limit)

    return {
        "api": "fgi_physics_support_top_cells",
        "status": compact_status(data),
        "metric": metric,
        "limit": limit,
        "count": len(rows),
        "top_cells": rows,
        "scientific_caution": scientific_caution(),
    }


@router.get("/geojson")
def geojson() -> JSONResponse:
    if not GEOJSON_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "geojson_not_found",
                "file": str(GEOJSON_FILE),
                "hint": (
                    "Run: python scripts/build_physics_informed_fgi_v06.py "
                    "--species-group medium_pelagic --threshold 0.22"
                ),
            },
        )

    try:
        data = json.loads(GEOJSON_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "geojson_read_failed",
                "file": str(GEOJSON_FILE),
                "message": str(exc),
            },
        )

    return JSONResponse(content=data)
