from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, Query

# pakai handler yang sudah ada (single source of truth)
from app.routers.time_series_profile import temp_profile as _temp_profile

router = APIRouter(prefix="/api/v1/fgi/time-series", tags=["FGI-TimeSeries"])


@router.get("/temp-profile")
def temp_profile_alias(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD, default: latest"),
    max_depth: float = Query(default=200.0),
) -> Dict[str, Any]:
    return _temp_profile(date=date, max_depth=max_depth)
