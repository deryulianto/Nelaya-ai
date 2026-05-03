#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NELAYA-AI Ocean Dynamic Physics Layer v0.1

Purpose:
- Build daily dynamic physics features from:
  current uo/vo, SSH zos, SST thetao, CHL, wave VHM0, wind eastward/northward.
- Regrid all variables to the static bathymetry physics grid.
- Compute:
  current_speed_ms
  current_direction_deg
  vorticity_s-1
  divergence_s-1
  convergence_score
  vorticity_score
  sst_front_score
  chl_front_score
  ssh_gradient_score
  front_score
  dynamic_physics_score
  physics_confidence

Inputs:
- data/physics/dynamic_inputs_report.json
- data/physics/bathymetry_features_aceh.nc

Outputs:
- data/physics/ocean_dynamic_physics_today.nc
- data/physics/ocean_dynamic_physics_today.json
- data/physics/ocean_dynamic_front_preview.geojson

Notes:
- This is NOT a Navier-Stokes solver.
- It is a diagnostic physics layer derived from operational ocean variables.
- It prepares NELAYA-AI for Physics-informed FGI.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import xarray as xr


os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


DEFAULT_REPORT = Path("data/physics/dynamic_inputs_report.json")
DEFAULT_BATHY = Path("data/physics/bathymetry_features_aceh.nc")
DEFAULT_OUT = Path("data/physics")


EXPLICIT_VARS = {
    "current_u": "uo",
    "current_v": "vo",
    "ssh": "zos",
    "sst": "thetao",
    "chl": "CHL",
    "wave": "VHM0",
    "wind_u": "eastward_wind",
    "wind_v": "northward_wind",
}


LAT_NAMES = ["lat", "latitude", "nav_lat", "y"]
LON_NAMES = ["lon", "longitude", "nav_lon", "x"]


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


def open_dataset_any(path: Path) -> xr.Dataset:
    engines = ["scipy", "netcdf4", "h5netcdf", None]
    errors = []

    for engine in engines:
        try:
            if engine is None:
                return xr.open_dataset(path, cache=False, decode_times=False)
            return xr.open_dataset(path, engine=engine, cache=False, decode_times=False)
        except Exception as e:
            errors.append(f"{engine}: {type(e).__name__}: {e}")

    raise RuntimeError(
        "Cannot open dataset with scipy/netcdf4/h5netcdf/auto. "
        + " | ".join(errors)
    )


def find_coord_name(ds: xr.Dataset, candidates: List[str]) -> Optional[str]:
    names = list(ds.coords) + list(ds.dims) + list(ds.variables)

    for c in candidates:
        for n in names:
            if str(n) == c:
                return str(n)

    for c in candidates:
        c_low = c.lower()
        for n in names:
            if str(n).lower() == c_low:
                return str(n)

    return None


def standardize_lat_lon(ds: xr.Dataset) -> xr.Dataset:
    lat_name = find_coord_name(ds, LAT_NAMES)
    lon_name = find_coord_name(ds, LON_NAMES)

    if lat_name is None or lon_name is None:
        raise ValueError(f"Cannot detect lat/lon coords. coords={list(ds.coords)}, dims={list(ds.dims)}")

    rename = {}
    if lat_name != "lat":
        rename[lat_name] = "lat"
    if lon_name != "lon":
        rename[lon_name] = "lon"

    if rename:
        ds = ds.rename(rename)

    if float(ds["lon"].max()) > 180:
        ds = ds.assign_coords(lon=(((ds["lon"] + 180) % 360) - 180))
        ds = ds.sortby("lon")

    if ds["lat"].values[0] > ds["lat"].values[-1]:
        ds = ds.sortby("lat")

    return ds

