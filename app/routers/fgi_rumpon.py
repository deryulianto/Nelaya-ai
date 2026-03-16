from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query

from app.services.fgi_rumpon import enrich_feature_with_rumpon, FORMULA_VERSION
from app.utils.rumpon import load_rumpon_points

router = APIRouter(prefix="/api/v1/fgi-r", tags=["FGI-R (FGI + Rumpon)"])

ROOT = Path(__file__).resolve().parents[2]
FGI_DAILY_DIR = ROOT / "data" / "fgi_daily"
FGI_GRID_DIR = ROOT / "data" / "fgi_map_grid"


def _find_fgi_map_geojson(date_ymd: str, max_back_days: int = 14) -> Tuple[str, Path]:
    try:
        base = datetime.strptime(date_ymd[:10], "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {date_ymd}")

    for k in range(0, max_back_days + 1):
        d = base - timedelta(days=k)
        yyyy = f"{d.year:04d}"
        mm = f"{d.month:02d}"
        ds = d.isoformat()

        candidates = [
            FGI_DAILY_DIR / yyyy / mm / f"fgi_map_{ds}.geojson",
            FGI_GRID_DIR / f"fgi_grid_{ds}.geojson",
        ]
        for path in candidates:
            if path.exists() and path.is_file():
                return ds, path

    latest_grid = FGI_GRID_DIR / "latest.geojson"
    if latest_grid.exists() and latest_grid.is_file():
        return date_ymd[:10], latest_grid

    raise HTTPException(status_code=404, detail="FGI map geojson not found")


def _load_geojson(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read geojson: {e}")


def _pick_fgi_r(feature: Dict[str, Any]) -> float:
    props = feature.get("properties") or {}
    try:
        return float(props.get("fgi_r", props.get("score", 0.0)) or 0.0)
    except Exception:
        return 0.0


@router.get("/ping")
def ping():
    rumpon = load_rumpon_points()
    return {
        "status": "ok",
        "message": "FGI-R module alive",
        "rumpon_loaded": len(rumpon),
        "formula_version": FORMULA_VERSION,
    }


@router.get("/map")
def get_fgi_r_map(
    date: str = Query(..., description="YYYY-MM-DD"),
    lambda_km: float = Query(15.0, gt=0),
    radius_km: float = Query(20.0, gt=0),
    n_ref: int = Query(3, ge=1),
    w_env: float = Query(0.85, ge=0),
    w_rumpon: float = Query(0.15, ge=0),

    # visual mode
    mode: str = Query("full", description="full | ops | env_only"),
    min_fgi_r: Optional[float] = Query(None, ge=0, le=1),
    top_n: Optional[int] = Query(None, ge=1, le=500),
):
    date_used, path = _find_fgi_map_geojson(date)
    obj = _load_geojson(path)

    feats = obj.get("features") or []
    rumpon_points = load_rumpon_points()

    calc_mode = "env_only" if mode == "env_only" else "full"

    enriched: List[Dict[str, Any]] = []
    for f in feats:
        ef = enrich_feature_with_rumpon(
            f,
            rumpon_points,
            lambda_km=lambda_km,
            radius_km=radius_km,
            n_ref=n_ref,
            w_env=w_env,
            w_rumpon=w_rumpon,
            mode=calc_mode,
        )
        if ef is not None:
            enriched.append(ef)

    enriched.sort(key=_pick_fgi_r, reverse=True)

    effective_min = min_fgi_r
    effective_top_n = top_n

    if mode == "ops":
        if effective_min is None:
            effective_min = 0.30
        if effective_top_n is None:
            effective_top_n = 60

    if effective_min is not None:
        enriched = [f for f in enriched if _pick_fgi_r(f) >= float(effective_min)]

    if effective_top_n is not None:
        enriched = enriched[: int(effective_top_n)]

    return {
        "type": "FeatureCollection",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": {
            "date_used": date_used,
            "source_file": path.name,
            "count": len(enriched),
            "formula_version": FORMULA_VERSION,
            "formula": "FGI_R = w_env*FGI_env + w_rumpon*RII",
            "mode": mode,
            "fgi_env_inputs": ["sst_c", "sal_psu", "chl_mg_m3"],
            "not_yet_explicitly_included": ["sst_gradient", "current_speed", "chl_gradient"],
            "params": {
                "lambda_km": lambda_km,
                "radius_km": radius_km,
                "n_ref": n_ref,
                "w_env": w_env,
                "w_rumpon": w_rumpon,
                "min_fgi_r": effective_min,
                "top_n": effective_top_n,
            },
        },
        "features": enriched,
    }


