from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from app.schemas.fgi_recommend import (
    OptimizeOriginRequest,
    SpotOut,
)

# --- FGI-R support (optional rumpon enhancement) ---
try:
    from app.utils.rumpon import load_rumpon_points, compute_rumpon_influence
    HAS_FGIR = True
except Exception:
    HAS_FGIR = False

router = APIRouter(prefix="/api/v1/fgi/recommendations", tags=["FGI Recommendations"])

ROOT = Path(__file__).resolve().parents[2]
FGI_DAILY_DIR = ROOT / "data" / "fgi_daily"
FGI_GRID_DIR = ROOT / "data" / "fgi_map_grid"


def _freshness_status(date_utc: str | None, ref_day_utc: str | None = None) -> str:
    try:
        if not date_utc:
            return "unknown"
        data_day = datetime.strptime(str(date_utc)[:10], "%Y-%m-%d").date()
        ref_day = (
            datetime.strptime(str(ref_day_utc)[:10], "%Y-%m-%d").date()
            if ref_day_utc
            else datetime.now(timezone.utc).date()
        )
        age = (ref_day - data_day).days
        if age <= 0:
            return "fresh"
        if age <= 2:
            return "recent"
        return "stale"
    except Exception:
        return "unknown"


def _confidence_recommendation(
    candidate_count: int,
    used_budget_filter: bool,
    fgir_enabled: bool,
) -> str:
    if candidate_count >= 10 and fgir_enabled:
        return "high"
    if candidate_count >= 3:
        return "medium"
    if candidate_count >= 1:
        return "low"
    return "low"


def _build_trust(
    *,
    source: str,
    date_utc: str | None,
    generated_at: str | None,
    confidence: str,
    basis_type: str,
    mode: str,
    candidate_count: int,
) -> Dict[str, Any]:
    freshness = _freshness_status(date_utc)
    caveat = (
        "Rekomendasi memadukan skor FGI-R, jarak, dan biaya operasi; bukan jaminan hasil tangkapan."
        if basis_type == "rule_plus_model_recommendation"
        else "Skor bersifat indikatif dan perlu dibaca bersama kondisi laut aktual."
    )
    return {
        "source": source,
        "date_utc": date_utc,
        "generated_at": generated_at,
        "freshness_status": freshness,
        "confidence": confidence,
        "basis_type": basis_type,
        "mode": mode,
        "candidate_count": candidate_count,
        "caveat": caveat,
    }


def _spot_to_dict(s: SpotOut) -> Dict[str, Any]:
    if hasattr(s, "model_dump"):
        return s.model_dump()
    if hasattr(s, "dict"):
        return s.dict()
    return dict(s)


def _origin_to_dict(origin: Any) -> Dict[str, Any]:
    if hasattr(origin, "model_dump"):
        return origin.model_dump()
    if hasattr(origin, "dict"):
        return origin.dict()
    return dict(origin)


def _build_port_rank_items(origin: Any, ranked: List[SpotOut], cheapest: SpotOut | None, best_fgi: SpotOut | None, budget_rp: float | None) -> List[Dict[str, Any]]:
    if not origin:
        return []
    cheapest_cost = float(cheapest.fuel_cost_rp or 0.0) if cheapest else None
    best_fgi_value = float(best_fgi.fgi or 0.0) if best_fgi else None
    within_budget = None if budget_rp is None or cheapest_cost is None else cheapest_cost <= float(budget_rp)
    over_budget_by_rp = None if budget_rp is None or cheapest_cost is None else max(0.0, cheapest_cost - float(budget_rp))
    if cheapest_cost is None:
        ui_badge = "No candidate"
        ui_summary = "Belum ada spot yang lolos filter radius / FGI / budget."
    else:
        if within_budget is True:
            ui_badge = "Within budget"
        elif within_budget is False:
            ui_badge = "Over budget"
        else:
            ui_badge = "Candidate"
        ui_summary = (
            f"Cheapest ~{round(cheapest_cost):,} Rp • "
            f"Best FGI {best_fgi_value:.3f}" if best_fgi_value is not None else
            f"Cheapest ~{round(cheapest_cost):,} Rp"
        ).replace(",", ".")
    return [{
        "origin": _origin_to_dict(origin),
        "n_spots": len(ranked),
        "ui_badge": ui_badge,
        "ui_summary": ui_summary,
        "cheapest_cost_rp": cheapest_cost,
        "best_fgi_value": best_fgi_value,
        "within_budget": within_budget,
        "over_budget_by_rp": over_budget_by_rp,
        "cheapest": _spot_to_dict(cheapest) if cheapest else None,
        "best_fgi": _spot_to_dict(best_fgi) if best_fgi else None,
    }]


