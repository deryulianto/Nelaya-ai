from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/fgi/map-build", tags=["FGI Map Build"])

@router.get("/ping")
def ping():
    return {"ok": True, "service": "fgi_map_build"}

@router.post("/run")
def run(date: str | None = Query(default=None), trace: str | None = Query(default=None)):
    # Placeholder: nanti disambungkan ke pipeline build peta FGI (raster/tiles/json)
    return {
        "ok": True,
        "requested_date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace": trace,
        "note": "FGI map build pipeline not configured yet",
    }
