from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/fgi/cache", tags=["FGI Cache"])

@router.get("/ping")
def ping():
    return {"ok": True, "service": "fgi_cache"}

@router.get("/status")
def status(trace: str | None = Query(default=None)):
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace": trace,
        "note": "FGI cache layer not configured yet",
    }
