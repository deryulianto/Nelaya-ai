from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/waves", tags=["Waves"])

@router.get("/ping")
def ping():
    return {"ok": True, "service": "waves"}

@router.get("/forecast")
def forecast(
    spot: str | None = Query(default=None, description="Optional spot name/id"),
    days: int = Query(default=3, ge=1, le=10),
    trace: str | None = Query(default=None),
):
    # Placeholder: nanti kita sambungkan ke pipeline/produk ombak (Copernicus/NOAA) atau file cache json
    return {
        "spot": spot,
        "days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace": trace,
        "note": "Wave forecast not configured yet",
        "data": [],
    }
