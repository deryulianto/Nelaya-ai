# app/api/v1/fgi_physics_support.py
# -*- coding: utf-8 -*-

"""
NELAYA-AI FGI Physics Support API

Purpose:
- Expose Physics-informed FGI Support v0.6.x to frontend/API.
- Reads:
    data/physics/fgi_physics_support_today.json
    data/physics/fgi_physics_support_preview.geojson

Important:
- This endpoint does not replace the main FGI model.
- It exposes a physics-informed support layer:
  bathymetry + shelf-break + current/front/convergence/vorticity + confidence.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse


router = APIRouter()

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


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "file_not_found",
                "message": f"Required file not found: {path}",
                "hint": (
                    "Run scripts/build_physics_informed_fgi_v06.py first, "
                    "for example: python scripts/build_physics_informed_fgi_v06.py "
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
                "message": str(exc),
                "file": str(path),
            },
        )


def _compact_top_cells(
    data: Dict[str, Any],
    metric: str = DEFAULT_METRIC,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    top_cells = data.get("top_cells", {})
    rows = top_cells.get(metric, [])

    if not isinstance(rows, list):
        return []

    return rows[: max(1, min(limit, 100))]


def _scientific_caution() -> str:
    return (
        "FGI Physics Support is a physics-informed support layer, not a direct "
        "fish abundance or catch prediction. It combines seabed structure, "
        "shelf-break information, current/front/convergence/vorticity diagnostics, "
        "and confidence metadata. Field validation and calibration remain required."
    )


def _api_status(data: Dict[str, Any]) -> Dict[str, Any]:
    outputs = data.get("outputs", {})
    geojson = outputs.get("geojson", {})

    return {
        "module": data.get("module", "nelaya_ai_physics_informed_fgi_support"),
        "version": data.get("version"),
        "status": data.get("status", "unknown"),
        "region": data.get("region"),
        "species_group": data.get("species_group"),
        "geojson_created": geojson.get("created"),
        "geojson_point_count": geojson.get("point_count"),
        "summary_file_exists": SUMMARY_FILE.exists(),
        "geojson_file_exists": GEOJSON_FILE.exists(),
    }


@router.get("/today")
def get_physics_support_today(
    include_top_cells: bool = Query(True, description="Include top ranked support cells."),
    top_limit: int = Query(10, ge=1, le=100, description="Maximum number of top cells."),
) -> Dict[str, Any]:
    """
    Full daily Physics-informed FGI Support summary.
    """

    data = _read_json(SUMMARY_FILE)

    response = {
        "api": "fgi_physics_support_today",
        "status": _api_status(data),
        "summary_metrics": data.get("summary_metrics", {}),
        "stats": data.get("stats", {}),
        "outputs": data.get("outputs", {}),
        "weights": data.get("weights", {}),
        "grid": data.get("grid", {}),
        "interpretation": data.get("interpretation", {}),
        "scientific_caution": _scientific_caution(),
    }

    if include_top_cells:
        response["top_cells"] = {
            DEFAULT_METRIC: _compact_top_cells(
                data,
                metric=DEFAULT_METRIC,
                limit=top_limit,
            )
        }

    return response


@router.get("/summary")
def get_physics_support_summary() -> Dict[str, Any]:
    """
    Lightweight summary for dashboard cards.
    """

    data = _read_json(SUMMARY_FILE)
    summary = data.get("summary_metrics", {})
    top = _compact_top_cells(data, metric=DEFAULT_METRIC, limit=1)

    best_cell: Optional[Dict[str, Any]] = top[0] if top else None

    return {
        "api": "fgi_physics_support_summary",
        "status": _api_status(data),
        "species_group": data.get("species_group"),
        "summary_metrics": summary,
        "best_cell": best_cell,
        "scientific_caution": _scientific_caution(),
        "ui_message": (
            "Physics-informed FGI support is active. The system reads "
            "bathymetry, shelf-break, daily ocean fronts, current, convergence, "
            "vorticity, and confidence to support FGI interpretation."
        ),
    }


@router.get("/top-cells")
def get_physics_support_top_cells(
    metric: str = Query(
        DEFAULT_METRIC,
        description="Metric key from top_cells.",
    ),
    limit: int = Query(10, ge=1, le=100),
) -> Dict[str, Any]:
    """
    Return top cells for a selected metric.
    """

    if metric not in ALLOWED_TOP_CELL_METRICS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_metric",
                "metric": metric,
                "allowed_metrics": sorted(ALLOWED_TOP_CELL_METRICS),
            },
        )

    data = _read_json(SUMMARY_FILE)
    rows = _compact_top_cells(data, metric=metric, limit=limit)

    return {
        "api": "fgi_physics_support_top_cells",
        "status": _api_status(data),
        "metric": metric,
        "limit": limit,
        "count": len(rows),
        "top_cells": rows,
        "scientific_caution": _scientific_caution(),
    }


@router.get("/geojson")
def get_physics_support_geojson() -> JSONResponse:
    """
    Return GeoJSON preview for map overlay.
    """

    if not GEOJSON_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "geojson_not_found",
                "message": f"GeoJSON file not found: {GEOJSON_FILE}",
                "hint": (
                    "Run scripts/build_physics_informed_fgi_v06.py with a threshold "
                    "low enough to generate points, e.g. --threshold 0.22"
                ),
            },
        )

    try:
        geojson = json.loads(GEOJSON_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "geojson_read_failed",
                "message": str(exc),
                "file": str(GEOJSON_FILE),
            },
        )

    return JSONResponse(content=geojson)


@router.get("/health")
def get_physics_support_health() -> Dict[str, Any]:
    """
    Health check for the Physics-informed FGI Support layer.
    """

    summary_exists = SUMMARY_FILE.exists()
    geojson_exists = GEOJSON_FILE.exists()

    data = _read_json(SUMMARY_FILE) if summary_exists else {}

    return {
        "api": "fgi_physics_support_health",
        "ok": bool(summary_exists and geojson_exists),
        "summary_file": str(SUMMARY_FILE),
        "summary_file_exists": summary_exists,
        "geojson_file": str(GEOJSON_FILE),
        "geojson_file_exists": geojson_exists,
        "status": _api_status(data) if data else None,
    }
