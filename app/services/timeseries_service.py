from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from statistics import mean

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
TS_ROOT = ROOT / "data" / "time_series" / "aceh"


REGION_FOLDER_MAP = {
    "banda aceh": "banda_aceh_aceh_besar",
    "aceh besar": "banda_aceh_aceh_besar",
    "banda aceh, aceh besar": "banda_aceh_aceh_besar",
}

METRIC_FILE_MAP = {
    "sst": ("sst", "series", "sst_daily_mean.csv"),
    "chlorophyll": ("chlorophyll", "series", "chlorophyll_daily_mean.csv"),
    "current": ("current", "series", "current_daily_mean.csv"),
    # alias tambahan
    "chl": ("chlorophyll", "series", "chlorophyll_daily_mean.csv"),
}


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _resolve_region_folder(region: Optional[str]) -> Optional[Path]:
    if not region:
        return None

    key = _norm(region)
    folder = REGION_FOLDER_MAP.get(key)
    if not folder:
        return None

    p = TS_ROOT / folder
    return p if p.exists() else None


def _resolve_metric_file(region: Optional[str], metric: str) -> Optional[Path]:
    region_dir = _resolve_region_folder(region)
    if not region_dir:
        return None

    metric_key = _norm(metric)
    spec = METRIC_FILE_MAP.get(metric_key)
    if not spec:
        return None

    p = region_dir.joinpath(*spec)
    return p if p.exists() else None


def _load_metric_rows(region: Optional[str], metric: str) -> List[Dict[str, Any]]:
    path = _resolve_metric_file(region, metric)
    if not path:
        return []

    try:
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
        else:
            df = pd.read_excel(path)
    except Exception:
        return []

    norm_cols = {str(c).strip().lower(): c for c in df.columns}

    date_col = None
    mean_col = None

    for cand in ["date", "tanggal", "day"]:
        if cand in norm_cols:
            date_col = norm_cols[cand]
            break

    for cand in ["mean", "value", "avg", "average"]:
        if cand in norm_cols:
            mean_col = norm_cols[cand]
            break

    if date_col is None or mean_col is None:
        return []

    rows: List[Dict[str, Any]] = []

    for _, r in df.iterrows():
        try:
            d = r[date_col]
            v = r[mean_col]

            if pd.isna(d) or pd.isna(v):
                continue

            d = pd.to_datetime(d).date().isoformat()
            v = float(v)

            rows.append({
                "date": d,
                "value": v,
            })
        except Exception:
            continue

    return rows

def _metric_label(metric: str) -> str:
    return {
        "sst": "suhu laut",
        "chlorophyll": "klorofil",
        "chl": "klorofil",
        "current": "arus laut",
        "wave": "gelombang",
        "wind": "angin",
    }.get(metric, metric)


def get_trend_summary(region: Optional[str], metric: str) -> Dict[str, Any]:
    rows = _load_metric_rows(region, metric)

    if not rows:
        return {
            "metric": metric,
            "trend": "unknown",
            "latest": None,
            "avg_7d": None,
            "anomaly_vs_7d": None,
            "count": 0,
            "source_type": "csv_timeseries",
        }

    rows.sort(key=lambda x: x["date"])

    latest = rows[-1]["value"]
    last_7 = [x["value"] for x in rows[-7:]]
    avg_7d = mean(last_7) if last_7 else None

    anomaly = None
    if avg_7d is not None and latest is not None:
        anomaly = latest - avg_7d

    trend = "stabil"
    if anomaly is not None:
        if anomaly > 0.05:
            trend = "naik"
        elif anomaly < -0.05:
            trend = "turun"

    return {
        "metric": metric,
        "trend": trend,
        "latest": latest,
        "avg_7d": avg_7d,
        "anomaly_vs_7d": anomaly,
        "count": len(rows),
        "source_type": "csv_timeseries",
        "latest_date": rows[-1]["date"],
    }


def compare_this_week_vs_last_week(region: Optional[str], metric: str) -> Dict[str, Any]:
    rows = _load_metric_rows(region, metric)

    if len(rows) < 14:
        return {
            "metric": metric,
            "this_week_avg": None,
            "last_week_avg": None,
            "delta": None,
            "direction": "unknown",
            "enough_data": False,
            "source_type": "csv_timeseries",
        }

    rows.sort(key=lambda x: x["date"])

    this_week = [x["value"] for x in rows[-7:]]
    last_week = [x["value"] for x in rows[-14:-7]]

    if not this_week or not last_week:
        return {
            "metric": metric,
            "this_week_avg": None,
            "last_week_avg": None,
            "delta": None,
            "direction": "unknown",
            "enough_data": False,
            "source_type": "csv_timeseries",
        }

    this_week_avg = mean(this_week)
    last_week_avg = mean(last_week)
    delta = this_week_avg - last_week_avg

    direction = "stabil"
    if delta > 0.05:
        direction = "naik"
    elif delta < -0.05:
        direction = "turun"

    return {
        "metric": metric,
        "this_week_avg": this_week_avg,
        "last_week_avg": last_week_avg,
        "delta": delta,
        "direction": direction,
        "enough_data": True,
        "source_type": "csv_timeseries",
        "latest_date": rows[-1]["date"],
    }


def compare_today_vs_yesterday(region: Optional[str], metric: str) -> Dict[str, Any]:
    rows = _load_metric_rows(region, metric)

    if len(rows) < 2:
        return {
            "metric": metric,
            "today": None,
            "yesterday": None,
            "delta": None,
            "direction": "unknown",
            "enough_data": False,
            "source_type": "csv_timeseries",
        }

    rows.sort(key=lambda x: x["date"])

    today_v = rows[-1]["value"]
    yday_v = rows[-2]["value"]
    delta = today_v - yday_v

    direction = "stabil"
    if delta > 0.05:
        direction = "naik"
    elif delta < -0.05:
        direction = "turun"

    return {
        "metric": metric,
        "today": today_v,
        "yesterday": yday_v,
        "delta": delta,
        "direction": direction,
        "enough_data": True,
        "source_type": "csv_timeseries",
        "latest_date": rows[-1]["date"],
    }