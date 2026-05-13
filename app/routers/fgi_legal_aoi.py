from pathlib import Path
import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix="/api/v1/fgi/legal-aoi",
    tags=["FGI Legal AOI"],
)

ROOT = Path(__file__).resolve().parents[2]

SUMMARY_FILE = ROOT / "data/fgi/legal_zone_aoi_today.json"
GEOJSON_FILE = ROOT / "data/fgi/species_grid_legal_aoi_today.geojson"


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "message": "FGI Legal AOI belum tersedia.",
                "hint": "Jalankan: python scripts/build_fgi_legal_aoi_guardrail.py",
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
                "message": "Gagal membaca FGI Legal AOI.",
                "error": str(exc),
                "path": str(path),
            },
        )


@router.get("/today")
def get_fgi_legal_aoi_summary_today():
    return read_json(SUMMARY_FILE)


@router.get("/geojson")
def get_fgi_legal_aoi_geojson():
    return read_json(GEOJSON_FILE)
