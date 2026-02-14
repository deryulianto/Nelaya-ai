from __future__ import annotations

from pathlib import Path
import csv
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/fgi/time-series", tags=["FGI Time Series"])

ROOT_DIR = Path(__file__).resolve().parents[2]
TS_DIR = ROOT_DIR / "data" / "time_series"


def _pick_latest(files: List[Path]) -> Optional[Path]:
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[0] if files else None


def _parse_date(s: str) -> Optional[str]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).date().isoformat()
        except Exception:
            pass
    return s[:10]


def _find_daily_mean_csv(metric: str) -> Path:
    metric = (metric or "").lower().strip()
    aliases = {
        "sst": ["sst"],
        "chl": ["chl", "chlorophyll", "chlor_a", "chlorophyll_a"],
        "current": ["current", "speed", "uv", "u_v", "current_speed"],
        "temp50": ["temp50", "t50", "temp_50", "temp_50m"],
    }.get(metric, [metric])

    candidates: List[Path] = []
    if TS_DIR.exists():
        for a in aliases:
            candidates += list(TS_DIR.rglob(f"*{a}*_daily_mean*.csv"))
            candidates += list(TS_DIR.rglob(f"*{a}*daily*mean*.csv"))
            candidates += list(TS_DIR.rglob(f"*daily*mean*{a}*.csv"))

    p = _pick_latest(candidates)
    if not p:
        raise HTTPException(
            status_code=404,
            detail={"error": "daily_mean_csv_not_found", "metric": metric, "aliases": aliases, "searched_in": str(TS_DIR)},
        )
    return p


def _read_daily_mean_points(csv_path: Path, days: int) -> List[Dict[str, Any]]:
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            return []
        cols = list(r.fieldnames)

        date_col = next((c for c in cols if c.lower() in ("date", "day", "t", "time", "timestamp")), cols[0])
        value_col = next((c for c in cols if c != date_col), None)
        if not value_col:
            return []

        rows: List[Dict[str, Any]] = []
        for row in r:
            d = _parse_date(row.get(date_col, "") or "")
            try:
                v = float(row.get(value_col, ""))
            except Exception:
                continue
            if d:
                rows.append({"date": d, "mean": v})

    if days and days > 0 and len(rows) > days:
        rows = rows[-days:]
    return rows


@router.get("/daily-mean")
def daily_mean(metric: str = "sst", days: int = 90):
    # metric di frontend: sst | chl | current | temp50
    csv_path = _find_daily_mean_csv(metric)
    pts = _read_daily_mean_points(csv_path, int(days))
    return {
        "region": "Banda Aceh - Aceh Besar",
        "metric": metric,
        "days": int(days),
        "source": str(csv_path),
        "points": pts,
    }
