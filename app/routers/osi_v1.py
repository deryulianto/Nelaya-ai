from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.osi import OsiFeatures, OsiResponse, compute_osi

router = APIRouter(prefix="/api/v1/osi", tags=["osi-v1"])


@router.get("/health")
def osi_health():
    return {"ok": True, "service": "osi-v1"}


@router.post("/compute", response_model=OsiResponse)
def compute_osi_endpoint(payload: OsiFeatures) -> OsiResponse:
    try:
        return compute_osi(payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OSI compute failed: {e}") from e