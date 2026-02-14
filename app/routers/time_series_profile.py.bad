from __future__ import annotations

from datetime import datetime
from pathlib import Path
import csv
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from app.routers.time_series_profile import temp_profile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data" / "time_series" / "aceh" / "banda_aceh_aceh_besar" / "temp_profile" / "series"
SERIES = BASE / "temp_profile_daily_profile.csv"

router = APIRouter(prefix="/api/v1/time-series", tags=["FGI-TimeSeries"])


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


@router.get("/temp-profile")
def temp_profile(
    date: Optional[str] = Query(default=None),
    max_depth: float = Query(default=200.0),
) -> Dict[str, Any]:
     return temp_profile(date=date, max_depth=max_depth)

    rows: List[Dict[str, Any]] = []
    all_dates: List[str] = []

    with open(SERIES, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            d = (row.get("date") or "").strip()
            if d:
                all_dates.append(d)
            rows.append(row)

    if not rows:
        return {"region": "Banda Aceh - Aceh Besar", "date": date, "points": []}

    # pilih tanggal (default latest yang ada)
    target = date
    if not target:
        target = sorted(set(all_dates))[-1]

    # kalau tanggal target tidak ada, fallback ke nearest previous
    existing = sorted(set(all_dates))
    if target not in set(existing):
        # pilih tanggal <= target
        try:
            td = _parse_date(target).date()
            cand = [d for d in existing if _parse_date(d).date() <= td]
            target = cand[-1] if cand else existing[-1]
        except Exception:
            target = existing[-1]

    pts: List[Dict[str, Any]] = []
    for row in rows:
        if (row.get("date") or "").strip() != target:
            continue
        try:
            depth = float(row.get("depth_m") or "nan")
        except Exception:
            continue
        if depth > max_depth:
            continue
        t_raw = (row.get("temp_c") or "").strip()
        if not t_raw:
            continue
        try:
            temp = float(t_raw)
        except Exception:
            continue
        pts.append({"depth_m": depth, "temp_c": temp})

    pts.sort(key=lambda x: x["depth_m"])

    return {
        "region": "Banda Aceh - Aceh Besar",
        "date": target,
        "points": pts,
    }
