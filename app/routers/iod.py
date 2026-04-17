from __future__ import annotations

from fastapi import APIRouter

from app.services.iod_service import (
    build_iod_narrative,
    load_iod_historical_latest,
    load_iod_operational,
)

router = APIRouter(prefix="/iod", tags=["iod"])


@router.get("/today")
def get_iod_today():
    data = load_iod_operational()
    if data is None:
        return {
            "status": "unavailable",
            "message": "IOD operational data is not available yet.",
        }

    return {
        **data,
        "narrative": build_iod_narrative(data),
    }


@router.get("/historical/latest")
def get_iod_historical_latest():
    data = load_iod_historical_latest()
    if data is None:
        return {
            "status": "unavailable",
            "message": "IOD historical latest data is not available yet.",
        }

    return {
        **data,
        "narrative": build_iod_narrative(data),
    }
