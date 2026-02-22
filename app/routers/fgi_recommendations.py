# app/routers/fgi_recommendations.py
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from app.schemas.fgi_recommend import (
    OptimizeOriginRequest,
    OptimizeOriginResponse,
    SpotOut,
)

router = APIRouter(prefix="/api/v1/fgi/recommendations", tags=["FGI Recommendations"])

ROOT = Path(__file__).resolve().parents[2]  # .../NELAYA-AI-LAB
FGI_DAILY_DIR = ROOT / "data" / "fgi_daily"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _find_fgi_map_geojson(date_ymd: str, max_back_days: int = 14) -> Tuple[str, Path]:
    """
    Cari file: data/fgi_daily/YYYY/MM/fgi_map_YYYY-MM-DD.geojson
    Kalau tanggal itu gak ada, mundur sampai max_back_days.
    Return: (date_used, path)
    """
    try:
        base = datetime.strptime(date_ymd, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {date_ymd} (expected YYYY-MM-DD)")

    for k in range(0, max_back_days + 1):
        d = base - timedelta(days=k)
        yyyy = f"{d.year:04d}"
        mm = f"{d.month:02d}"
        fn = f"fgi_map_{d.isoformat()}.geojson"
        path = FGI_DAILY_DIR / yyyy / mm / fn
        if path.exists():
            return (d.isoformat(), path)

    raise HTTPException(
        status_code=404,
        detail=f"FGI map geojson not found for {date_ymd} (searched back {max_back_days} days) under {FGI_DAILY_DIR}",
    )


def _load_features(path: Path) -> List[Dict[str, Any]]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        feats = obj.get("features") or []
        if not isinstance(feats, list):
            return []
        return feats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read geojson: {path} ({e})")


def _feature_to_spot(f: Dict[str, Any], date_used: str) -> Optional[SpotOut]:
    g = f.get("geometry") or {}
    if g.get("type") != "Point":
        return None
    coords = g.get("coordinates") or []
    if not (isinstance(coords, list) and len(coords) >= 2):
        return None

    lon = float(coords[0])
    lat = float(coords[1])
    props = f.get("properties") or {}

    score = props.get("score", None)
    try:
        fgi = float(score)
    except Exception:
        return None

    return SpotOut(
        id=props.get("id"),
        lat=lat,
        lon=lon,
        fgi=fgi,
        band=props.get("band"),
        date=props.get("date_utc") or props.get("date") or date_used,
        sst_c=props.get("sst_c"),
        sal_psu=props.get("sal_psu"),
        chl_mg_m3=props.get("chl_mg_m3"),
    )


def _enforce_min_separation(spots: List[SpotOut], min_sep_km: float) -> List[SpotOut]:
    if min_sep_km <= 0:
        return spots
    picked: List[SpotOut] = []
    for s in spots:
        ok = True
        for p in picked:
            if _haversine_km(s.lat, s.lon, p.lat, p.lon) < min_sep_km:
                ok = False
                break
        if ok:
            picked.append(s)
    return picked


@router.post("/optimize-origin", response_model=OptimizeOriginResponse)
def optimize_origin(req: OptimizeOriginRequest) -> OptimizeOriginResponse:
    # date fallback
    date_used = req.date or req.date_utc
    if not date_used:
        date_used = datetime.now(timezone.utc).date().isoformat()

    # load geojson
    date_found, path = _find_fgi_map_geojson(date_used, max_back_days=14)
    feats = _load_features(path)

    origin = req.origin
    boat = req.boat
    cons = req.constraints

    candidates: List[SpotOut] = []
    for f in feats:
        spot = _feature_to_spot(f, date_found)
        if not spot:
            continue

        # filter FGI min
        if spot.fgi < float(cons.fgi_min):
            continue

        # distance
        dist_km = _haversine_km(origin.lat, origin.lon, spot.lat, spot.lon)
        if dist_km > float(cons.max_radius_km):
            continue

        # ETA + BBM
        speed = float(boat.speed_kmh)
        burn_lph = float(boat.burn_lph)
        fuel_price = float(boat.fuel_price)

        eta_min = (dist_km / speed) * 60.0
        hours_round = (dist_km * 2.0) / speed
        fuel_l = hours_round * burn_lph
        cost = fuel_l * fuel_price

        # mode budget: filter kalau ada budget_rp
        if req.mode == "budget" and cons.budget_rp is not None:
            if cost > float(cons.budget_rp):
                continue

        spot.distance_km = float(dist_km)
        spot.eta_min_oneway = float(eta_min)
        spot.fuel_l_roundtrip = float(fuel_l)
        spot.fuel_cost_rp = float(cost)

        candidates.append(spot)

    if not candidates:
        return OptimizeOriginResponse(
            ok=False,
            message="No candidate spots found (check radius/fgi_min/budget)",
            date=date_found,
            generated_at=datetime.now(timezone.utc).isoformat(),
            mode=req.mode,
            constraints=cons.model_dump(),
            chosen_origin=origin.model_dump(),
            ranks=[],
        )

    # rank lists
    # - by score desc then cost asc
    by_fgi = sorted(candidates, key=lambda s: (-float(s.fgi), float(s.fuel_cost_rp or 1e18)))
    # - by cost asc then score desc
    by_cost = sorted(candidates, key=lambda s: (float(s.fuel_cost_rp or 1e18), -float(s.fgi)))

    # apply min separation on top lists (biar tidak numpuk)
    top_n = int(cons.top_n)
    min_sep = float(cons.min_separation_km)

    ranked = _enforce_min_separation(by_fgi, min_sep)[:top_n]
    cheapest = _enforce_min_separation(by_cost, min_sep)[:top_n]

    chosen_best_fgi = ranked[0] if ranked else by_fgi[0]
    chosen_cheapest = cheapest[0] if cheapest else by_cost[0]

    if req.mode == "budget":
        chosen_best = chosen_cheapest
    else:
        # "optimal" = gabung score tinggi tapi tetap “waras” biaya
        chosen_best = by_fgi[0]

    return OptimizeOriginResponse(
        ok=True,
        message="ok",
        date=date_found,
        generated_at=datetime.now(timezone.utc).isoformat(),
        mode=req.mode,
        constraints=cons.model_dump(),
        chosen_origin=origin.model_dump(),
        chosen_best=chosen_best,
        chosen_cheapest=chosen_cheapest,
        chosen_best_fgi=chosen_best_fgi,
        ranks=ranked,
    )