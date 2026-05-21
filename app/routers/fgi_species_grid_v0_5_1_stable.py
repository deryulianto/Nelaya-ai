from pathlib import Path
import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix="/api/v1/fgi/species-grid",
    tags=["FGI Species Grid"],
)

ROOT = Path(__file__).resolve().parents[2]

SUMMARY_FILE = ROOT / "data/fgi/species_grid_today.json"
GEOJSON_FILE = ROOT / "data/fgi/species_grid_today.geojson"


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "message": "FGI Species Grid belum tersedia.",
                "hint": "Jalankan: python scripts/build_fgi_species_grid.py",
                "path": str(path),
            },
        )

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Gagal membaca FGI Species Grid.",
                "error": str(exc),
                "path": str(path),
            },
        )


@router.get("/today")
def get_fgi_species_grid_summary_today():
    return read_json(SUMMARY_FILE)


@router.get("/geojson")
def get_fgi_species_grid_geojson():
    return read_json(GEOJSON_FILE)