def _suggest_budget(cheapest: SpotOut | None) -> Dict[str, Any]:
    if not cheapest or cheapest.fuel_cost_rp is None:
        return {
            "suggested_budget_min_rp": None,
            "suggested_budget_rounded_rp": None,
            "suggested_budget_note": None,
        }
    min_rp = float(cheapest.fuel_cost_rp)
    rounded = int(math.ceil(min_rp / 50000.0) * 50000)
    return {
        "suggested_budget_min_rp": round(min_rp, 2),
        "suggested_budget_rounded_rp": rounded,
        "suggested_budget_note": "Dibulatkan ke atas per 50 ribu untuk buffer operasional.",
    }



def _to_band(p: float) -> str:
    return "High" if p >= 0.75 else ("Medium" if p >= 0.50 else "Low")


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
    Cari file FGI dari:
    1) legacy: data/fgi_daily/YYYY/MM/fgi_map_YYYY-MM-DD.geojson
    2) current: data/fgi_map_grid/fgi_grid_YYYY-MM-DD.geojson
    3) fallback terakhir: data/fgi_map_grid/latest.geojson
    Return: (date_used, path)
    """
    try:
        base = datetime.strptime(date_ymd[:10], "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date format: {date_ymd} (expected YYYY-MM-DD)"
        )

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
                return (ds, path)

    latest_grid = FGI_GRID_DIR / "latest.geojson"
    if latest_grid.exists() and latest_grid.is_file():
        return (date_ymd[:10], latest_grid)

    raise HTTPException(
        status_code=404,
        detail=(
            f"FGI map geojson not found for {date_ymd} "
            f"(searched back {max_back_days} days) under "
            f"{FGI_DAILY_DIR} and {FGI_GRID_DIR}"
        ),
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


def _pick_number(*vals: Any) -> Optional[float]:
    for v in vals:
        try:
            if v is None:
                continue
            n = float(v)
            if math.isfinite(n):
                return n
        except Exception:
            continue
    return None


def _compute_fgi_r(env_score: float, lat: float, lon: float) -> Dict[str, Any]:
    """
    Blend environmental FGI with rumpon influence:
    FGI_R = 0.85 * FGI_env + 0.15 * RII
    """
    env_score = float(env_score)

    if not HAS_FGIR:
        return {
            "fgi_env": round(env_score, 6),
            "fgi_r": round(env_score, 6),
            "band_r": _to_band(env_score),
            "nearest_rumpon_id": None,
            "nearest_rumpon_km": None,
            "rumpon_count_radius": None,
            "rumpon_influence": None,
            "distance_score": None,
            "density_score": None,
            "legal_score": None,
        }

    try:
        rumpon_points = load_rumpon_points()
        if not rumpon_points:
            return {
                "fgi_env": round(env_score, 6),
                "fgi_r": round(env_score, 6),
                "band_r": _to_band(env_score),
                "nearest_rumpon_id": None,
                "nearest_rumpon_km": None,
                "rumpon_count_radius": None,
                "rumpon_influence": None,
                "distance_score": None,
                "density_score": None,
                "legal_score": None,
            }

        ri = compute_rumpon_influence(
            lat,
            lon,
            rumpon_points,
            lambda_km=15.0,
            radius_km=20.0,
            n_ref=3,
            w_distance=0.5,
            w_density=0.2,
            w_legal=0.3,
        )

        rii = float(ri["rumpon_influence"])
        fgi_r = (0.85 * env_score) + (0.15 * rii)
        fgi_r = max(0.0, min(1.0, fgi_r))

        return {
            "fgi_env": round(env_score, 6),
            "fgi_r": round(fgi_r, 6),
            "band_r": _to_band(fgi_r),
            "nearest_rumpon_id": ri["nearest_rumpon_id"],
            "nearest_rumpon_km": ri["nearest_rumpon_km"],
            "rumpon_count_radius": ri["rumpon_count_radius"],
            "rumpon_influence": ri["rumpon_influence"],
            "distance_score": ri["distance_score"],
            "density_score": ri["density_score"],
            "legal_score": ri["legal_score"],
        }

    except Exception:
        return {
            "fgi_env": round(env_score, 6),
            "fgi_r": round(env_score, 6),
            "band_r": _to_band(env_score),
            "nearest_rumpon_id": None,
            "nearest_rumpon_km": None,
            "rumpon_count_radius": None,
            "rumpon_influence": None,
            "distance_score": None,
            "density_score": None,
            "legal_score": None,
        }


def _feature_to_spot(f: Dict[str, Any], date_used: str) -> Optional[SpotOut]:
    g = f.get("geometry") or {}
    if g.get("type") != "Point":
        return None

    coords = g.get("coordinates") or []
    if not (isinstance(coords, list) and len(coords) >= 2):
        return None

    try:
        lon = float(coords[0])
        lat = float(coords[1])
    except Exception:
        return None

    props = f.get("properties") or {}
    fgi_obj = props.get("fgi") or {}
    means = props.get("means") or {}

    score = _pick_number(
        props.get("score"),
        fgi_obj.get("score"),
        fgi_obj.get("raw"),
    )
    if score is None:
        return None

    band = props.get("band") or fgi_obj.get("band")

    rmeta = _compute_fgi_r(float(score), lat, lon)

    return SpotOut(
        id=props.get("id"),
        lat=lat,
        lon=lon,
        fgi=float(rmeta["fgi_r"]),   # <-- pakai FGI-R sebagai skor utama recommendation
        band=rmeta["band_r"] or band,
        date=props.get("date_utc") or props.get("date") or date_used,
        sst_c=_pick_number(props.get("sst_c"), means.get("sst_c")),
        sal_psu=_pick_number(props.get("sal_psu"), means.get("sal_psu")),
        chl_mg_m3=_pick_number(props.get("chl_mg_m3"), means.get("chl_mg_m3")),

        fgi_env=float(rmeta["fgi_env"]),
        fgi_r=float(rmeta["fgi_r"]),
        band_r=rmeta["band_r"],

        nearest_rumpon_id=rmeta["nearest_rumpon_id"],
        nearest_rumpon_km=rmeta["nearest_rumpon_km"],
        rumpon_count_radius=rmeta["rumpon_count_radius"],
        rumpon_influence=rmeta["rumpon_influence"],
        distance_score=rmeta["distance_score"],
        density_score=rmeta["density_score"],
        legal_score=rmeta["legal_score"],
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


def _pick_optimal_spot(spots: List[SpotOut]) -> SpotOut:
    """
    Pilih rekomendasi seimbang:
    - peluang relatif (FGI-R) tetap dominan
    - biaya dan jarak ikut dipertimbangkan
    """
    if not spots:
        raise ValueError("No spots available")

    max_cost = max(float(s.fuel_cost_rp or 0.0) for s in spots) or 1.0
    max_dist = max(float(s.distance_km or 0.0) for s in spots) or 1.0

    def utility(s: SpotOut) -> float:
        fgi = float(s.fgi or 0.0)
        cost_norm = float(s.fuel_cost_rp or 0.0) / max_cost
        dist_norm = float(s.distance_km or 0.0) / max_dist

        return (
            0.55 * fgi +
            0.25 * (1.0 - cost_norm) +
            0.20 * (1.0 - dist_norm)
        )

    return max(spots, key=utility)


@router.post("/optimize-origin")
def optimize_origin(req: OptimizeOriginRequest) -> Dict[str, Any]:
    # date fallback
    date_used = req.date or req.date_utc
    if not date_used:
        date_used = datetime.now(timezone.utc).date().isoformat()

    # wajib ada origin
    origin = req.origin
    if not origin:
        raise HTTPException(status_code=422, detail="origin is required")

    boat = req.boat
    cons = req.constraints

    # load geojson
    date_found, path = _find_fgi_map_geojson(date_used, max_back_days=14)
    feats = _load_features(path)

    candidates: List[SpotOut] = []
    rejected_by_budget: List[SpotOut] = []

    for f in feats:
        spot = _feature_to_spot(f, date_found)
        if not spot:
            continue

        # filter FGI min -> pakai FGI-R
        if spot.fgi < float(cons.fgi_min):
            continue

        # distance
        dist_km = _haversine_km(origin.lat, origin.lon, spot.lat, spot.lon)
        if dist_km > float(cons.max_radius_km):
            continue

        # ETA + BBM
        speed = max(1e-6, float(boat.speed_kmh))
        burn_lph = max(0.0, float(boat.burn_lph))
        fuel_price = max(0.0, float(boat.fuel_price))

        eta_min = (dist_km / speed) * 60.0
        hours_round = (dist_km * 2.0) / speed
        fuel_l = hours_round * burn_lph
        cost = fuel_l * fuel_price

        spot.distance_km = float(dist_km)
        spot.eta_min_oneway = float(eta_min)
        spot.fuel_l_roundtrip = float(fuel_l)
        spot.fuel_cost_rp = float(cost)

        # mode budget
        if req.mode == "budget" and cons.budget_rp is not None:
            if cost > float(cons.budget_rp):
                rejected_by_budget.append(spot)
                continue

        candidates.append(spot)

    if not candidates:
        msg = "No candidate spots found"
        if req.mode == "budget" and cons.budget_rp is not None and rejected_by_budget:
            cheapest_over = min(rejected_by_budget, key=lambda s: float(s.fuel_cost_rp or 1e18))
            msg = (
                "No candidate spots passed current budget. "
                f"Cheapest available is ~{round(float(cheapest_over.fuel_cost_rp or 0.0))} Rp "
                f"at {round(float(cheapest_over.distance_km or 0.0), 1)} km."
            )
        else:
            msg = "No candidate spots found (check radius / fgi_min / budget / source data)"

        generated_at = datetime.now(timezone.utc).isoformat()
        suggested = _suggest_budget(min(rejected_by_budget, key=lambda s: float(s.fuel_cost_rp or 1e18)) if rejected_by_budget else None)
        return {
            "ok": False,
            "message": msg,
            "date": date_found,
            "generated_at": generated_at,
            "mode": req.mode,
            "constraints": cons.model_dump(),
            "chosen_origin": origin.model_dump(),
            "chosen_best": None,
            "chosen_cheapest": None,
            "chosen_best_fgi": None,
            "ranks": [],
            "ranked_origins": [],
            "recommendations": None,
            **suggested,
            "trust": _build_trust(
                source=f"FGI geojson • {path.name}",
                date_utc=date_found,
                generated_at=generated_at,
                confidence="low",
                basis_type="rule_plus_model_recommendation",
                mode="upstream",
                candidate_count=0,
            ),
        }

    # ranking dasar -> sekarang berdasarkan FGI-R
    by_fgi = sorted(candidates, key=lambda s: (-float(s.fgi), float(s.fuel_cost_rp or 1e18)))
    by_cost = sorted(candidates, key=lambda s: (float(s.fuel_cost_rp or 1e18), -float(s.fgi)))

    top_n = int(cons.top_n)
    min_sep = float(cons.min_separation_km)

    ranked = _enforce_min_separation(by_fgi, min_sep)[:top_n]
    cheapest_ranked = _enforce_min_separation(by_cost, min_sep)[:top_n]

    chosen_best_fgi = by_fgi[0]
    chosen_cheapest = by_cost[0]

    if req.mode == "budget":
        chosen_best = chosen_cheapest
    else:
        chosen_best = _pick_optimal_spot(candidates)

    generated_at = datetime.now(timezone.utc).isoformat()
    suggested = _suggest_budget(chosen_cheapest)
    port_items = _build_port_rank_items(
        origin=origin,
        ranked=ranked,
        cheapest=chosen_cheapest,
        best_fgi=chosen_best_fgi,
        budget_rp=cons.budget_rp,
    )
    return {
        "ok": True,
        "message": (
            f"ok • source={path.name} • date_used={date_found} "
            f"• candidates={len(candidates)} • fgir={'on' if HAS_FGIR else 'off'}"
        ),
        "date": date_found,
        "generated_at": generated_at,
        "mode": req.mode,
        "constraints": cons.model_dump(),
        "chosen_origin": origin.model_dump(),
        "chosen_best": _spot_to_dict(chosen_best),
        "chosen_cheapest": _spot_to_dict(chosen_cheapest),
        "chosen_best_fgi": _spot_to_dict(chosen_best_fgi),
        "ranks": [_spot_to_dict(s) for s in ranked],
        "ranked_origins": port_items,
        "recommendations": {
            "chosen_origin": origin.model_dump(),
            "chosen_best": _spot_to_dict(chosen_best),
            "candidate_count": len(candidates),
        },
        **suggested,
        "trust": _build_trust(
            source=f"FGI geojson • {path.name}",
            date_utc=date_found,
            generated_at=generated_at,
            confidence=_confidence_recommendation(
                candidate_count=len(candidates),
                used_budget_filter=(req.mode == "budget" and cons.budget_rp is not None),
                fgir_enabled=HAS_FGIR,
            ),
            basis_type="rule_plus_model_recommendation",
            mode="upstream",
            candidate_count=len(candidates),
        ),
    }