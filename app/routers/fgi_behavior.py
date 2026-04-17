from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException, Query

from app.schemas.behavior_fgi import BehaviorFGIRequest, BehaviorFGIResponse
from app.schemas.behavior_from_raw import (
    BehaviorFromRawResponse,
    BehaviorFromRawSummaryResponse,
)
from app.services.behavior_fgi import compute_behavior_fgi
from app.services.behavior_from_raw import (
    compute_behavior_fgi_from_raw,
    extract_behavior_hotspots,
)

from app.schemas.behavior_hotspots import BehaviorHotspotsResponse
from app.services.behavior_from_raw import (
    compute_behavior_fgi_from_raw,
    extract_behavior_hotspots,
)

from app.schemas.behavior_today import BehaviorTodayResponse
from app.services.behavior_today import get_behavior_today

router = APIRouter(tags=["FGI Behavior"])


@router.post("/fgi/behavior-score", response_model=BehaviorFGIResponse)
def behavior_score(payload: BehaviorFGIRequest) -> BehaviorFGIResponse:
    try:
        result = compute_behavior_fgi(
            sst=np.array(payload.sst, dtype=float),
            chl=np.array(payload.chl, dtype=float),
            wind=np.array(payload.wind, dtype=float),
            wave=np.array(payload.wave, dtype=float),
            salinity=np.array(payload.salinity, dtype=float),
            ssh_cm=np.array(payload.ssh_cm, dtype=float),
            species=payload.species,
            dx=payload.dx,
            dy=payload.dy,
            hotspot_threshold=payload.hotspot_threshold,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute behavior score: {e}") from e

    return BehaviorFGIResponse(
        species=payload.species,
        component_means=result["component_means"],
        explanation=result["explanation"],
        hotspot_threshold=payload.hotspot_threshold,
        hotspot_fraction=result["component_means"]["hotspot_fraction"],
        behavior_score_grid=result["behavior_score_grid"],
        hotspot_mask=result["hotspot_mask"],
    )


@router.get("/fgi/behavior-from-raw", response_model=BehaviorFromRawResponse)
def behavior_from_raw(
    date: str = Query(..., description="Tanggal format YYYY-MM-DD"),
    species: str = Query("medium_pelagic"),
    hotspot_threshold: float = Query(0.65, ge=0.0, le=1.0),
    target_field: str = Query("sst"),
    base_dir: str = Query("data/raw/aceh_simeulue"),
) -> BehaviorFromRawResponse:
    try:
        result = compute_behavior_fgi_from_raw(
            date_str=date,
            species=species,
            base_dir=Path(base_dir),
            target_field=target_field,
            hotspot_threshold=hotspot_threshold,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute behavior from raw: {e}") from e

    return BehaviorFromRawResponse(
        date=result["date"],
        species=result["species"],
        component_means=result["component_means"],
        explanation=result["explanation"],
        lat=result["lat"],
        lon=result["lon"],
        behavior_score_grid=result["behavior_score_grid"],
        hotspot_mask=result["hotspot_mask"],
        meta=result["meta"],
    )


@router.get("/fgi/behavior-summary", response_model=BehaviorFromRawSummaryResponse)
def behavior_summary(
    date: str = Query(..., description="Tanggal format YYYY-MM-DD"),
    species: str = Query("medium_pelagic"),
    hotspot_threshold: float = Query(0.65, ge=0.0, le=1.0),
    target_field: str = Query("sst"),
    base_dir: str = Query("data/raw/aceh_simeulue"),
) -> BehaviorFromRawSummaryResponse:
    try:
        result = compute_behavior_fgi_from_raw(
            date_str=date,
            species=species,
            base_dir=Path(base_dir),
            target_field=target_field,
            hotspot_threshold=hotspot_threshold,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute behavior summary: {e}") from e

    return BehaviorFromRawSummaryResponse(
        date=result["date"],
        species=result["species"],
        component_means=result["component_means"],
        explanation=result["explanation"],
        hotspot_fraction=float(result["component_means"]["hotspot_fraction"]),
        meta=result["meta"],
    )

@router.get("/fgi/behavior-hotspots", response_model=BehaviorHotspotsResponse)
def behavior_hotspots(
    date: str = Query(..., description="Tanggal format YYYY-MM-DD"),
    species: str = Query("medium_pelagic"),
    hotspot_threshold: float = Query(0.55, ge=0.0, le=1.0),
    target_field: str = Query("sst"),
    base_dir: str = Query("data/raw/aceh_simeulue"),
    top_k: int = Query(150, ge=1, le=5000),
) -> BehaviorHotspotsResponse:
    try:
        result = extract_behavior_hotspots(
            date_str=date,
            species=species,
            base_dir=Path(base_dir),
            target_field=target_field,
            hotspot_threshold=hotspot_threshold,
            top_k=top_k,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute behavior hotspots: {e}") from e

    return BehaviorHotspotsResponse(
        date=result["date"],
        species=result["species"],
        threshold=float(result["threshold"]),
        count=int(result["count"]),
        points=result["points"],
        component_means=result["component_means"],
        explanation=result["explanation"],
        meta=result["meta"],
    )

@router.get("/fgi/behavior-today", response_model=BehaviorTodayResponse)
def behavior_today(
    species: str = Query("medium_pelagic"),
    hotspot_threshold: float = Query(0.55, ge=0.0, le=1.0),
    top_k: int = Query(50, ge=1, le=5000),
    target_field: str = Query("sst"),
    base_dir: str = Query("data/raw/aceh_simeulue"),
) -> BehaviorTodayResponse:
    try:
        result = get_behavior_today(
            species=species,
            hotspot_threshold=hotspot_threshold,
            top_k=top_k,
            base_dir=Path(base_dir),
            target_field=target_field,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute behavior today: {e}") from e

    return BehaviorTodayResponse(
        date=result["date"],
        species=result["species"],
        threshold=float(result["threshold"]),
        count=int(result["count"]),
        points=result["points"],
        component_means=result["component_means"],
        explanation=result["explanation"],
        meta=result["meta"],
    )