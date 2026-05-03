#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NELAYA-AI Physics-informed FGI Support Layer v0.6

Purpose:
- Fuse static bathymetry physics and daily dynamic ocean physics.
- Produce species-group physics support score:
    small_pelagic
    medium_pelagic
    demersal

Inputs:
- data/physics/bathymetry_features_aceh.nc
- data/physics/ocean_dynamic_physics_today.nc
- data/physics/ocean_dynamic_physics_today.json

Outputs:
- data/physics/fgi_physics_support_today.nc
- data/physics/fgi_physics_support_today.json
- data/physics/fgi_physics_support_preview.geojson

Important:
- This is NOT direct fish abundance prediction.
- This is a physics-informed support layer to be fused later with existing FGI,
  safety, regulation, economy, and field validation.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import xarray as xr


os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


DEFAULT_BATHY = Path("data/physics/bathymetry_features_aceh.nc")
DEFAULT_DYNAMIC = Path("data/physics/ocean_dynamic_physics_today.nc")
DEFAULT_DYNAMIC_JSON = Path("data/physics/ocean_dynamic_physics_today.json")
DEFAULT_OUT = Path("data/physics")


SPECIES_BATHY_VAR = {
    "small_pelagic": "small_pelagic_bathy_support",
    "medium_pelagic": "medium_pelagic_bathy_support",
    "demersal": "demersal_bathy_support",
}


SPECIES_WEIGHTS = {
    # small pelagic: dynamic productivity/front matters, but shelf/coastal support still important.
    "small_pelagic": {
        "dynamic": 0.55,
        "bathy": 0.30,
        "shelf_break": 0.10,
        "operational": 0.05,
    },
    # medium pelagic: shelf break and ocean fronts are especially important.
    "medium_pelagic": {
        "dynamic": 0.50,
        "bathy": 0.25,
        "shelf_break": 0.20,
        "operational": 0.05,
    },
    # demersal: bathymetry/seafloor structure has stronger weight.
    "demersal": {
        "dynamic": 0.35,
        "bathy": 0.45,
        "shelf_break": 0.10,
        "operational": 0.10,
    },
}


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


def get_required(ds: xr.Dataset, var_name: str) -> xr.DataArray:
    if var_name not in ds:
        raise KeyError(f"Required variable not found: {var_name}. Available={list(ds.data_vars)}")
    return sanitize_da(ds[var_name], name=var_name)


def interp_bathy_to_dynamic(bathy: xr.Dataset, dyn: xr.Dataset) -> xr.Dataset:
    """
    Bathy and dynamic should already be on same 1/12 degree grid.
    This function makes the fusion robust if small coordinate differences exist.
    """
    return bathy.interp(
        lat=dyn["lat"],
        lon=dyn["lon"],
        method="nearest",
    )


def build_wave_score(wave: Optional[xr.DataArray], template: xr.DataArray) -> xr.DataArray:
    if wave is None:
        out = xr.full_like(template, 0.70, dtype=float)
        out.name = "wave_operational_score"
        out.attrs["note"] = "Wave layer unavailable; neutral score 0.70 used."
        return out

    # First-generation small-vessel operational heuristic:
    # <=0.8 m good, 0.8-2.5 declining, >2.5 poor.
    score = xr.where(
        wave <= 0.8,
        1.0,
        xr.where(wave >= 2.5, 0.0, 1.0 - ((wave - 0.8) / (2.5 - 0.8))),
    )

    score = clip01(score)
    score.name = "wave_operational_score"
    score.attrs = {
        "long_name": "Wave operational score",
        "units": "0-1",
        "note": "Heuristic; not a marine safety guarantee.",
    }
    return score


