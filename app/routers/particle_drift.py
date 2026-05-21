from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response


router = APIRouter(
    prefix="/api/v1/physics/particle-drift",
    tags=["physics", "particle-drift", "lagrangian"],
)


DRIFT_JSON_PATH = Path("data/physics/particle_drift_today.json")
DRIFT_GEOJSON_PATH = Path("data/physics/particle_drift_today.geojson")
DRIFT_IMAGE_PATH = Path("data/physics/particle_drift_today.png")


def read_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"File not found: {path}",
                "hint": "Run scripts/build_particle_drift_beta.py first.",
            },
        )

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Failed to read JSON file: {path}",
                "error": str(exc),
            },
        )


@router.get("/today")
def get_particle_drift_today() -> Dict[str, Any]:
    data = read_json_file(DRIFT_JSON_PATH)
    data.setdefault(
        "api_note",
        "Particle Drift Beta is diagnostic and should not be interpreted as deterministic fish-location prediction.",
    )
    return data


@router.get("/summary")
def get_particle_drift_summary() -> Dict[str, Any]:
    data = read_json_file(DRIFT_JSON_PATH)

    return {
        "version": data.get("version"),
        "product": data.get("product"),
        "date": data.get("date"),
        "method": data.get("method"),
        "settings": data.get("settings", {}),
        "summary": data.get("summary", {}),
        "first_hotspot": (data.get("retention_hotspots") or [None])[0],
        "first_track": (data.get("sample_tracks") or [None])[0],
        "scientific_caution": data.get("scientific_caution"),
    }


@router.get("/geojson")
def get_particle_drift_geojson() -> JSONResponse:
    data = read_json_file(DRIFT_GEOJSON_PATH)
    return JSONResponse(content=data)


@router.get("/image")
def get_particle_drift_image():
    if not DRIFT_IMAGE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"File not found: {DRIFT_IMAGE_PATH}",
                "hint": "Run scripts/build_particle_drift_beta.py first.",
            },
        )

    return FileResponse(
        DRIFT_IMAGE_PATH,
        media_type="image/png",
        filename="particle_drift_today.png",
    )


@router.head("/image")
def head_particle_drift_image():
    if not DRIFT_IMAGE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"File not found: {DRIFT_IMAGE_PATH}",
                "hint": "Run scripts/build_particle_drift_beta.py first.",
            },
        )

    return Response(
        status_code=200,
        media_type="image/png",
        headers={
            "content-length": str(DRIFT_IMAGE_PATH.stat().st_size),
            "cache-control": "no-store",
        },
    )