def sanitize_grid_da(da: xr.DataArray, name: Optional[str] = None) -> xr.DataArray:
    """
    Force a DataArray to become a clean 2D lat/lon grid.

    Why:
    - Operational NetCDF files often retain scalar coords such as time/depth.
    - Different files have different time values.
    - If not removed, xr.Dataset merge can fail with:
      MergeError: conflicting values for variable 'time'
    """
    da = da.squeeze(drop=True)

    if "lat" not in da.dims or "lon" not in da.dims:
        raise ValueError(f"Expected lat/lon dims after squeeze, got dims={da.dims}")

    da = da.transpose("lat", "lon")

    attrs = dict(da.attrs)

    clean = xr.DataArray(
        np.asarray(da.values, dtype=float),
        coords={
            "lat": np.asarray(da["lat"].values, dtype=float),
            "lon": np.asarray(da["lon"].values, dtype=float),
        },
        dims=("lat", "lon"),
        name=name or da.name,
        attrs=attrs,
    )

    return clean



def get_var(ds: xr.Dataset, var_name: str, kind: str) -> xr.DataArray:
    if var_name not in ds.data_vars and var_name not in ds.variables:
        raise KeyError(f"Variable {var_name!r} not found for {kind}. Available: {list(ds.data_vars)}")

    da = ds[var_name]

    # Reduce to 2D lat/lon.
    # Common dims: time, depth, latitude, longitude
    for dim in list(da.dims):
        if dim not in ["lat", "lon"]:
            da = da.isel({dim: 0})

    # Drop scalar coords that can disturb later merge.
    da = da.squeeze(drop=True)

    if "lat" not in da.dims or "lon" not in da.dims:
        raise ValueError(f"{kind}:{var_name} is not 2D lat/lon after squeeze. dims={da.dims}")

    return sanitize_grid_da(da, name=var_name).astype("float64")


def maybe_convert_sst_to_celsius(da: xr.DataArray) -> xr.DataArray:
    arr = np.asarray(da.values, dtype=float)
    valid = arr[np.isfinite(arr)]

    if valid.size == 0:
        return da

    med = float(np.nanmedian(valid))

    # Kelvin-like ocean SST.
    if med > 100:
        out = da - 273.15
        out.attrs.update(da.attrs)
        out.attrs["converted_to"] = "degree_C"
        out.attrs["conversion_note"] = "Median value suggested Kelvin; subtracted 273.15."
        return out

    da.attrs["converted_to"] = "degree_C_assumed"
    return da


def clean_chl(da: xr.DataArray) -> xr.DataArray:
    # CHL must be positive for log-front analysis.
    out = xr.where(da > 0, da, np.nan)
    out.attrs.update(da.attrs)
    out.attrs["cleaning_note"] = "Non-positive CHL values converted to NaN."
    return out


def interp_to_target(da: xr.DataArray, target_lat: xr.DataArray, target_lon: xr.DataArray) -> xr.DataArray:
    da = da.sortby("lat").sortby("lon")

    try:
        out = da.interp(lat=target_lat, lon=target_lon, method="linear")
    except Exception:
        out = da.interp(lat=target_lat, lon=target_lon, method="nearest")

    # If linear left many NaNs, fill with nearest.
    arr = np.asarray(out.values, dtype=float)
    nan_ratio = float(np.mean(~np.isfinite(arr)))

    if nan_ratio > 0.5:
        nearest = da.interp(lat=target_lat, lon=target_lon, method="nearest")
        out = out.where(np.isfinite(out), nearest)

    return sanitize_grid_da(out, name=da.name)


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


def dx_dy_m(lat: xr.DataArray, lon: xr.DataArray) -> Tuple[float, float]:
    lat_res = estimate_resolution(lat)
    lon_res = estimate_resolution(lon)

    if lat_res is None or lon_res is None:
        raise ValueError("Cannot estimate grid resolution.")

    mean_lat = float(np.nanmean(lat.values))

    dy = lat_res * 111_320.0
    dx = lon_res * 111_320.0 * max(0.1, math.cos(math.radians(mean_lat)))

    return dx, dy


def fill_for_gradient(arr: np.ndarray) -> np.ndarray:
    valid = arr[np.isfinite(arr)]

    if valid.size == 0:
        return arr

    fill = float(np.nanmedian(valid))
    return np.where(np.isfinite(arr), arr, fill)


