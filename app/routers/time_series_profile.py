from fastapi import APIRouter
from typing import Optional

router = APIRouter(prefix="/api/v1/time-series", tags=["Time Series Profile"])

@router.get("/temp-profile")
def temp_profile(date: str, max_depth: int = 200, trace: Optional[str] = None):
    """
    Alias ke endpoint FGI biar konsisten:
    /api/v1/time-series/temp-profile  ->  /api/v1/fgi/time-series/temp-profile
    """
    from app.routers.fgi_time_series_profile import temp_profile as fgi_temp_profile  # local import avoid circular
    return fgi_temp_profile(date=date, max_depth=max_depth, trace=trace)
