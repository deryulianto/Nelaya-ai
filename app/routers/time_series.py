from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/time-series", tags=["Time Series"])

@router.get("/ping")
def ping():
    return {"ok": True, "service": "time_series"}

@router.get("/summary")
def summary(
    metric: str | None = Query(default=None, description="sst/chl/current/etc"),
    area: str | None = Query(default=None),
    trace: str | None = Query(default=None),
):
    return {
        "metric": metric,
        "area": area,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace": trace,
        "note": "Time-series service not configured yet",
        "data": [],
    }
