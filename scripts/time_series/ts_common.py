from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Any

import yaml  # type: ignore


@dataclass
class BBox:
    min_lon: float
    max_lon: float
    min_lat: float
    max_lat: float


@dataclass
class VarSpec:
    # generic var key
    key: str

    # dataset ids
    dataset_id: Optional[str] = None
    dataset_id_my: Optional[str] = None
    dataset_id_nrt: Optional[str] = None

    # variable names
    var_name: Optional[str] = None
    var_u: Optional[str] = None
    var_v: Optional[str] = None

    # extras
    unit: Optional[str] = None
    depth_m: Optional[float] = None  # ✅ untuk temp50 dst


@dataclass
class TimeSeriesConfig:
    region: str
    base_dir: Path
    raw_dirname: str
    daily_dirname: str
    series_dirname: str
    source_name: str
    default_lag_days: int
    bbox: BBox
    vars: Dict[str, VarSpec]


def load_config(path: str) -> TimeSeriesConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    bbox_raw = raw.get("bbox") or {}
    bbox = BBox(
        min_lon=float(bbox_raw.get("min_lon")),
        max_lon=float(bbox_raw.get("max_lon")),
        min_lat=float(bbox_raw.get("min_lat")),
        max_lat=float(bbox_raw.get("max_lat")),
    )

    vars_raw: Dict[str, Any] = raw.get("vars") or {}
    vars_out: Dict[str, VarSpec] = {}

    for key, v in vars_raw.items():
        v = v or {}
        vars_out[str(key)] = VarSpec(
            key=str(key),
            dataset_id=v.get("dataset_id"),
            dataset_id_my=v.get("dataset_id_my"),
            dataset_id_nrt=v.get("dataset_id_nrt"),
            var_name=v.get("var_name"),
            var_u=v.get("var_u"),
            var_v=v.get("var_v"),
            unit=v.get("unit"),
            depth_m=v.get("depth_m"),
        )

    return TimeSeriesConfig(
        region=str(raw.get("region") or "Aceh"),
        base_dir=Path(str(raw.get("base_dir") or "data/time_series")),
        raw_dirname=str(raw.get("raw_dirname") or "raw"),
        daily_dirname=str(raw.get("daily_dirname") or "daily"),
        series_dirname=str(raw.get("series_dirname") or "series"),
        source_name=str(raw.get("source_name") or "Copernicus Marine Service (CMEMS)"),
        default_lag_days=int(raw.get("default_lag_days") or 1),
        bbox=bbox,
        vars=vars_out,
    )


def ensure_dirs(cfg: TimeSeriesConfig, var_key: str) -> Dict[str, Path]:
    base = cfg.base_dir / var_key
    raw_dir = base / cfg.raw_dirname
    daily_dir = base / cfg.daily_dirname
    series_dir = base / cfg.series_dirname
    raw_dir.mkdir(parents=True, exist_ok=True)
    daily_dir.mkdir(parents=True, exist_ok=True)
    series_dir.mkdir(parents=True, exist_ok=True)
    return {"base": base, "raw": raw_dir, "daily": daily_dir, "series": series_dir}
