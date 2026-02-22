from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
LATEST = ROOT / "data" / "fgi_map_grid" / "latest.geojson"

router = APIRouter(prefix="/api/v1/fgi/map-grid", tags=["FGI Map Grid"])

@router.get("/latest")
def latest():
    if not LATEST.exists():
        raise HTTPException(status_code=404, detail="grid map not found (run build_fgi_grid_map_daily)")
    return json.loads(LATEST.read_text(encoding="utf-8"))