def build_wind_score(wind_speed: Optional[xr.DataArray], template: xr.DataArray) -> xr.DataArray:
    if wind_speed is None:
        out = xr.full_like(template, 0.70, dtype=float)
        out.name = "wind_operational_score"
        out.attrs["note"] = "Wind layer unavailable; neutral score 0.70 used."
        return out

    # First-generation operational heuristic:
    # <=6 m/s good, 6-14 declining, >14 poor.
    score = xr.where(
        wind_speed <= 6.0,
        1.0,
        xr.where(wind_speed >= 14.0, 0.0, 1.0 - ((wind_speed - 6.0) / (14.0 - 6.0))),
    )

    score = clip01(score)
    score.name = "wind_operational_score"
    score.attrs = {
        "long_name": "Wind operational score",
        "units": "0-1",
        "note": "Heuristic; not a marine safety guarantee.",
    }
    return score


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
                "front_score": safe_float(ds["front_score"].values[i, j], None)
                if "front_score" in ds else None,
                "dynamic_physics_score": safe_float(ds["dynamic_physics_score"].values[i, j], None)
                if "dynamic_physics_score" in ds else None,
                "shelf_break_score": safe_float(ds["shelf_break_score"].values[i, j], None)
                if "shelf_break_score" in ds else None,
                "bathy_support": safe_float(ds["species_bathy_support"].values[i, j], None)
                if "species_bathy_support" in ds else None,
                "current_speed_ms": safe_float(ds["current_speed_ms"].values[i, j], None)
                if "current_speed_ms" in ds else None,
                "depth_m": safe_float(ds["depth_m"].values[i, j], None)
                if "depth_m" in ds else None,
            }
        )

    return rows