def gradient_components(da: xr.DataArray) -> Tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    """
    Return:
      grad_x, grad_y, grad_magnitude
    Units:
      da unit per meter.
    """
    dx, dy = dx_dy_m(da["lat"], da["lon"])

    arr = np.asarray(da.values, dtype=float)
    arr_filled = fill_for_gradient(arr)

    grad_y, grad_x = np.gradient(arr_filled, dy, dx)
    grad_mag = np.sqrt(grad_x**2 + grad_y**2)

    mask = np.isfinite(arr)

    grad_x = np.where(mask, grad_x, np.nan)
    grad_y = np.where(mask, grad_y, np.nan)
    grad_mag = np.where(mask, grad_mag, np.nan)

    gx = xr.DataArray(grad_x, coords=da.coords, dims=da.dims)
    gy = xr.DataArray(grad_y, coords=da.coords, dims=da.dims)
    gm = xr.DataArray(grad_mag, coords=da.coords, dims=da.dims)

    return gx, gy, gm


def vector_derivatives(u: xr.DataArray, v: xr.DataArray) -> Dict[str, xr.DataArray]:
    dx, dy = dx_dy_m(u["lat"], u["lon"])

    u_arr = np.asarray(u.values, dtype=float)
    v_arr = np.asarray(v.values, dtype=float)

    common_mask = np.isfinite(u_arr) & np.isfinite(v_arr)

    u_fill = fill_for_gradient(u_arr)
    v_fill = fill_for_gradient(v_arr)

    dudy, dudx = np.gradient(u_fill, dy, dx)
    dvdy, dvdx = np.gradient(v_fill, dy, dx)

    dudy = np.where(common_mask, dudy, np.nan)
    dudx = np.where(common_mask, dudx, np.nan)
    dvdy = np.where(common_mask, dvdy, np.nan)
    dvdx = np.where(common_mask, dvdx, np.nan)

    divergence = dudx + dvdy
    vorticity = dvdx - dudy

    return {
        "dudx": xr.DataArray(dudx, coords=u.coords, dims=u.dims),
        "dudy": xr.DataArray(dudy, coords=u.coords, dims=u.dims),
        "dvdx": xr.DataArray(dvdx, coords=u.coords, dims=u.dims),
        "dvdy": xr.DataArray(dvdy, coords=u.coords, dims=u.dims),
        "divergence": xr.DataArray(divergence, coords=u.coords, dims=u.dims),
        "vorticity": xr.DataArray(vorticity, coords=u.coords, dims=u.dims),
    }


def robust_score_positive(da: xr.DataArray, p95_floor: float = 1e-12) -> xr.DataArray:
    arr = np.asarray(da.values, dtype=float)
    valid = arr[np.isfinite(arr)]

    if valid.size == 0:
        return xr.full_like(da, np.nan, dtype=float)

    positive = valid[valid > 0]
    if positive.size == 0:
        return xr.full_like(da, 0.0, dtype=float)

    p95 = float(np.nanpercentile(positive, 95))
    scale = max(p95, p95_floor)

    score = da / scale
    score = xr.where(score < 0, 0, xr.where(score > 1, 1, score))
    return score


def robust_score_abs(da: xr.DataArray, p95_floor: float = 1e-12) -> xr.DataArray:
    return robust_score_positive(abs(da), p95_floor=p95_floor)


def current_speed_score(speed: xr.DataArray) -> xr.DataArray:
    """
    General dynamic suitability from current speed:
    - too weak can mean less transport/mixing;
    - too strong can be operationally risky;
    - middle range gets higher score.
    First-generation heuristic.
    """
    # Center around 0.25 m/s, width 0.25 m/s.
    score = np.exp(-((speed - 0.25) / 0.25) ** 2)
    score = xr.where(speed < 0.03, score * 0.5, score)
    score = xr.where(speed > 0.80, score * 0.5, score)
    score = xr.where(score < 0, 0, xr.where(score > 1, 1, score))
    score.name = "current_speed_score"
    score.attrs = {
        "long_name": "Heuristic current speed suitability score",
        "units": "0-1",
        "note": "First-generation dynamic score; not a safety guarantee.",
    }
    return score


