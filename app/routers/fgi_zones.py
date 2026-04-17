from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.behavior_zones import compute_behavior_zones

router = APIRouter(tags=["FGI Zones"])


@router.get("/fgi/behavior-zones")
def behavior_zones(
    species: str = Query("medium_pelagic"),
    hotspot_threshold: float = Query(0.55, ge=0.0, le=1.0),
    top_k: int = Query(80, ge=1, le=500),
    eps_km: float = Query(25.0, gt=0.0),
    min_samples: int = Query(4, ge=1, le=50),
):
    return compute_behavior_zones(
        species=species,
        hotspot_threshold=hotspot_threshold,
        top_k=top_k,
        eps_km=eps_km,
        min_samples=min_samples,
    )