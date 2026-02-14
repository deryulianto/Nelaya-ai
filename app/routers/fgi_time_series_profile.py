from pathlib import Path
from datetime import datetime, timezone
import csv
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

ROOT_DIR = Path(__file__).resolve().parents[2]
TS_DIR = ROOT_DIR / "data" / "time_series"

router = APIRouter(prefix="/api/v1/fgi/time-series", tags=["FGI Time Series"])

REGION_DEFAULT = "Banda Aceh - Aceh Besar"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_date(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    # normalize jadi YYYY-MM-DD bila memungkinkan
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).date().isoformat()
        except Exception:
            pass
    return s[:10]


def _read_csv_rows(p: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with p.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            return [], []
        rows = list(r)
        return list(r.fieldnames), rows


def _find_temp_profile_daily_csv(date: str) -> Optional[Path]:
    # lokasi yang kamu punya:
    # data/time_series/aceh/banda_aceh_aceh_besar/temp_profile/daily/temp_profile_daily_YYYY-MM-DD.csv
    date = date[:10]
    candidates: List[Path] = []
    if TS_DIR.exists():
        candidates += list(TS_DIR.rglob(f"temp_profile_daily_{date}.csv"))
        candidates += list(TS_DIR.rglob(f"*temp_profile*{date}*.csv"))
    if not candidates:
        return None
    # ambil yang paling spesifik (nama persis) kalau ada
    exact = [c for c in candidates if c.name == f"temp_profile_daily_{date}.csv"]
    if exact:
        return sorted(exact, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _find_temp_profile_series_csv() -> Optional[Path]:
    # series yang kamu punya:
    # data/time_series/**/temp_profile/series/temp_profile_daily_profile.csv
    candidates: List[Path] = []
    if TS_DIR.exists():
        candidates += list(TS_DIR.rglob("*temp_profile_daily_profile*.csv"))
        candidates += list(TS_DIR.rglob("*temp_profile*series*.csv"))
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _pick_col(cols: List[str], wanted: List[str]) -> Optional[str]:
    low = {c.lower(): c for c in cols}
    for w in wanted:
        if w in low:
            return low[w]
    return None


def _parse_points_long(rows: List[Dict[str, str]], cols: List[str], max_depth: int) -> List[Dict[str, Any]]:
    # format long: depth,temp
    depth_col = _pick_col(cols, ["depth_m", "depth", "z"])
    temp_col  = _pick_col(cols, ["temp_c", "temp", "temperature", "thetao", "value", "v"])
    if not depth_col or not temp_col:
        return []

    pts: List[Dict[str, Any]] = []
    for r in rows:
        try:
            z = float((r.get(depth_col) or "").strip())
            t = float((r.get(temp_col) or "").strip())
        except Exception:
            continue
        if z <= float(max_depth):
            pts.append({"depth_m": z, "temp_c": t})
    pts.sort(key=lambda x: x["depth_m"])
    return pts


def _parse_points_series(rows: List[Dict[str, str]], cols: List[str], date: str, max_depth: int) -> List[Dict[str, Any]]:
    # coba 2 kemungkinan:
    # A) long series: ada date_col + depth + temp
    date_col = _pick_col(cols, ["date", "day", "t", "time", "timestamp"])
    depth_col = _pick_col(cols, ["depth_m", "depth", "z"])
    temp_col  = _pick_col(cols, ["temp_c", "temp", "temperature", "thetao", "value", "v"])

    date = date[:10]

    if date_col and depth_col and temp_col:
        pts: List[Dict[str, Any]] = []
        for r in rows:
            d = _parse_date(r.get(date_col) or "")
            if d != date:
                continue
            try:
                z = float((r.get(depth_col) or "").strip())
                t = float((r.get(temp_col) or "").strip())
            except Exception:
                continue
            if z <= float(max_depth):
                pts.append({"depth_m": z, "temp_c": t})
        pts.sort(key=lambda x: x["depth_m"])
        return pts

    # B) wide series: 1 row per date, kolom lain mewakili kedalaman
    if date_col:
        target = None
        for r in rows:
            d = _parse_date(r.get(date_col) or "")
            if d == date:
                target = r
                break
        if not target:
            return []

        def parse_depth(col: str) -> Optional[float]:
            m = re.search(r"(\d+(\.\d+)?)", col)
            if not m:
                return None
            try:
                return float(m.group(1))
            except Exception:
                return None

        pts: List[Dict[str, Any]] = []
        for c in cols:
            if c == date_col:
                continue
            z = parse_depth(c.lower())
            if z is None or z > float(max_depth):
                continue
            try:
                t = float((target.get(c) or "").strip())
            except Exception:
                continue
            pts.append({"depth_m": z, "temp_c": t})
        pts.sort(key=lambda x: x["depth_m"])
        return pts

    return []


@router.get("/temp-profile")
def temp_profile(date: str, max_depth: int = 200, trace: Optional[str] = None):
    date = _parse_date(date)
    if not date:
        raise HTTPException(status_code=400, detail={"error": "bad_date"})

    # 1) PRIORITAS: daily csv untuk tanggal itu
    daily = _find_temp_profile_daily_csv(date)
    if daily and daily.exists():
        cols, rows = _read_csv_rows(daily)
        pts = _parse_points_long(rows, cols, int(max_depth))
        return {
            "region": REGION_DEFAULT,
            "date": date,
            "meta": {"generated_at": _now_iso(), "trace": trace},
            "note": "temp-profile served from DAILY CSV",
            "source": str(daily),
            "points": pts,
        }

    # 2) FALLBACK: series csv (ambil row tanggal tsb)
    series = _find_temp_profile_series_csv()
    if series and series.exists():
        cols, rows = _read_csv_rows(series)
        pts = _parse_points_series(rows, cols, date, int(max_depth))
        return {
            "region": REGION_DEFAULT,
            "date": date,
            "meta": {"generated_at": _now_iso(), "trace": trace},
            "note": "temp-profile served from SERIES CSV",
            "source": str(series),
            "points": pts,
        }

    # 3) kalau tidak ada apa-apa
    raise HTTPException(
        status_code=404,
        detail={
            "error": "temp_profile_csv_not_found",
            "searched_in": str(TS_DIR),
            "hint": "Cek data/time_series/**/temp_profile/daily/ atau series/",
        },
    )
