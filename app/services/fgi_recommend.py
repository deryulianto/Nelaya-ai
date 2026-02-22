from __future__ import annotations

import json, math, glob
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.fgi_recommend import (
    OptimizeOriginRequest, OptimizeOriginResponse,
    Spot, RankItem
)

ROOT = Path(__file__).resolve().parents[2]

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2
    return 2*R*math.asin(math.sqrt(a))

def _pick_geojson_for_date(date_utc: str) -> Optional[Path]:
    # 1) coba persis tanggalnya
    pat = str(ROOT / "data" / "fgi_daily" / "**" / f"fgi_map_{date_utc}.geojson")
    hits = glob.glob(pat, recursive=True)
    if hits:
        return Path(sorted(hits)[-1])

    # 2) fallback: latest geojson yang ada
    pat2 = str(ROOT / "data" / "fgi_daily" / "**" / "fgi_map_*.geojson")
    hits2 = glob.glob(pat2, recursive=True)
    if not hits2:
        return None
    # sort by filename (tanggal ada di nama)
    return Path(sorted(hits2)[-1])

def _load_points(fc: Dict[str, Any]) -> List[Tuple[float,float,float,Dict[str,Any]]]:
    out = []
    for f in (fc.get("features") or []):
        g = (f or {}).get("geometry") or {}
        if g.get("type") != "Point":
            continue
        coords = g.get("coordinates") or []
        if len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
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

async def recommend_optimize_origin(req: OptimizeOriginRequest) -> OptimizeOriginResponse:
    p = _pick_geojson_for_date(req.date_utc)

    if not p or not p.exists():
        return OptimizeOriginResponse(
            ok=False,
            message="No FGI map geojson available on disk",
            generated_at=datetime.now(timezone.utc).isoformat(),
            chosen_origin=req.origin,
            error="missing fgi_map_*.geojson under data/fgi_daily",
        )

    fc = json.loads(p.read_text())
    pts = _load_points(fc)
    if not pts:
        return OptimizeOriginResponse(
            ok=False,
            message="FGI geojson loaded but no valid point features found",
            generated_at=datetime.now(timezone.utc).isoformat(),
            chosen_origin=req.origin,
            error=f"empty/invalid points in {p}",
        )

    # sort by score desc
    pts.sort(key=lambda x: x[2], reverse=True)

    # ranks (top 30)
    ranks: List[RankItem] = []
    o_lat, o_lon = req.origin.lat, req.origin.lon
    for i, (lat, lon, score, props) in enumerate(pts[:30], start=1):
        dist = _haversine_km(o_lat, o_lon, lat, lon)
        ranks.append(RankItem(
            rank=i, lat=lat, lon=lon, score=score,
            band=props.get("band"), distance_km=dist
        ))

    # chosen_best_fgi: top1 by score
    lat, lon, score, props = pts[0]
    chosen_best_fgi = Spot(lat=lat, lon=lon, score=score, band=props.get("band"), props=props)

    # chosen_cheapest: nearest among top 20 (simple proxy)
    best_near = min(pts[:20], key=lambda x: _haversine_km(o_lat, o_lon, x[0], x[1]))
    lat2, lon2, score2, props2 = best_near
    chosen_cheapest = Spot(lat=lat2, lon=lon2, score=score2, band=props2.get("band"), props=props2)

    # chosen_best: kita samakan dengan best_fgi untuk sekarang
    chosen_best = chosen_best_fgi

    return OptimizeOriginResponse(
        ok=True,
        message="optimize-origin OK (simple disk-based recommender)",
        date=req.date_utc,
        generated_at=datetime.now(timezone.utc).isoformat(),
        mode="disk_geojson_v1",
        constraints={"boat_type": req.boat_type, "priority": req.priority, **(req.constraints or {})},
        chosen_origin=req.origin,
        chosen_best=chosen_best,
        chosen_cheapest=chosen_cheapest,
        chosen_best_fgi=chosen_best_fgi,
        ranks=ranks,
        detail={"source_geojson": str(p)},
    )
