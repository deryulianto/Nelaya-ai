from __future__ import annotations

import json
import math
import glob
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.fgi_recommend import (
    OptimizeOriginRequest,
    OptimizeOriginResponse,
    SpotSummary,
    OriginRankItem,
    PortOrigin,
)

ROOT = Path(__file__).resolve().parents[2]

# --- FGI-R support (optional rumpon enhancement) ---
try:
    from app.utils.rumpon import load_rumpon_points, compute_rumpon_influence
    HAS_FGIR = True
except Exception:
    HAS_FGIR = False


def compute_fgi_r(env_score: float, lat: float, lon: float) -> float:
    """
    Combine environmental FGI with rumpon influence.
    If rumpon module unavailable, return env_score unchanged.
    """

    env_score = float(env_score)

    if not HAS_FGIR:
        return env_score

    try:
        rumpon_points = load_rumpon_points()

        if not rumpon_points:
            return env_score

        ri = compute_rumpon_influence(
            lat,
            lon,
            rumpon_points,
            lambda_km=15,
            radius_km=20,
        )

        rii = float(ri.get("rumpon_influence", 0))

        return (0.85 * env_score) + (0.15 * rii)

    except Exception:
        return env_score


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )

    return 2 * R * math.asin(math.sqrt(a))


def _pick_geojson_for_date(date_utc: Optional[str]) -> Optional[Path]:

    if date_utc:

        pat = str(
            ROOT
            / "data"
            / "fgi_daily"
            / "**"
            / f"fgi_map_{date_utc}.geojson"
        )

        hits = glob.glob(pat, recursive=True)

        if hits:
            return Path(sorted(hits)[-1])

    pat2 = str(
        ROOT
        / "data"
        / "fgi_daily"
        / "**"
        / "fgi_map_*.geojson"
    )

    hits2 = glob.glob(pat2, recursive=True)

    if hits2:
        return Path(sorted(hits2)[-1])

    return None


def _load_points(
    fc: Dict[str, Any]
) -> List[Tuple[float, float, float, Dict[str, Any]]]:

    out: List[Tuple[float, float, float, Dict[str, Any]]] = []

    for f in (fc.get("features") or []):

        g = (f or {}).get("geometry") or {}

        if g.get("type") != "Point":
            continue

        coords = g.get("coordinates") or []

        if len(coords) < 2:
            continue

        lon = float(coords[0])
        lat = float(coords[1])

        props = (f or {}).get("properties") or {}

        sc = props.get("score", None)

        try:
            score = float(sc) if sc is not None else float("nan")
        except Exception:
            score = float("nan")

        if not math.isfinite(score):
            continue

        out.append((lat, lon, score, props))

    return out


async def recommend_optimize_origin(
    req: OptimizeOriginRequest
) -> OptimizeOriginResponse:

    p = _pick_geojson_for_date(None)

    if not p or not p.exists():

        return OptimizeOriginResponse(
            ok=False,
            message="No FGI map geojson available on disk",
            generated_at=datetime.now(timezone.utc).isoformat(),
            error="missing fgi_map_*.geojson under data/fgi_daily",
        )

    fc = json.loads(p.read_text())

    pts = _load_points(fc)

    if not pts:

        return OptimizeOriginResponse(
            ok=False,
            message="FGI geojson loaded but no valid point features found",
            generated_at=datetime.now(timezone.utc).isoformat(),
            error=f"empty/invalid points in {p}",
        )

    # sort by environmental score
    pts.sort(key=lambda x: x[2], reverse=True)

    origin: Optional[PortOrigin] = None

    if req.origins and len(req.origins) > 0:
        origin = req.origins[0]

    o_lat = origin.lat if origin else None
    o_lon = origin.lon if origin else None

    ranks: List[OriginRankItem] = []

    for i, (lat, lon, score_env, props) in enumerate(pts[:30], start=1):

        score = compute_fgi_r(score_env, lat, lon)

        dist = None

        if o_lat is not None and o_lon is not None:
            dist = _haversine_km(o_lat, o_lon, lat, lon)

        spot = SpotSummary(
            lat=lat,
            lon=lon,
            fgi=score,
            band=props.get("band"),
            distance_km=dist,
            score=score,
        )

        ranks.append(
            OriginRankItem(
                origin=origin,
                chosen_best_fgi=spot,
                total_score=score,
            )
        )

    # Best FGI-R location

    lat, lon, score_env, props = pts[0]

    score = compute_fgi_r(score_env, lat, lon)

    chosen_best_fgi = SpotSummary(
        lat=lat,
        lon=lon,
        fgi=score,
        band=props.get("band"),
        score=score,
    )

    # Cheapest (nearest from top 20)

    if origin:

        best_near = min(
            pts[:20],
            key=lambda x: _haversine_km(o_lat, o_lon, x[0], x[1]),
        )

    else:

        best_near = pts[0]

    lat2, lon2, score2_env, props2 = best_near

    score2 = compute_fgi_r(score2_env, lat2, lon2)

    chosen_cheapest = SpotSummary(
        lat=lat2,
        lon=lon2,
        fgi=score2,
        band=props2.get("band"),
        score=score2,
    )

    return OptimizeOriginResponse(
        ok=True,
        message="optimize-origin OK (FGI-R enabled)",
        generated_at=datetime.now(timezone.utc).isoformat(),
        mode="disk_geojson_fgir_v1",
        chosen_origin=origin,
        chosen_best=chosen_best_fgi,
        chosen_cheapest=chosen_cheapest,
        chosen_best_fgi=chosen_best_fgi,
        ranks=ranks,
        detail={"source_geojson": str(p)},
    )