def make_geojson_preview(
    ds: xr.Dataset,
    out_file: Path,
    score_var: str,
    threshold: float,
    max_points: int = 500,
) -> Dict[str, Any]:
    if score_var not in ds:
        return {
            "created": False,
            "reason": f"{score_var} not found",
            "file": str(out_file),
        }

    da = ds[score_var]
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
                "front_score": safe_float(ds["front_score"].values[i, j], None),
                "dynamic_physics_score": safe_float(ds["dynamic_physics_score"].values[i, j], None),
                "shelf_break_score": safe_float(ds["shelf_break_score"].values[i, j], None),
                "bathy_support": safe_float(ds["species_bathy_support"].values[i, j], None),
                "operational_score": safe_float(ds["operational_score"].values[i, j], None),
                "current_speed_ms": safe_float(ds["current_speed_ms"].values[i, j], None),
                "depth_m": safe_float(ds["depth_m"].values[i, j], None),
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
                    score_var: r["score"],
                    "front_score": r["front_score"],
                    "dynamic_physics_score": r["dynamic_physics_score"],
                    "shelf_break_score": r["shelf_break_score"],
                    "species_bathy_support": r["bathy_support"],
                    "operational_score": r["operational_score"],
                    "current_speed_ms": r["current_speed_ms"],
                    "depth_m": r["depth_m"],
                    "label": "FGI v0.6 physics-informed support candidate",
                },
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "name": "NELAYA-AI FGI Physics Support Preview",
        "features": features,
    }

    out_file.write_text(json.dumps(to_builtin(geojson), indent=2, ensure_ascii=False))

    return {
        "created": True,
        "file": str(out_file),
        "score_var": score_var,
        "threshold": threshold,
        "point_count": len(features),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bathy", default=str(DEFAULT_BATHY))
    parser.add_argument("--dynamic", default=str(DEFAULT_DYNAMIC))
    parser.add_argument("--dynamic-json", default=str(DEFAULT_DYNAMIC_JSON))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--species-group",
        default="medium_pelagic",
        choices=["small_pelagic", "medium_pelagic", "demersal"],
    )
    parser.add_argument("--threshold", type=float, default=0.55)
    args = parser.parse_args()

    bathy_file = Path(args.bathy)
    dyn_file = Path(args.dynamic)
    dyn_json_file = Path(args.dynamic_json)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not bathy_file.exists():
        raise SystemExit(f"Missing bathymetry file: {bathy_file}")

    if not dyn_file.exists():
        raise SystemExit(f"Missing dynamic physics file: {dyn_file}")

    print("=" * 78, flush=True)
    print("NELAYA-AI Physics-informed FGI Support Layer v0.6", flush=True)
    print("=" * 78, flush=True)
    print(f"Species group : {args.species_group}", flush=True)
    print(f"Bathy         : {bathy_file}", flush=True)
    print(f"Dynamic       : {dyn_file}", flush=True)

    bathy = open_dataset_any(bathy_file)
    dyn = open_dataset_any(dyn_file)

    bathy = interp_bathy_to_dynamic(bathy, dyn)

    species_bathy_var = SPECIES_BATHY_VAR[args.species_group]
    weights = SPECIES_WEIGHTS[args.species_group]

    print("Loading fusion layers...", flush=True)

    dynamic_physics_score = get_required(dyn, "dynamic_physics_score")
    front_score = get_required(dyn, "front_score")
    convergence_score = get_required(dyn, "convergence_score")
    vorticity_score = get_required(dyn, "vorticity_score")
    current_speed_score = get_required(dyn, "current_speed_score")
    current_speed_ms = get_required(dyn, "current_speed_ms")
    physics_confidence = get_required(dyn, "physics_confidence")

    species_bathy_support = get_required(bathy, species_bathy_var)
    shelf_break_score = get_required(bathy, "shelf_break_score")
    ocean_fraction = get_required(bathy, "ocean_fraction")
    depth_m = get_required(bathy, "depth_m")
    bathymetry_slope = get_required(bathy, "bathymetry_slope")

    wave = sanitize_da(dyn["wave_height_m"], "wave_height_m") if "wave_height_m" in dyn else None
    wind_speed = sanitize_da(dyn["wind_speed_ms"], "wind_speed_ms") if "wind_speed_ms" in dyn else None

    print("Computing operational score...", flush=True)

    wave_operational_score = build_wave_score(wave, dynamic_physics_score)
    wind_operational_score = build_wind_score(wind_speed, dynamic_physics_score)

    operational_score = clip01(0.60 * wave_operational_score + 0.40 * wind_operational_score)
    operational_score.name = "operational_score"
    operational_score.attrs = {
        "long_name": "Simple operational condition score from wave and wind",
        "units": "0-1",
        "note": "Heuristic support only; not official safety guidance.",
    }

    print("Computing physics-informed support score...", flush=True)

    dynamic_structure_score = clip01(
        0.50 * dynamic_physics_score
        + 0.20 * front_score
        + 0.15 * convergence_score
        + 0.10 * vorticity_score
        + 0.05 * current_speed_score
    )
    dynamic_structure_score.name = "dynamic_structure_score"
    dynamic_structure_score.attrs = {
        "long_name": "Combined dynamic ocean structure support score",
        "units": "0-1",
    }

    topographic_structure_score = clip01(
        0.65 * species_bathy_support
        + 0.35 * shelf_break_score
    )
    topographic_structure_score.name = "topographic_structure_score"
    topographic_structure_score.attrs = {
        "long_name": "Combined bathymetry and shelf-break structure score",
        "units": "0-1",
    }

    raw_support_base = clip01(
        weights["dynamic"] * dynamic_structure_score
        + weights["bathy"] * species_bathy_support
        + weights["shelf_break"] * shelf_break_score
        + weights["operational"] * operational_score
    )

    # v0.6.1 habitat balance gate:
    # dynamic ocean signals are important, but ranking should not be dominated
    # by dynamic fronts alone when bathymetry/shelf-break support is very weak.
    if args.species_group == "medium_pelagic":
        habitat_balance_gate = clip01(
            0.45
            + 0.35 * species_bathy_support
            + 0.20 * shelf_break_score
        )
    elif args.species_group == "small_pelagic":
        habitat_balance_gate = clip01(
            0.50
            + 0.40 * species_bathy_support
            + 0.10 * shelf_break_score
        )
    else:
        habitat_balance_gate = clip01(
            0.40
            + 0.50 * species_bathy_support
            + 0.10 * shelf_break_score
        )

    habitat_balance_gate.name = "habitat_balance_gate"
    habitat_balance_gate.attrs = {
        "long_name": "Habitat balance gate for physics-informed FGI",
        "units": "0-1",
        "note": "Prevents dynamic-only signals from dominating when bathymetry support is weak.",
    }

    raw_support_after_gate = clip01(raw_support_base * habitat_balance_gate)

    # v0.6.2 depth realism dampening:
    # For medium pelagic shelf-break support, very deep ocean cells should not
    # dominate ranking unless bathymetry/shelf-break support is also meaningful.
    if args.species_group == "medium_pelagic":
        deep_ocean_penalty = xr.where(
            depth_m <= 1000,
            1.0,
            xr.where(
                depth_m >= 2500,
                0.55,
                1.0 - 0.45 * ((depth_m - 1000) / (2500 - 1000)),
            ),
        )

        # If shelf-break and bathy support are weak, apply stronger penalty.
        weak_topography = (shelf_break_score < 0.25) & (species_bathy_support < 0.30)
        deep_ocean_penalty = xr.where(
            weak_topography & (depth_m > 1000),
            deep_ocean_penalty * 0.70,
            deep_ocean_penalty,
        )
    else:
        deep_ocean_penalty = xr.full_like(raw_support_after_gate, 1.0, dtype=float)

    deep_ocean_penalty.name = "deep_ocean_penalty"
    deep_ocean_penalty.attrs = {
        "long_name": "Depth realism penalty for physics-informed FGI",
        "units": "0-1",
        "note": "Reduces dominance of very deep cells when shelf-break/bathymetry support is weak.",
    }

    raw_support = clip01(raw_support_after_gate * deep_ocean_penalty)
    raw_support = raw_support.where(ocean_fraction >= 0.25)
    raw_support.name = "fgi_physics_support_score"
    raw_support.attrs = {
        "long_name": "FGI v0.6 physics-informed support score",
        "units": "0-1",
        "note": "Physics support layer only; not direct fish abundance prediction.",
    }

    confidence_adjusted = clip01(raw_support * (0.60 + 0.40 * physics_confidence))
    confidence_adjusted.name = "fgi_physics_support_confidence_adjusted"
    confidence_adjusted.attrs = {
        "long_name": "Confidence-adjusted FGI physics support score",
        "units": "0-1",
        "note": "Score moderated by dynamic physics confidence.",
    }

    ds_out = xr.Dataset(
        {
            "fgi_physics_support_score": raw_support,
            "fgi_physics_support_confidence_adjusted": confidence_adjusted,
            "raw_support_base": raw_support_base,
            "habitat_balance_gate": habitat_balance_gate,
            "raw_support_after_gate": raw_support_after_gate,
            "deep_ocean_penalty": deep_ocean_penalty,
            "dynamic_structure_score": dynamic_structure_score,
            "topographic_structure_score": topographic_structure_score,
            "dynamic_physics_score": dynamic_physics_score,
            "front_score": front_score,
            "convergence_score": convergence_score,
            "vorticity_score": vorticity_score,
            "current_speed_score": current_speed_score,
            "species_bathy_support": species_bathy_support,
            "shelf_break_score": shelf_break_score,
            "operational_score": operational_score,
            "wave_operational_score": wave_operational_score,
            "wind_operational_score": wind_operational_score,
            "physics_confidence": physics_confidence,
            "current_speed_ms": current_speed_ms,
            "depth_m": depth_m,
            "bathymetry_slope": bathymetry_slope,
            "ocean_fraction": ocean_fraction,
        }
    )

    if wave is not None:
        ds_out["wave_height_m"] = wave
    if wind_speed is not None:
        ds_out["wind_speed_ms"] = wind_speed

    dyn_summary = {}
    if dyn_json_file.exists():
        try:
            dyn_summary = json.loads(dyn_json_file.read_text())
        except Exception:
            dyn_summary = {}

    ds_out.attrs = {
        "module": "nelaya_ai_physics_informed_fgi_support",
        "version": "0.6.2",
        "species_group": args.species_group,
        "region": "Aceh-Simeulue",
        "bathymetry_input": str(bathy_file),
        "dynamic_input": str(dyn_file),
        "scientific_caution": (
            "This is a physics-informed support layer, not a direct fish abundance "
            "prediction and not a full hydrodynamic model."
        ),
    }

    nc_out = out_dir / "fgi_physics_support_today.nc"
    json_out = out_dir / "fgi_physics_support_today.json"
    geojson_out = out_dir / "fgi_physics_support_preview.geojson"

    print("Saving NetCDF...", flush=True)
    ds_out.to_netcdf(nc_out, engine="scipy")

    print("Saving GeoJSON preview...", flush=True)
    geojson_info = make_geojson_preview(
        ds_out,
        out_file=geojson_out,
        score_var="fgi_physics_support_confidence_adjusted",
        threshold=args.threshold,
        max_points=500,
    )

    summary = {
        "module": "nelaya_ai_physics_informed_fgi_support",
        "version": "0.6",
        "status": "ready",
        "region": "Aceh-Simeulue",
        "species_group": args.species_group,
        "weights": weights,
        "inputs": {
            "bathymetry": str(bathy_file),
            "dynamic_physics": str(dyn_file),
            "dynamic_summary": str(dyn_json_file) if dyn_json_file.exists() else None,
        },
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
        "summary_metrics": {
            "mean_support_score": safe_stats(raw_support)["mean"],
            "median_support_score": safe_stats(raw_support)["p50"],
            "p95_support_score": safe_stats(raw_support)["p95"],
            "max_support_score": safe_stats(raw_support)["max"],
            "mean_confidence_adjusted_score": safe_stats(confidence_adjusted)["mean"],
            "max_confidence_adjusted_score": safe_stats(confidence_adjusted)["max"],
            "dynamic_physics_confidence": safe_stats(physics_confidence)["mean"],
            "mean_current_speed_ms": safe_stats(current_speed_ms)["mean"],
            "dynamic_mean_current_direction_deg": dyn_summary.get("summary_metrics", {}).get("mean_current_direction_deg"),
            "dynamic_mean_current_direction_label": dyn_summary.get("summary_metrics", {}).get("mean_current_direction_label"),
        },
        "stats": {
            "fgi_physics_support_score": safe_stats(raw_support),
            "fgi_physics_support_confidence_adjusted": safe_stats(confidence_adjusted),
            "dynamic_structure_score": safe_stats(dynamic_structure_score),
            "topographic_structure_score": safe_stats(topographic_structure_score),
            "operational_score": safe_stats(operational_score),
            "front_score": safe_stats(front_score),
            "shelf_break_score": safe_stats(shelf_break_score),
            "species_bathy_support": safe_stats(species_bathy_support),
            "raw_support_base": safe_stats(raw_support_base),
            "habitat_balance_gate": safe_stats(habitat_balance_gate),
            "raw_support_after_gate": safe_stats(raw_support_after_gate),
            "deep_ocean_penalty": safe_stats(deep_ocean_penalty),
        },
        "top_cells": {
            "fgi_physics_support_score": top_cells(ds_out, "fgi_physics_support_score", n=10),
            "fgi_physics_support_confidence_adjusted": top_cells(ds_out, "fgi_physics_support_confidence_adjusted", n=10),
            "dynamic_structure_score": top_cells(ds_out, "dynamic_structure_score", n=10),
            "topographic_structure_score": top_cells(ds_out, "topographic_structure_score", n=10),
        },
        "interpretation": {
            "what_this_means": (
                "NELAYA-AI now has a first physics-informed support layer for FGI. "
                "It combines seabed structure, shelf-break information, daily current/front/"
                "convergence/vorticity diagnostics, and simple operational wave-wind support."
            ),
            "scientific_caution": (
                "This layer should be interpreted as habitat/physics support, not as a direct "
                "fish catch prediction. Field validation and calibration are still required."
            ),
            "recommended_next_step": (
                "Fuse this support layer with existing FGI hotspot/recommendation logic, then "
                "compare against trip logger and fisher observations."
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
    print(f"  cat {json_out} | jq '.stats.fgi_physics_support_confidence_adjusted'", flush=True)
    print(f"  cat {json_out} | jq '.top_cells.fgi_physics_support_confidence_adjusted[0:10]'", flush=True)
    print(f"  cat {json_out} | jq '.outputs.geojson'", flush=True)
    print("=" * 78, flush=True)


if __name__ == "__main__":
    main()
