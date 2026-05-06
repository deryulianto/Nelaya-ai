#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NELAYA-AI FGI Temporal Memory Builder v0.7-alpha

Purpose:
- Build temporal memory from archived daily FGI Physics Support NetCDF files.
- This is the first foundation for FGI v0.7.

Inputs:
  data/physics/history/YYYY/MM/DD/fgi_physics_support_today.nc
  data/physics/history/YYYY/MM/DD/fgi_physics_support_today.json

Outputs:
  data/physics/fgi_temporal_memory_today.nc
  data/physics/fgi_temporal_memory_today.json
  data/physics/fgi_temporal_memory_preview.geojson

Main scores:
  - today_physics_support_score
  - weighted_physics_support_score
  - persistence_score
  - stability_score
  - temporal_memory_score
  - temporal_confidence
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import xarray as xr


os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


ROOT = Path(".")
PHYSICS_DIR = ROOT / "data" / "physics"
HISTORY_DIR = PHYSICS_DIR / "history"

SCORE_VAR = "fgi_physics_support_confidence_adjusted"


def to_builtin(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_builtin(v) for v in obj]
    if isinstance(obj, tuple):
        return [to_builtin(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    return obj


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def open_dataset_any(path: Path) -> xr.Dataset:
    engines = ["scipy", "netcdf4", "h5netcdf", None]
    errors = []

    for engine in engines:
        try:
            if engine is None:
                return xr.open_dataset(path, cache=False, decode_times=False)
            return xr.open_dataset(path, engine=engine, cache=False, decode_times=False)
        except Exception as exc:
            errors.append(f"{engine}: {type(exc).__name__}: {exc}")

    raise RuntimeError("Cannot open dataset: " + " | ".join(errors))


def sanitize_da(da: xr.DataArray, name: Optional[str] = None) -> xr.DataArray:
    da = da.squeeze(drop=True)

    if "lat" not in da.dims or "lon" not in da.dims:
        raise ValueError(f"Expected lat/lon dims, got {da.dims}")

    da = da.transpose("lat", "lon")

    return xr.DataArray(
        np.asarray(da.values, dtype=float),
        coords={
            "lat": np.asarray(da["lat"].values, dtype=float),
            "lon": np.asarray(da["lon"].values, dtype=float),
        },
        dims=("lat", "lon"),
        name=name or da.name,
        attrs=dict(da.attrs),
    )


def clip01(da: xr.DataArray) -> xr.DataArray:
    return xr.where(da < 0, 0, xr.where(da > 1, 1, da))


def safe_stats(da: xr.DataArray) -> Dict[str, Any]:
    arr = np.asarray(da.values, dtype=float)
    valid = arr[np.isfinite(arr)]

    if valid.size == 0:
        return {
            "count": 0,
            "nan_ratio": 1.0,
            "min": None,
            "p05": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p95": None,
            "max": None,
            "mean": None,
        }

    return {
        "count": int(valid.size),
        "nan_ratio": float(1.0 - valid.size / arr.size),
        "min": float(np.nanmin(valid)),
        "p05": float(np.nanpercentile(valid, 5)),
        "p25": float(np.nanpercentile(valid, 25)),
        "p50": float(np.nanpercentile(valid, 50)),
        "p75": float(np.nanpercentile(valid, 75)),
        "p95": float(np.nanpercentile(valid, 95)),
        "max": float(np.nanmax(valid)),
        "mean": float(np.nanmean(valid)),
    }


def estimate_resolution(coord: xr.DataArray) -> Optional[float]:
    vals = np.asarray(coord.values, dtype=float)
    vals = vals[np.isfinite(vals)]
    if vals.size < 2:
        return None

    diffs = np.diff(np.sort(np.unique(vals)))
    diffs = diffs[np.isfinite(diffs)]
    if diffs.size == 0:
        return None

    return float(np.nanmedian(np.abs(diffs)))


def list_history_entries(history_dir: Path) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []

    for year_dir in sorted(history_dir.glob("20??")):
        for month_dir in sorted(year_dir.glob("??")):
            for day_dir in sorted(month_dir.glob("??")):
                date = f"{year_dir.name}-{month_dir.name}-{day_dir.name}"
                nc = day_dir / "fgi_physics_support_today.nc"
                js = day_dir / "fgi_physics_support_today.json"
                manifest = day_dir / "manifest.json"

                if nc.exists():
                    entries.append(
                        {
                            "date": date,
                            "dir": str(day_dir),
                            "nc": str(nc),
                            "json": str(js) if js.exists() else None,
                            "manifest": str(manifest) if manifest.exists() else None,
                        }
                    )

    return sorted(entries, key=lambda e: e["date"])


def load_score_for_entry(entry: Dict[str, Any], target: Optional[xr.DataArray] = None) -> xr.DataArray:
    ds = open_dataset_any(Path(entry["nc"]))

    if SCORE_VAR not in ds:
        raise KeyError(f"{SCORE_VAR} not found in {entry['nc']}. Available={list(ds.data_vars)}")

    da = sanitize_da(ds[SCORE_VAR], name=SCORE_VAR)

    if target is not None:
        da = da.interp(lat=target["lat"], lon=target["lon"], method="nearest")
        da = sanitize_da(da, name=SCORE_VAR)

    return da


def normalized_weights(n: int, half_life: float = 2.0) -> np.ndarray:
    # entries are chronological oldest -> newest
    # newest gets highest weight.
    ages = np.arange(n - 1, -1, -1, dtype=float)
    weights = np.exp(-np.log(2.0) * ages / half_life)
    weights = weights / np.sum(weights)
    return weights


def bearing_between(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
    try:
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dlon = math.radians(lon2 - lon1)

        x = math.sin(dlon) * math.cos(phi2)
        y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)

        brng = (math.degrees(math.atan2(x, y)) + 360.0) % 360.0
        return brng
    except Exception:
        return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
    try:
        r = 6371.0
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)

        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return r * c
    except Exception:
        return None


def direction_label_id(deg: Optional[float]) -> Optional[str]:
    if deg is None:
        return None
    labels = [
        "utara",
        "timur_laut",
        "timur",
        "tenggara",
        "selatan",
        "barat_daya",
        "barat",
        "barat_laut",
    ]
    idx = int(((deg + 22.5) % 360) // 45)
    return labels[idx]


def weighted_centroid(da: xr.DataArray, threshold: float) -> Optional[Dict[str, Any]]:
    arr = np.asarray(da.values, dtype=float)
    lat = np.asarray(da["lat"].values, dtype=float)
    lon = np.asarray(da["lon"].values, dtype=float)

    mask = np.isfinite(arr) & (arr >= threshold)
    if not np.any(mask):
        return None

    weights = np.where(mask, arr, 0.0)
    total = float(np.nansum(weights))

    if total <= 0:
        return None

    lat_grid, lon_grid = np.meshgrid(lat, lon, indexing="ij")

    return {
        "lat": float(np.nansum(lat_grid * weights) / total),
        "lon": float(np.nansum(lon_grid * weights) / total),
        "total_weight": total,
        "cell_count": int(np.sum(mask)),
        "threshold": threshold,
    }


def movement_consistency_score(
    centroid_history: List[Dict[str, Any]],
    current_direction_deg: Optional[float],
) -> Dict[str, Any]:
    if len(centroid_history) < 2:
        return {
            "available": False,
            "reason": "Need at least 2 centroids.",
            "movement_consistency_score": None,
        }

    last = centroid_history[-1]
    prev = centroid_history[-2]

    bearing = bearing_between(prev["lat"], prev["lon"], last["lat"], last["lon"])
    distance = haversine_km(prev["lat"], prev["lon"], last["lat"], last["lon"])

    if bearing is None or current_direction_deg is None:
        return {
            "available": False,
            "reason": "Missing bearing or current direction.",
            "centroid_shift_bearing_deg": bearing,
            "centroid_shift_km": distance,
            "movement_consistency_score": None,
        }

    diff = abs((bearing - current_direction_deg + 180) % 360 - 180)
    score = (1.0 + math.cos(math.radians(diff))) / 2.0

    return {
        "available": True,
        "centroid_shift_km": distance,
        "centroid_shift_bearing_deg": bearing,
        "centroid_shift_direction_label": direction_label_id(bearing),
        "current_direction_deg": current_direction_deg,
        "current_direction_label": direction_label_id(current_direction_deg),
        "angle_difference_deg": diff,
        "movement_consistency_score": score,
        "note": "Score close to 1 means centroid shift broadly aligns with mean current direction.",
    }


def top_cells(ds: xr.Dataset, var_name: str, n: int = 10) -> List[Dict[str, Any]]:
    da = ds[var_name]
    arr = np.asarray(da.values, dtype=float)
    lat_vals = np.asarray(ds["lat"].values, dtype=float)
    lon_vals = np.asarray(ds["lon"].values, dtype=float)

    flat = arr.ravel()
    valid_idx = np.where(np.isfinite(flat))[0]

    if valid_idx.size == 0:
        return []

    valid_scores = flat[valid_idx]
    order = np.argsort(valid_scores)[::-1][:n]
    selected = valid_idx[order]

    rows = []
    ny, nx = arr.shape

    for idx in selected:
        i = idx // nx
        j = idx % nx

        row = {
            "rank": len(rows) + 1,
            "lat": float(lat_vals[i]),
            "lon": float(lon_vals[j]),
            var_name: safe_float(arr[i, j], None),
        }

        for extra in [
            "today_physics_support_score",
            "weighted_physics_support_score",
            "persistence_score",
            "stability_score",
            "temporal_confidence",
        ]:
            if extra in ds:
                row[extra] = safe_float(ds[extra].values[i, j], None)

        rows.append(row)

    return rows


def make_geojson(ds: xr.Dataset, out_file: Path, threshold: float, max_points: int) -> Dict[str, Any]:
    score_var = "temporal_memory_confidence_adjusted" if "temporal_memory_confidence_adjusted" in ds else "temporal_memory_score"
    score = ds[score_var]
    arr = np.asarray(score.values, dtype=float)
    lat_vals = np.asarray(ds["lat"].values, dtype=float)
    lon_vals = np.asarray(ds["lon"].values, dtype=float)

    valid = np.where(np.isfinite(arr) & (arr >= threshold))

    rows = []
    for i, j in zip(valid[0], valid[1]):
        rows.append(
            {
                "lat": float(lat_vals[i]),
                "lon": float(lon_vals[j]),
                "temporal_memory_score": safe_float(arr[i, j], 0.0),
                "today_physics_support_score": safe_float(ds["today_physics_support_score"].values[i, j], None),
                "weighted_physics_support_score": safe_float(ds["weighted_physics_support_score"].values[i, j], None),
                "persistence_score": safe_float(ds["persistence_score"].values[i, j], None),
                "stability_score": safe_float(ds["stability_score"].values[i, j], None),
                "temporal_confidence": safe_float(ds["temporal_confidence"].values[i, j], None),
            }
        )

    rows = sorted(rows, key=lambda x: x["temporal_memory_score"] or 0.0, reverse=True)[:max_points]

    features = []
    for r in rows:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [r["lon"], r["lat"]],
                },
                "properties": {
                    "score_var": score_var,
                    score_var: r["temporal_memory_score"],
                    "today_physics_support_score": r["today_physics_support_score"],
                    "weighted_physics_support_score": r["weighted_physics_support_score"],
                    "persistence_score": r["persistence_score"],
                    "stability_score": r["stability_score"],
                    "temporal_confidence": r["temporal_confidence"],
                    "label": "FGI v0.7 temporal memory candidate",
                    "note": "GeoJSON uses confidence-adjusted temporal memory when available.",
                },
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "name": "NELAYA-AI FGI Temporal Memory Preview",
        "features": features,
    }

    out_file.write_text(json.dumps(to_builtin(geojson), indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "created": True,
        "file": str(out_file),
        "threshold": threshold,
        "point_count": len(features),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="NELAYA-AI-LAB root.")
    parser.add_argument("--window-days", type=int, default=5)
    parser.add_argument("--active-threshold", type=float, default=0.22)
    parser.add_argument("--geojson-threshold", type=float, default=0.25)
    parser.add_argument("--max-points", type=int, default=300)
    parser.add_argument("--half-life", type=float, default=2.0)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    physics_dir = root / "data" / "physics"
    history_dir = physics_dir / "history"

    entries = list_history_entries(history_dir)

    if not entries:
        raise SystemExit(
            f"No history entries found in {history_dir}. "
            "Run scripts/archive_daily_physics_outputs.py first."
        )

    selected = entries[-args.window_days :]

    print("=" * 78)
    print("NELAYA-AI FGI Temporal Memory Builder v0.7-alpha")
    print("=" * 78)
    print(f"History entries found : {len(entries)}")
    print(f"Window days requested : {args.window_days}")
    print(f"Window days used      : {len(selected)}")
    print(f"Active threshold      : {args.active_threshold}")
    print(f"GeoJSON threshold     : {args.geojson_threshold}")

    target = load_score_for_entry(selected[-1])
    layers: List[xr.DataArray] = []
    centroid_history: List[Dict[str, Any]] = []
    source_dates: List[str] = []

    dynamic_current_direction = None

    for entry in selected:
        date = entry["date"]
        source_dates.append(date)

        da = load_score_for_entry(entry, target=target)
        da = da.rename(f"score_{date.replace('-', '')}")
        layers.append(da)

        centroid = weighted_centroid(da, threshold=args.active_threshold)
        if centroid:
            centroid["date"] = date
            centroid_history.append(centroid)

        js = read_json(Path(entry["json"])) if entry.get("json") else {}
        maybe_dir = (
            js.get("summary_metrics", {})
            .get("dynamic_mean_current_direction_deg")
        )
        if maybe_dir is not None:
            dynamic_current_direction = maybe_dir

    stack = xr.concat(layers, dim="time")
    stack = stack.assign_coords(time=np.arange(len(layers)))

    weights = normalized_weights(len(layers), half_life=args.half_life)

    weighted = xr.zeros_like(target, dtype=float)
    valid_weight_sum = xr.zeros_like(target, dtype=float)

    for idx, w in enumerate(weights):
        layer = stack.isel(time=idx)
        valid = xr.where(np.isfinite(layer), 1.0, 0.0)
        weighted = weighted + layer.fillna(0) * float(w)
        valid_weight_sum = valid_weight_sum + valid * float(w)

    weighted_score = xr.where(valid_weight_sum > 0, weighted / valid_weight_sum, np.nan)
    weighted_score.name = "weighted_physics_support_score"

    today_score = stack.isel(time=-1)
    today_score = today_score.rename("today_physics_support_score")

    active = xr.where(stack >= args.active_threshold, 1.0, 0.0)
    finite = xr.where(np.isfinite(stack), 1.0, 0.0)
    persistence = xr.where(finite.sum(dim="time") > 0, active.sum(dim="time") / finite.sum(dim="time"), np.nan)
    persistence.name = "persistence_score"

    mean_score = stack.mean(dim="time", skipna=True)
    std_score = stack.std(dim="time", skipna=True)

    stability = xr.where(
        np.isfinite(mean_score),
        1.0 - (std_score / (mean_score + 0.05)),
        np.nan,
    )
    stability = clip01(stability)
    stability.name = "stability_score"

    # With only one historical day, stability becomes 1.0 but temporal confidence remains low.
    temporal_memory = clip01(
        0.45 * weighted_score
        + 0.35 * persistence
        + 0.20 * stability
    )
    temporal_memory.name = "temporal_memory_score"

    finite_coverage = finite.mean(dim="time")
    window_factor = min(1.0, len(layers) / max(1, args.window_days))

    temporal_confidence = clip01(
        (0.60 * finite_coverage + 0.40 * window_factor)
    )
    temporal_confidence.name = "temporal_confidence"

    # v0.7-alpha.1 maturity-aware adjustment:
    # raw temporal memory can look strong with only one archived day because
    # persistence and stability are trivially high. This adjusted score reduces
    # overconfidence until the historical window becomes mature.
    history_maturity_factor = min(1.0, len(layers) / max(1, args.window_days))

    temporal_memory_confidence_adjusted = clip01(
        temporal_memory
        * (0.35 + 0.65 * temporal_confidence)
        * (0.50 + 0.50 * history_maturity_factor)
    )
    temporal_memory_confidence_adjusted.name = "temporal_memory_confidence_adjusted"
    temporal_memory_confidence_adjusted.attrs = {
        "long_name": "Confidence-adjusted temporal memory score",
        "units": "0-1",
        "note": "Reduces overconfidence when temporal history is still short.",
    }

    movement = movement_consistency_score(
        centroid_history=centroid_history,
        current_direction_deg=dynamic_current_direction,
    )

    ds_out = xr.Dataset(
        {
            "today_physics_support_score": sanitize_da(today_score, "today_physics_support_score"),
            "weighted_physics_support_score": sanitize_da(weighted_score, "weighted_physics_support_score"),
            "persistence_score": sanitize_da(persistence, "persistence_score"),
            "stability_score": sanitize_da(stability, "stability_score"),
            "temporal_memory_score": sanitize_da(temporal_memory, "temporal_memory_score"),
            "temporal_memory_confidence_adjusted": sanitize_da(
                temporal_memory_confidence_adjusted,
                "temporal_memory_confidence_adjusted",
            ),
            "temporal_confidence": sanitize_da(temporal_confidence, "temporal_confidence"),
        }
    )

    ds_out.attrs = {
        "module": "nelaya_ai_fgi_temporal_memory",
        "version": "0.7-alpha",
        "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "source_dates": json.dumps(source_dates),
        "window_days_requested": args.window_days,
        "window_days_used": len(selected),
        "active_threshold": args.active_threshold,
        "note": (
            "Temporal memory layer for FGI v0.7. "
            "This is a memory-support layer, not direct fish abundance prediction."
        ),
    }

    nc_out = physics_dir / "fgi_temporal_memory_today.nc"
    json_out = physics_dir / "fgi_temporal_memory_today.json"
    geojson_out = physics_dir / "fgi_temporal_memory_preview.geojson"

    ds_out.to_netcdf(nc_out, engine="scipy")

    geojson_info = make_geojson(
        ds=ds_out,
        out_file=geojson_out,
        threshold=args.geojson_threshold,
        max_points=args.max_points,
    )

    top_temporal = top_cells(ds_out, "temporal_memory_score", n=10)

    summary = {
        "module": "nelaya_ai_fgi_temporal_memory",
        "version": "0.7-alpha",
        "status": "ready",
        "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "source_dates": source_dates,
        "window_days_requested": args.window_days,
        "window_days_used": len(selected),
        "active_threshold": args.active_threshold,
        "outputs": {
            "netcdf": str(nc_out),
            "summary_json": str(json_out),
            "geojson": geojson_info,
        },
        "grid": {
            "lat_size": int(ds_out.sizes["lat"]),
            "lon_size": int(ds_out.sizes["lon"]),
            "resolution_deg": {
                "lat": estimate_resolution(ds_out["lat"]),
                "lon": estimate_resolution(ds_out["lon"]),
            },
        },
        "weights": {
            "recency_weights_oldest_to_newest": [float(w) for w in weights],
            "half_life_days": args.half_life,
            "temporal_memory_score": {
                "weighted_physics_support_score": 0.45,
                "persistence_score": 0.35,
                "stability_score": 0.20,
            },
        },
        "summary_metrics": {
            "mean_temporal_memory_score": safe_stats(ds_out["temporal_memory_score"])["mean"],
            "max_temporal_memory_score": safe_stats(ds_out["temporal_memory_score"])["max"],
            "mean_persistence_score": safe_stats(ds_out["persistence_score"])["mean"],
            "mean_stability_score": safe_stats(ds_out["stability_score"])["mean"],
            "mean_temporal_confidence": safe_stats(ds_out["temporal_confidence"])["mean"],
            "mean_temporal_memory_confidence_adjusted": safe_stats(ds_out["temporal_memory_confidence_adjusted"])["mean"],
            "max_temporal_memory_confidence_adjusted": safe_stats(ds_out["temporal_memory_confidence_adjusted"])["max"],
            "history_maturity_factor": history_maturity_factor,
        },
        "stats": {
            "today_physics_support_score": safe_stats(ds_out["today_physics_support_score"]),
            "weighted_physics_support_score": safe_stats(ds_out["weighted_physics_support_score"]),
            "persistence_score": safe_stats(ds_out["persistence_score"]),
            "stability_score": safe_stats(ds_out["stability_score"]),
            "temporal_memory_score": safe_stats(ds_out["temporal_memory_score"]),
            "temporal_confidence": safe_stats(ds_out["temporal_confidence"]),
            "temporal_memory_confidence_adjusted": safe_stats(ds_out["temporal_memory_confidence_adjusted"]),
        },
        "centroid_history": centroid_history,
        "movement_consistency": movement,
        "top_cells": {
            "temporal_memory_score": top_temporal,
            "temporal_memory_confidence_adjusted": top_cells(ds_out, "temporal_memory_confidence_adjusted", n=10),
        },
        "interpretation": {
            "what_this_means": (
                "This layer tells whether today's physics support is part of a recent temporal pattern "
                "or only a one-day signal."
            ),
            "scientific_caution": (
                "Temporal memory quality depends on the number of archived days. "
                "With only one day, the score is preliminary and confidence must be interpreted cautiously."
            ),
            "recommended_next_step": (
                "Archive daily outputs for several days, then fuse temporal_memory_score into FGI v0.7."
            ),
        },
    }

    json_out.write_text(json.dumps(to_builtin(summary), indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 78)
    print("DONE")
    print("=" * 78)
    print(f"NetCDF  : {nc_out}")
    print(f"Summary : {json_out}")
    print(f"GeoJSON : {geojson_out}")
    print("")
    print("Summary metrics:")
    print(json.dumps(to_builtin(summary["summary_metrics"]), indent=2, ensure_ascii=False))
    print("")
    print("Top temporal memory cells:")
    print(json.dumps(to_builtin(top_temporal[:5]), indent=2, ensure_ascii=False))
    print("=" * 78)


if __name__ == "__main__":
    main()
