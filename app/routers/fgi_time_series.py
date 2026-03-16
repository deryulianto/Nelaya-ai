from __future__ import annotations

from pathlib import Path
import csv
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/fgi/time-series", tags=["FGI Time Series"])

ROOT_DIR = Path(__file__).resolve().parents[2]
TS_DIR = ROOT_DIR / "data" / "time_series"


def _pick_latest(files: List[Path]) -> Optional[Path]:
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[0] if files else None


def _parse_date_obj(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except Exception:
            pass

    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


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
            detail={
                "error": "daily_mean_csv_not_found",
                "metric": metric,
                "aliases": aliases,
                "searched_in": str(TS_DIR),
            },
        )
    return p


def _pick_value_col(cols: List[str], date_col: str) -> Optional[str]:
    preferred = [
        "mean",
        "daily_mean",
        "avg",
        "average",
        "value",
        "v",
    ]

    low_map = {c.lower(): c for c in cols}
    for p in preferred:
        if p in low_map and low_map[p] != date_col:
            return low_map[p]

    for c in cols:
        if c != date_col:
            return c
    return None


def _read_daily_mean_rows(csv_path: Path) -> List[Dict[str, Any]]:
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            return []

        cols = list(r.fieldnames)
        date_col = next(
            (c for c in cols if c.lower() in ("date", "day", "t", "time", "timestamp")),
            cols[0],
        )
        value_col = _pick_value_col(cols, date_col)
        if not value_col:
            return []

        # dedupe by date, keep the latest row encountered in file
        by_date: Dict[str, float] = {}

        for row in r:
            d_obj = _parse_date_obj(row.get(date_col, "") or "")
            if not d_obj:
                continue

            try:
                v = float(row.get(value_col, ""))
            except Exception:
                continue

            by_date[d_obj.isoformat()] = v

    rows = [{"date": d, "mean": v} for d, v in by_date.items()]
    rows.sort(key=lambda x: x["date"])
    return rows


def _filter_calendar_window(rows: List[Dict[str, Any]], days: int) -> tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
    if not rows:
        return [], None, None

    days = max(1, int(days))
    latest_obj = _parse_date_obj(rows[-1]["date"])
    if not latest_obj:
        return rows, rows[-1]["date"], None

    start_obj = latest_obj - timedelta(days=days - 1)

    filtered = []
    for row in rows:
        d_obj = _parse_date_obj(row["date"])
        if not d_obj:
            continue
        if start_obj <= d_obj <= latest_obj:
            filtered.append(row)

    return filtered, latest_obj.isoformat(), start_obj.isoformat()


@router.get("/daily-mean")
def daily_mean(metric: str = "sst", days: int = 90):
    csv_path = _find_daily_mean_csv(metric)
    all_rows = _read_daily_mean_rows(csv_path)
    pts, latest_available_date, window_start_date = _filter_calendar_window(all_rows, int(days))

    return {
        "region": "Banda Aceh - Aceh Besar",
        "metric": metric,
        "days": int(days),
        "requested_days": int(days),
        "window_start_date": window_start_date,
        "latest_available_date": latest_available_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(csv_path),
        "source_file": csv_path.name,
        "points_count": len(pts),
        "note": "Calendar-window filter based on latest available date in series; missing dates may occur when source daily CSV has gaps.",
        "points": pts,
    }