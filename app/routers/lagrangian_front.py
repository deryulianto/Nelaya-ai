from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse


router = APIRouter(
    prefix="/api/v1/physics/lagrangian-front",
    tags=["physics", "lagrangian-front"],
)


LFI_JSON_PATH = Path("data/physics/lagrangian_front_today.json")
LFI_GEOJSON_PATH = Path("data/physics/lagrangian_front_today.geojson")
LFI_IMAGE_PATH = Path("data/physics/lagrangian_front_today.png")


def read_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"File not found: {path}",
                "hint": "Run scripts/build_lagrangian_front_alpha.py first.",
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
def get_lagrangian_front_today() -> Dict[str, Any]:
    """
    Return today's LFI Alpha result.

    LFI Alpha is an indicative surface-current front proxy based on:
    - current convergence
    - current shear
    - current speed gradient
    - current vorticity

    It is not yet full FTLE/LCS particle tracking.
    """
    data = read_json_file(LFI_JSON_PATH)

    data.setdefault(
        "api_note",
        "LFI Alpha is indicative and should not be interpreted as a deterministic fish-location prediction.",
    )

    return data


@router.get("/summary")
def get_lagrangian_front_summary() -> Dict[str, Any]:
    """
    Lightweight summary endpoint for dashboard cards.
    """
    data = read_json_file(LFI_JSON_PATH)

    return {
        "version": data.get("version"),
        "product": data.get("product"),
        "date": data.get("date"),
        "method": data.get("method"),
        "summary": data.get("summary", {}),
        "first_zone": (data.get("top_zones") or [None])[0],
        "scientific_caution": data.get("scientific_caution"),
    }


@router.get("/geojson")
def get_lagrangian_front_geojson() -> JSONResponse:
    """
    Return LFI top zones as GeoJSON.
    """
    data = read_json_file(LFI_GEOJSON_PATH)
    return JSONResponse(content=data)

@router.get("/image")
def get_lagrangian_front_image():
    """
    Return LFI Alpha visualization as PNG.
    """
    if not LFI_IMAGE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"File not found: {LFI_IMAGE_PATH}",
                "hint": "Run scripts/plot_lagrangian_front_alpha.py first.",
            },
        )

    return FileResponse(
        LFI_IMAGE_PATH,
        media_type="image/png",
        filename="lagrangian_front_today.png",
    )

