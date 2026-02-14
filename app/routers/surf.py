from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/surf", tags=["Surf"])

@router.get("/ping")
def ping():
    return {"ok": True, "service": "surf"}

@router.get("/forecast")
def forecast(
    spot: str | None = Query(default=None),
    days: int = Query(default=3, ge=1, le=10),
    trace: str | None = Query(default=None),
):
    return {
        "spot": spot,
        "days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace": trace,
        "note": "Surf forecast not configured yet",
        "data": [],
    }