def compute_confidence(layers: Dict[str, xr.DataArray], essential: List[str], optional: List[str]) -> Dict[str, Any]:
    layer_quality = {}

    for name, da in layers.items():
        arr = np.asarray(da.values, dtype=float)
        if arr.size == 0:
            q = 0.0
        else:
            q = float(np.mean(np.isfinite(arr)))
        layer_quality[name] = q

    essential_q = [layer_quality.get(k, 0.0) for k in essential]
    optional_q = [layer_quality.get(k, 0.0) for k in optional]

    essential_score = float(np.mean(essential_q)) if essential_q else 0.0
    optional_score = float(np.mean(optional_q)) if optional_q else 0.0

    confidence = 0.85 * essential_score + 0.15 * optional_score

    return {
        "physics_confidence": max(0.0, min(1.0, confidence)),
        "essential_score": essential_score,
        "optional_score": optional_score,
        "layer_quality": layer_quality,
    }


def top_cells(ds: xr.Dataset, var_name: str, n: int = 10) -> List[Dict[str, Any]]:
    if var_name not in ds:
        return []

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

        rows.append(
            {
                "rank": len(rows) + 1,
                "lat": float(lat_vals[i]),
                "lon": float(lon_vals[j]),
                var_name: safe_float(arr[i, j], None),
                "current_speed_ms": safe_float(ds["current_speed_ms"].values[i, j], None)
                if "current_speed_ms" in ds
                else None,
                "front_score": safe_float(ds["front_score"].values[i, j], None)
                if "front_score" in ds
                else None,
                "convergence_score": safe_float(ds["convergence_score"].values[i, j], None)
                if "convergence_score" in ds
                else None,
            }
        )

    return rows


def make_geojson_preview(
    ds: xr.Dataset,
    out_file: Path,
    var_name: str = "front_score",
    threshold: float = 0.70,
    max_points: int = 500,
) -> Dict[str, Any]:
    if var_name not in ds:
        return {
            "created": False,
            "reason": f"{var_name} not available",
            "file": str(out_file),
        }

    da = ds[var_name]
    arr = np.asarray(da.values, dtype=float)

    lat_vals = np.asarray(ds["lat"].values, dtype=float)
    lon_vals = np.asarray(ds["lon"].values, dtype=float)

    valid = np.where(np.isfinite(arr) & (arr >= threshold))

    rows = []
    for i, j in zip(valid[0], valid[1]):
        rows.append(
            {
                "lat": float(lat_vals[i]),
                "lon": float(lon_vals[j]),
                "score": safe_float(arr[i, j], 0.0),
                "current_speed_ms": safe_float(ds["current_speed_ms"].values[i, j], None),
                "convergence_score": safe_float(ds["convergence_score"].values[i, j], None),
                "vorticity_score": safe_float(ds["vorticity_score"].values[i, j], None),
                "sst_front_score": safe_float(ds["sst_front_score"].values[i, j], None),
                "chl_front_score": safe_float(ds["chl_front_score"].values[i, j], None),
                "ssh_gradient_score": safe_float(ds["ssh_gradient_score"].values[i, j], None),
            }
        )

    rows = sorted(rows, key=lambda x: x["score"] or 0.0, reverse=True)[:max_points]

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
                    var_name: r["score"],
                    "current_speed_ms": r["current_speed_ms"],
                    "convergence_score": r["convergence_score"],
                    "vorticity_score": r["vorticity_score"],
                    "sst_front_score": r["sst_front_score"],
                    "chl_front_score": r["chl_front_score"],
                    "ssh_gradient_score": r["ssh_gradient_score"],
                    "label": "Dynamic physics front candidate",
                },
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "name": "NELAYA-AI Ocean Dynamic Front Preview",
        "features": features,
    }

    out_file.write_text(json.dumps(to_builtin(geojson), indent=2, ensure_ascii=False))

    return {
        "created": True,
        "file": str(out_file),
        "var_name": var_name,
        "threshold": threshold,
        "point_count": len(features),
    }


def load_layer(
    kind: str,
    file_path: Path,
    var_name: str,
    target_lat: xr.DataArray,
    target_lon: xr.DataArray,
) -> xr.DataArray:
    print(f"Loading {kind}: {file_path} :: {var_name}", flush=True)

    ds = open_dataset_any(file_path)
    ds = standardize_lat_lon(ds)

    da = get_var(ds, var_name, kind)

    if kind == "sst":
        da = maybe_convert_sst_to_celsius(da)

    if kind == "chl":
        da = clean_chl(da)

    da_i = interp_to_target(da, target_lat=target_lat, target_lon=target_lon)
    da_i = sanitize_grid_da(da_i, name=kind)

    return da_i


