from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/fgi/map", tags=["FGI Map"])

ROOT = Path(__file__).resolve().parents[2]
MAPDIR = ROOT / "data" / "fgi_map"
LATEST = MAPDIR / "latest.geojson"

@router.get("/ping")
def ping():
    return {"ok": True, "service": "fgi_map"}

@router.get("/latest")
def latest():
    if not LATEST.exists():
        raise HTTPException(status_code=501, detail="FGI map not configured yet. Run: python scripts/daily_fgi.py && python -m app.jobs.build_fgi_map_daily")
    return JSONResponse(content=json.loads(LATEST.read_text(encoding="utf-8")))

@router.get("/by-date")
def by_date(date: str = Query(..., description="YYYY-MM-DD (UTC/as_of)")):
    p = MAPDIR / f"fgi_map_{date}.geojson"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"FGI map not found: {p.name}")
    return JSONResponse(content=json.loads(p.read_text(encoding="utf-8")))
