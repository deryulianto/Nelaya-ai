from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/ocean/memory", tags=["Ocean Memory"])

@router.get("/ping")
def ping():
    return {"ok": True, "service": "ocean_memory"}

@router.get("/summary")
def summary(area: str | None = Query(default=None), trace: str | None = Query(default=None)):
    return {
        "area": area,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace": trace,
        "note": "Ocean memory (time-series narrative) not configured yet",
        "data": {},
    }
