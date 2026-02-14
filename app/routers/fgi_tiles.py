from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/fgi/tiles", tags=["FGI Tiles"])

@router.get("/ping")
def ping():
    return {"ok": True, "service": "fgi_tiles"}

# Placeholder endpoint: nanti kita isi dengan tile generator / tile server
@router.get("/{z}/{x}/{y}.png")
def tile_png(z: int, x: int, y: int):
    raise HTTPException(status_code=501, detail="FGI tile service not configured yet")
