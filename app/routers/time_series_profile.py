from fastapi import APIRouter
from typing import Optional

router = APIRouter(prefix="/api/v1/time-series", tags=["Time Series Profile"])


@router.get("/temp-profile")
def temp_profile(date: Optional[str] = None, max_depth: int = 200, trace: Optional[str] = None):
    """
    Alias:
    /api/v1/time-series/temp-profile  ->  /api/v1/fgi/time-series/temp-profile
    """
    from app.routers.fgi_time_series_profile import temp_profile as fgi_temp_profile
    return fgi_temp_profile(date=date, max_depth=max_depth, trace=trace)


@router.get("/sal-profile")
def sal_profile(date: Optional[str] = None, max_depth: int = 200, trace: Optional[str] = None):
    """
    Alias:
    /api/v1/time-series/sal-profile  ->  /api/v1/fgi/time-series/sal-profile
    """
    from app.routers.fgi_time_series_profile import sal_profile as fgi_sal_profile
    return fgi_sal_profile(date=date, max_depth=max_depth, trace=trace)