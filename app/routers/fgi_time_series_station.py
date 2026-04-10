from __future__ import annotations

from datetime import date as dt_date

from fastapi import APIRouter, HTTPException, Query

from app.core.ocean_stations import get_station, list_stations
from app.services.profile_station_sampling import (
    get_sal_profile_station,
    get_temp_profile_station,
)

router = APIRouter(
    prefix="/api/v1/fgi/time-series",
    tags=["FGI Time Series Stations"],
)


@router.get("/stations")
def api_list_stations():
    return {"stations": list_stations()}


@router.get("/temp-profile-station")
def api_temp_profile_station(
    station: str = Query(..., description="malaka | andaman | hindia"),
    date: str = Query(default_factory=lambda: dt_date.today().isoformat()),
    max_depth: int = Query(200, ge=10, le=1000),
):
    st = get_station(station)
    if not st:
        raise HTTPException(status_code=400, detail=f"Unknown station: {station}")

    return get_temp_profile_station(
        date=date,
        station_id=station,
        max_depth=max_depth,
    )


@router.get("/sal-profile-station")
def api_sal_profile_station(
    station: str = Query(..., description="malaka | andaman | hindia"),
    date: str = Query(default_factory=lambda: dt_date.today().isoformat()),
    max_depth: int = Query(200, ge=10, le=1000),
):
    st = get_station(station)
    if not st:
        raise HTTPException(status_code=400, detail=f"Unknown station: {station}")

    return get_sal_profile_station(
        date=date,
        station_id=station,
        max_depth=max_depth,
    )