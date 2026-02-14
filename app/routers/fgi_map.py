from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException

router = APIRouter(prefix="/api/v1/fgi/map", tags=["FGI Map"])

@router.get("/ping")
def ping():
    return {"ok": True, "service": "fgi_map"}

@router.get("/latest")
def latest(trace: str | None = Query(default=None)):
    # Placeholder: nanti return metadata map terbaru (date, bounds, url tiles/json)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace": trace,
        "note": "FGI map not configured yet",
    }

@router.get("/by-date")
def by_date(date: str = Query(...), trace: str | None = Query(default=None)):
    # Placeholder
    raise HTTPException(status_code=501, detail=f"FGI map for date={date} not configured yet (trace={trace})")