@router.get("/compare")
def compare_modes(
    date: str = Query(..., description="YYYY-MM-DD"),
    top_n: int = Query(20, ge=1, le=100),
):
    """
    Membandingkan ranking env_only vs full untuk tanggal tertentu.
    Ini bukti kontribusi rumpon ke ranking.
    """
    date_used, path = _find_fgi_map_geojson(date)
    obj = _load_geojson(path)

    feats = obj.get("features") or []
    rumpon_points = load_rumpon_points()

    env_rows: List[Dict[str, Any]] = []
    full_rows: List[Dict[str, Any]] = []

    for f in feats:
        env_f = enrich_feature_with_rumpon(f, rumpon_points, mode="env_only")
        full_f = enrich_feature_with_rumpon(f, rumpon_points, mode="full")

        if env_f is not None:
            p = env_f.get("properties") or {}
            g = env_f.get("geometry") or {}
            c = g.get("coordinates") or [None, None]
            env_rows.append({
                "lon": c[0],
                "lat": c[1],
                "fgi_env": p.get("fgi_env"),
                "fgi_r": p.get("fgi_r"),
                "nearest_rumpon_id": p.get("nearest_rumpon_id"),
                "nearest_rumpon_km": p.get("nearest_rumpon_km"),
                "rumpon_influence": p.get("rumpon_influence"),
            })

        if full_f is not None:
            p = full_f.get("properties") or {}
            g = full_f.get("geometry") or {}
            c = g.get("coordinates") or [None, None]
            full_rows.append({
                "lon": c[0],
                "lat": c[1],
                "fgi_env": p.get("fgi_env"),
                "fgi_r": p.get("fgi_r"),
                "nearest_rumpon_id": p.get("nearest_rumpon_id"),
                "nearest_rumpon_km": p.get("nearest_rumpon_km"),
                "rumpon_influence": p.get("rumpon_influence"),
            })

    env_rows.sort(key=lambda x: float(x.get("fgi_r") or 0.0), reverse=True)
    full_rows.sort(key=lambda x: float(x.get("fgi_r") or 0.0), reverse=True)

    return {
        "ok": True,
        "date_used": date_used,
        "formula_version": FORMULA_VERSION,
        "env_only_top": env_rows[:top_n],
        "full_top": full_rows[:top_n],
    }

@router.get("/hotspots")
def get_fgi_r_hotspots(
    date: str = Query(..., description="YYYY-MM-DD"),
    top_n: int = Query(3, ge=1, le=10),
):
    """
    Endpoint ringan untuk kartu FGI Lab / hotspot harian.
    Mengembalikan top hotspot operasional yang sudah diperkaya explainability.
    """
    date_used, path = _find_fgi_map_geojson(date)
    obj = _load_geojson(path)

    feats = obj.get("features") or []
    rumpon_points = load_rumpon_points()

    enriched: List[Dict[str, Any]] = []
    for f in feats:
        ef = enrich_feature_with_rumpon(
            f,
            rumpon_points,
            mode="full",
        )
        if ef is not None:
            enriched.append(ef)

    enriched.sort(key=_pick_fgi_r, reverse=True)
    enriched = enriched[:top_n]

    hotspots: List[Dict[str, Any]] = []
    for i, f in enumerate(enriched, start=1):
        g = f.get("geometry") or {}
        p = f.get("properties") or {}
        coords = g.get("coordinates") or [None, None]

        hotspots.append(
            {
                "rank": i,
                "lat": coords[1],
                "lon": coords[0],
                "fgi_env": p.get("fgi_env"),
                "fgi_r": p.get("fgi_r"),
                "band": p.get("band_r") or p.get("band"),
                "sst_c": p.get("sst_c"),
                "sal_psu": p.get("sal_psu"),
                "chl_mg_m3": p.get("chl_mg_m3"),
                "nearest_rumpon_id": p.get("nearest_rumpon_id"),
                "nearest_rumpon_km": p.get("nearest_rumpon_km"),
                "rumpon_influence": p.get("rumpon_influence"),
                "formula_version": p.get("formula_version"),
                "mode": p.get("mode"),
            }
        )

    return {
        "ok": True,
        "date_used": date_used,
        "formula_version": FORMULA_VERSION,
        "model_summary": {
            "env_inputs": ["sst_c", "sal_psu", "chl_mg_m3"],
            "enhancement": "rumpon distance decay",
            "not_yet_explicitly_included": ["sst_gradient", "current_speed", "chl_gradient"],
        },
        "hotspots": hotspots,
    }