def vector_mean_direction(u: xr.DataArray, v: xr.DataArray) -> Optional[float]:
    uu = np.asarray(u.values, dtype=float)
    vv = np.asarray(v.values, dtype=float)

    mask = np.isfinite(uu) & np.isfinite(vv)
    if np.sum(mask) == 0:
        return None

    u_mean = float(np.nanmean(uu[mask]))
    v_mean = float(np.nanmean(vv[mask]))

    # Bearing toward direction, 0 = north, 90 = east.
    bearing = (math.degrees(math.atan2(u_mean, v_mean)) + 360.0) % 360.0
    return bearing


def direction_label_id(deg: Optional[float]) -> Optional[str]:
    if deg is None:
        return None

    dirs = [
        ("utara", 0),
        ("timur_laut", 45),
        ("timur", 90),
        ("tenggara", 135),
        ("selatan", 180),
        ("barat_daya", 225),
        ("barat", 270),
        ("barat_laut", 315),
    ]

    idx = int(((deg + 22.5) % 360) // 45)
    return dirs[idx][0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--bathy", default=str(DEFAULT_BATHY))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--front-threshold", type=float, default=0.70)
    args = parser.parse_args()

    report_file = Path(args.report)
    bathy_file = Path(args.bathy)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not report_file.exists():
        raise SystemExit(f"Dynamic input report not found: {report_file}")

    if not bathy_file.exists():
        raise SystemExit(f"Bathymetry features file not found: {bathy_file}")

    print("=" * 78, flush=True)
    print("NELAYA-AI Ocean Dynamic Physics Layer v0.1", flush=True)
    print("=" * 78, flush=True)

    report = json.loads(report_file.read_text())

    readiness = report.get("readiness", {})
    if not readiness.get("ready_for_dynamic_physics_v01"):
        raise SystemExit(
            "Dynamic inputs are not ready according to report. "
            "Run scripts/inspect_dynamic_physics_inputs.py first."
        )

    latest_files = report.get("latest_files", {})

    print("Loading bathymetry physics grid...", flush=True)
    bathy = open_dataset_any(bathy_file)
    bathy = standardize_lat_lon(bathy)

    target_lat = bathy["lat"]
    target_lon = bathy["lon"]

    # Load essential layers.
    current_u = load_layer(
        "current_u",
        Path(latest_files["current"]),
        EXPLICIT_VARS["current_u"],
        target_lat,
        target_lon,
    )
    current_v = load_layer(
        "current_v",
        Path(latest_files["current"]),
        EXPLICIT_VARS["current_v"],
        target_lat,
        target_lon,
    )
    ssh = load_layer(
        "ssh",
        Path(latest_files["ssh"]),
        EXPLICIT_VARS["ssh"],
        target_lat,
        target_lon,
    )
    sst = load_layer(
        "sst",
        Path(latest_files["sst"]),
        EXPLICIT_VARS["sst"],
        target_lat,
        target_lon,
    )
    chl = load_layer(
        "chl",
        Path(latest_files["chl"]),
        EXPLICIT_VARS["chl"],
        target_lat,
        target_lon,
    )

    # Optional layers.
    wave = None
    wind_u = None
    wind_v = None

    if latest_files.get("wave"):
        try:
            wave = load_layer(
                "wave",
                Path(latest_files["wave"]),
                EXPLICIT_VARS["wave"],
                target_lat,
                target_lon,
            )
        except Exception as e:
            print(f"WARNING: wave layer skipped: {e}", flush=True)

    if latest_files.get("wind"):
        try:
            wind_u = load_layer(
                "wind_u",
                Path(latest_files["wind"]),
                EXPLICIT_VARS["wind_u"],
                target_lat,
                target_lon,
            )
            wind_v = load_layer(
                "wind_v",
                Path(latest_files["wind"]),
                EXPLICIT_VARS["wind_v"],
                target_lat,
                target_lon,
            )
        except Exception as e:
            print(f"WARNING: wind layer skipped: {e}", flush=True)

    print("Computing current diagnostics...", flush=True)
    current_speed = np.sqrt(current_u**2 + current_v**2)
    current_speed.name = "current_speed_ms"
    current_speed.attrs = {
        "long_name": "Surface current speed",
        "units": "m s-1",
    }

    current_direction = xr.apply_ufunc(
        lambda u, v: (np.degrees(np.arctan2(u, v)) + 360.0) % 360.0,
        current_u,
        current_v,
    )
    current_direction.name = "current_direction_deg"
    current_direction.attrs = {
        "long_name": "Surface current direction toward",
        "units": "degree",
        "note": "0=north, 90=east, 180=south, 270=west.",
    }

    deriv = vector_derivatives(current_u, current_v)
    divergence = deriv["divergence"]
    divergence.name = "divergence_s_1"
    divergence.attrs = {
        "long_name": "Horizontal current divergence",
        "units": "s-1",
        "note": "Positive divergence means spreading; negative divergence indicates convergence.",
    }

    vorticity = deriv["vorticity"]
    vorticity.name = "relative_vorticity_s_1"
    vorticity.attrs = {
        "long_name": "Relative vorticity",
        "units": "s-1",
        "note": "curl_z = dvdx - dudy.",
    }

    convergence = xr.where(divergence < 0, -divergence, 0)
    convergence.name = "convergence_s_1"

    convergence_score = robust_score_positive(convergence)
    convergence_score.name = "convergence_score"
    convergence_score.attrs = {
        "long_name": "Normalized convergence score",
        "units": "0-1",
    }

    vorticity_score = robust_score_abs(vorticity)
    vorticity_score.name = "vorticity_score"
    vorticity_score.attrs = {
        "long_name": "Normalized absolute vorticity score",
        "units": "0-1",
    }

    speed_score = current_speed_score(current_speed)

    print("Computing scalar fronts...", flush=True)
    _, _, sst_grad = gradient_components(sst)
    sst_grad.name = "sst_gradient_c_per_m"
    sst_front_score = robust_score_positive(sst_grad)
    sst_front_score.name = "sst_front_score"
    sst_front_score.attrs = {
        "long_name": "Normalized SST front score",
        "units": "0-1",
    }

    log_chl = np.log10(chl.clip(min=1e-6))
    log_chl.name = "log10_chl"
    _, _, chl_grad = gradient_components(log_chl)
    chl_grad.name = "chl_log10_gradient_per_m"
    chl_front_score = robust_score_positive(chl_grad)
    chl_front_score.name = "chl_front_score"
    chl_front_score.attrs = {
        "long_name": "Normalized chlorophyll front score",
        "units": "0-1",
        "note": "Computed from log10(CHL) to reduce skew.",
    }

    _, _, ssh_grad = gradient_components(ssh)
    ssh_grad.name = "ssh_gradient_m_per_m"
    ssh_gradient_score = robust_score_positive(ssh_grad)
    ssh_gradient_score.name = "ssh_gradient_score"
    ssh_gradient_score.attrs = {
        "long_name": "Normalized sea surface height gradient score",
        "units": "0-1",
    }

    print("Combining dynamic physics scores...", flush=True)
    front_score = (
        0.35 * sst_front_score
        + 0.35 * chl_front_score
        + 0.15 * ssh_gradient_score
        + 0.15 * vorticity_score
    )
    front_score = xr.where(front_score < 0, 0, xr.where(front_score > 1, 1, front_score))
    front_score.name = "front_score"
    front_score.attrs = {
        "long_name": "Combined dynamic front score",
        "units": "0-1",
        "note": "Weighted combination of SST, CHL, SSH gradient, and vorticity.",
    }

    dynamic_physics_score = (
        0.35 * front_score
        + 0.25 * convergence_score
        + 0.20 * vorticity_score
        + 0.20 * speed_score
    )
    dynamic_physics_score = xr.where(
        dynamic_physics_score < 0,
        0,
        xr.where(dynamic_physics_score > 1, 1, dynamic_physics_score),
    )
    dynamic_physics_score.name = "dynamic_physics_score"
    dynamic_physics_score.attrs = {
        "long_name": "Combined daily dynamic physics score",
        "units": "0-1",
        "note": "First-generation daily physics diagnostic score for Physics-informed FGI.",
    }

    # Optional wind/wave diagnostics.
    optional_vars = {}
    if wave is not None:
        wave.name = "wave_height_m"
        optional_vars["wave_height_m"] = wave

    if wind_u is not None and wind_v is not None:
        wind_speed = np.sqrt(wind_u**2 + wind_v**2)
        wind_speed.name = "wind_speed_ms"
        wind_speed.attrs = {
            "long_name": "Wind speed",
            "units": "m s-1",
        }
        optional_vars["wind_u_ms"] = wind_u.rename("wind_u_ms")
        optional_vars["wind_v_ms"] = wind_v.rename("wind_v_ms")
        optional_vars["wind_speed_ms"] = wind_speed

    print("Computing confidence...", flush=True)
    confidence_layers = {
        "current_u": current_u,
        "current_v": current_v,
        "ssh": ssh,
        "sst": sst,
        "chl": chl,
    }
    if wave is not None:
        confidence_layers["wave"] = wave
    if wind_u is not None:
        confidence_layers["wind_u"] = wind_u
    if wind_v is not None:
        confidence_layers["wind_v"] = wind_v

    confidence = compute_confidence(
        layers=confidence_layers,
        essential=["current_u", "current_v", "ssh", "sst", "chl"],
        optional=["wave", "wind_u", "wind_v"],
    )

    physics_confidence_field = xr.full_like(
        dynamic_physics_score,
        confidence["physics_confidence"],
        dtype=float,
    )
    physics_confidence_field.name = "physics_confidence"
    physics_confidence_field.attrs = {
        "long_name": "Physics layer confidence",
        "units": "0-1",
        "note": "Based on finite-data coverage of essential and optional layers.",
    }

    ds_out = xr.Dataset(
        {
            "current_u_ms": current_u.rename("current_u_ms"),
            "current_v_ms": current_v.rename("current_v_ms"),
            "current_speed_ms": current_speed,
            "current_direction_deg": current_direction,
            "divergence_s_1": divergence,
            "relative_vorticity_s_1": vorticity,
            "convergence_s_1": convergence,
            "convergence_score": convergence_score,
            "vorticity_score": vorticity_score,
            "current_speed_score": speed_score,
            "ssh_m": ssh.rename("ssh_m"),
            "sst_c": sst.rename("sst_c"),
            "chl_mg_m3": chl.rename("chl_mg_m3"),
            "sst_gradient_c_per_m": sst_grad,
            "chl_log10_gradient_per_m": chl_grad,
            "ssh_gradient_m_per_m": ssh_grad,
            "sst_front_score": sst_front_score,
            "chl_front_score": chl_front_score,
            "ssh_gradient_score": ssh_gradient_score,
            "front_score": front_score,
            "dynamic_physics_score": dynamic_physics_score,
            "physics_confidence": physics_confidence_field,
            **optional_vars,
        }
    )

    ds_out.attrs = {
        "module": "nelaya_ai_ocean_dynamic_physics_layer",
        "version": "0.1",
        "region": "Aceh-Simeulue",
        "source_report": str(report_file),
        "bathymetry_grid": str(bathy_file),
        "current_file": latest_files.get("current"),
        "ssh_file": latest_files.get("ssh"),
        "sst_file": latest_files.get("sst"),
        "chl_file": latest_files.get("chl"),
        "wave_file": latest_files.get("wave"),
        "wind_file": latest_files.get("wind"),
        "note": (
            "Daily dynamic physics diagnostic layer. "
            "This is not a Navier-Stokes solver; it extracts diagnostic features "
            "from operational ocean datasets for Physics-informed FGI."
        ),
    }

    nc_out = out_dir / "ocean_dynamic_physics_today.nc"
    json_out = out_dir / "ocean_dynamic_physics_today.json"
    geojson_out = out_dir / "ocean_dynamic_front_preview.geojson"

    print("Saving NetCDF...", flush=True)
    ds_out.to_netcdf(nc_out, engine="scipy")

    print("Saving GeoJSON preview...", flush=True)
    geojson_info = make_geojson_preview(
        ds_out,
        out_file=geojson_out,
        var_name="front_score",
        threshold=args.front_threshold,
        max_points=500,
    )

    mean_current_direction = vector_mean_direction(current_u, current_v)

    summary = {
        "module": "nelaya_ai_ocean_dynamic_physics_layer",
        "version": "0.1",
        "region": "Aceh-Simeulue",
        "status": "ready",
        "inputs": latest_files,
        "outputs": {
            "netcdf": str(nc_out),
            "summary_json": str(json_out),
            "front_geojson": geojson_info,
        },
        "grid": {
            "lat_size": int(ds_out.sizes["lat"]),
            "lon_size": int(ds_out.sizes["lon"]),
            "resolution_deg": {
                "lat": estimate_resolution(ds_out["lat"]),
                "lon": estimate_resolution(ds_out["lon"]),
            },
        },
        "summary_metrics": {
            "mean_current_speed_ms": safe_stats(current_speed)["mean"],
            "median_current_speed_ms": safe_stats(current_speed)["p50"],
            "mean_current_direction_deg": mean_current_direction,
            "mean_current_direction_label": direction_label_id(mean_current_direction),
            "physics_confidence": confidence["physics_confidence"],
            "essential_data_score": confidence["essential_score"],
            "optional_data_score": confidence["optional_score"],
        },
        "stats": {
            "current_speed_ms": safe_stats(ds_out["current_speed_ms"]),
            "divergence_s_1": safe_stats(ds_out["divergence_s_1"]),
            "relative_vorticity_s_1": safe_stats(ds_out["relative_vorticity_s_1"]),
            "convergence_score": safe_stats(ds_out["convergence_score"]),
            "vorticity_score": safe_stats(ds_out["vorticity_score"]),
            "sst_front_score": safe_stats(ds_out["sst_front_score"]),
            "chl_front_score": safe_stats(ds_out["chl_front_score"]),
            "ssh_gradient_score": safe_stats(ds_out["ssh_gradient_score"]),
            "front_score": safe_stats(ds_out["front_score"]),
            "dynamic_physics_score": safe_stats(ds_out["dynamic_physics_score"]),
        },
        "top_cells": {
            "front_score": top_cells(ds_out, "front_score", n=10),
            "dynamic_physics_score": top_cells(ds_out, "dynamic_physics_score", n=10),
            "convergence_score": top_cells(ds_out, "convergence_score", n=10),
            "vorticity_score": top_cells(ds_out, "vorticity_score", n=10),
        },
        "confidence": confidence,
        "interpretation": {
            "what_this_means": (
                "NELAYA-AI now has a daily dynamic ocean physics diagnostic layer. "
                "This layer can be fused with bathymetry, FGI, safety, and field validation."
            ),
            "scientific_caution": (
                "These features diagnose ocean structure from available operational datasets. "
                "They are not direct fish abundance predictions and not a replacement for "
                "full hydrodynamic modeling or field validation."
            ),
            "recommended_next_step": (
                "Fuse bathymetry_features_aceh.nc and ocean_dynamic_physics_today.nc "
                "to create FGI v0.6 Physics-informed FGI."
            ),
        },
    }

    json_out.write_text(json.dumps(to_builtin(summary), indent=2, ensure_ascii=False))

    print("=" * 78, flush=True)
    print("DONE", flush=True)
    print("=" * 78, flush=True)
    print(f"NetCDF  : {nc_out}", flush=True)
    print(f"Summary : {json_out}", flush=True)
    print(f"GeoJSON : {geojson_out}", flush=True)
    print("", flush=True)
    print("Quick check:", flush=True)
    print(f"  cat {json_out} | jq '.summary_metrics'", flush=True)
    print(f"  cat {json_out} | jq '.stats.front_score'", flush=True)
    print(f"  cat {json_out} | jq '.top_cells.front_score[0:10]'", flush=True)
    print("=" * 78, flush=True)


if __name__ == "__main__":
    main()