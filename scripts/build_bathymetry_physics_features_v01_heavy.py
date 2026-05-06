#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build bathymetry-derived physics features for NELAYA-AI.

Input:
  GEBCO elevation grid:
  data/raw/aceh_simeulue/bathymetry/gebco_2023_n10.0_s0.0_w90.0_e100.0.nc

Outputs:
  data/physics/bathymetry_features_aceh.nc
  data/physics/bathymetry_features_summary.json
  data/physics/bathymetry_shelfbreak_preview.geojson

Purpose:
  This is the first step toward Physics-informed FGI:
  - depth
  - bathymetric slope
  - shelf/slope/deep zones
  - shelf-break score
  - species bathymetry support scores
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import xarray as xr


ACEH_BBOX = {
    "min_lon": 92.0,
    "max_lon": 99.0,
    "min_lat": 1.0,
    "max_lat": 7.0,
}


DEFAULT_INPUT = (
    "data/raw/aceh_simeulue/bathymetry/"
    "gebco_2023_n10.0_s0.0_w90.0_e100.0.nc"
)


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


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def stats(da: xr.DataArray) -> Dict[str, Any]:
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


def normalize_lon_if_needed(ds: xr.Dataset, lon_name: str = "lon") -> xr.Dataset:
    lon = ds[lon_name]
    if float(lon.max()) > 180:
        ds = ds.assign_coords({lon_name: (((lon + 180) % 360) - 180)})
        ds = ds.sortby(lon_name)
    return ds


def subset_aceh(ds: xr.Dataset) -> xr.Dataset:
    ds = normalize_lon_if_needed(ds, "lon")

    lat_vals = np.asarray(ds["lat"].values)
    if lat_vals[0] <= lat_vals[-1]:
        lat_slice = slice(ACEH_BBOX["min_lat"], ACEH_BBOX["max_lat"])
    else:
        lat_slice = slice(ACEH_BBOX["max_lat"], ACEH_BBOX["min_lat"])

    return ds.sel(
        lon=slice(ACEH_BBOX["min_lon"], ACEH_BBOX["max_lon"]),
        lat=lat_slice,
    )


def estimate_resolution(coord: xr.DataArray) -> float | None:
    vals = np.asarray(coord.values, dtype=float)
    vals = vals[np.isfinite(vals)]
    if vals.size < 2:
        return None
    diffs = np.diff(np.sort(np.unique(vals)))
    diffs = diffs[np.isfinite(diffs)]
    if diffs.size == 0:
        return None
    return float(np.nanmedian(np.abs(diffs)))


def compute_slope_m_per_m(depth: xr.DataArray) -> xr.DataArray:
    """
    Compute approximate bathymetric slope in m/m.

    depth:
      positive ocean depth in meters.
      land must be NaN.
    """

    lat = np.asarray(depth["lat"].values, dtype=float)
    lon = np.asarray(depth["lon"].values, dtype=float)

    lat_res = estimate_resolution(depth["lat"])
    lon_res = estimate_resolution(depth["lon"])

    if lat_res is None or lon_res is None:
        raise ValueError("Cannot estimate lat/lon resolution.")

    mean_lat = float(np.nanmean(lat))

    dy_m = lat_res * 111_320.0
    dx_m = lon_res * 111_320.0 * max(0.1, math.cos(math.radians(mean_lat)))

    arr = np.asarray(depth.values, dtype=float)
    valid = arr[np.isfinite(arr)]

    if valid.size == 0:
        raise ValueError("No valid ocean depth values.")

    fill = float(np.nanmedian(valid))
    arr_filled = np.where(np.isfinite(arr), arr, fill)

    grad_y, grad_x = np.gradient(arr_filled, dy_m, dx_m)
    slope = np.sqrt(grad_x**2 + grad_y**2)

    slope = np.where(np.isfinite(arr), slope, np.nan)

    return xr.DataArray(
        slope,
        coords=depth.coords,
        dims=depth.dims,
        name="bathymetry_slope",
        attrs={
            "long_name": "Approximate bathymetric slope",
            "units": "m m-1",
            "note": "Computed from positive ocean depth using spherical degree-to-meter approximation.",
        },
    )


def clip01(da: xr.DataArray) -> xr.DataArray:
    return xr.where(da < 0, 0, xr.where(da > 1, 1, da))


def gaussian_score(da: xr.DataArray, center: float, width: float) -> xr.DataArray:
    return np.exp(-((da - center) / width) ** 2)


def linear_score_between(
    da: xr.DataArray,
    low: float,
    high: float,
    reverse: bool = False,
) -> xr.DataArray:
    score = (da - low) / (high - low)
    score = clip01(score)
    if reverse:
        score = 1.0 - score
    return score


def classify_depth_zone(depth: xr.DataArray) -> xr.DataArray:
    """
    Depth zone codes:
      0 = land_or_unknown
      1 = coastal_0_50m
      2 = shelf_50_200m
      3 = upper_slope_200_1000m
      4 = deep_gt_1000m
    """
    zone = xr.full_like(depth, 0, dtype=np.int16)
    zone = xr.where((depth >= 0) & (depth <= 50), 1, zone)
    zone = xr.where((depth > 50) & (depth <= 200), 2, zone)
    zone = xr.where((depth > 200) & (depth <= 1000), 3, zone)
    zone = xr.where(depth > 1000, 4, zone)

    zone.name = "depth_zone_code"
    zone.attrs = {
        "long_name": "Bathymetry depth zone code",
        "codes": "0=land_or_unknown, 1=coastal_0_50m, 2=shelf_50_200m, 3=upper_slope_200_1000m, 4=deep_gt_1000m",
    }
    return zone


def build_species_support_scores(
    depth: xr.DataArray,
    slope: xr.DataArray,
    shelf_break_score: xr.DataArray,
    ocean_fraction: xr.DataArray,
) -> Dict[str, xr.DataArray]:
    """
    Simple first-generation bathymetry support scores.

    These are not species predictions.
    They are habitat-structure support layers to be combined later with:
      SST, CHL, current, wave, wind, SSH, field validation.
    """

    # Small pelagic: generally shelf/coastal productivity zone,
    # avoid too deep ocean and very steep bathymetry.
    small_depth = (
        0.45 * gaussian_score(depth, center=60, width=60)
        + 0.35 * gaussian_score(depth, center=120, width=90)
        + 0.20 * gaussian_score(depth, center=25, width=35)
    )
    small_slope = linear_score_between(slope, low=0.00, high=0.12, reverse=True)
    small_pelagic = clip01((0.75 * small_depth + 0.25 * small_slope) * ocean_fraction)
    small_pelagic.name = "small_pelagic_bathy_support"
    small_pelagic.attrs = {
        "long_name": "Bathymetry structural support for small pelagic fish",
        "units": "0-1",
        "note": "First-generation structural score; not a fish abundance prediction.",
    }

    # Medium pelagic: shelf break, upper slope, and transition zones matter more.
    medium_depth = (
        0.30 * gaussian_score(depth, center=150, width=120)
        + 0.45 * gaussian_score(depth, center=350, width=250)
        + 0.25 * gaussian_score(depth, center=800, width=500)
    )
    medium_pelagic = clip01(
        (
            0.50 * medium_depth
            + 0.40 * shelf_break_score
            + 0.10 * linear_score_between(slope, low=0.02, high=0.20)
        )
        * ocean_fraction
    )
    medium_pelagic.name = "medium_pelagic_bathy_support"
    medium_pelagic.attrs = {
        "long_name": "Bathymetry structural support for medium pelagic fish",
        "units": "0-1",
        "note": "First-generation structural score; must be combined with dynamic ocean variables.",
    }

    # Demersal: seabed-associated fish; focus on shelf to upper slope.
    dem_depth = (
        0.45 * gaussian_score(depth, center=60, width=60)
        + 0.35 * gaussian_score(depth, center=150, width=100)
        + 0.20 * gaussian_score(depth, center=300, width=180)
    )
    dem_slope = linear_score_between(slope, low=0.00, high=0.18, reverse=True)
    demersal = clip01((0.70 * dem_depth + 0.30 * dem_slope) * ocean_fraction)
    demersal.name = "demersal_bathy_support"
    demersal.attrs = {
        "long_name": "Bathymetry structural support for demersal fish",
        "units": "0-1",
        "note": "First-generation structural score; not a direct catch prediction.",
    }

    return {
        "small_pelagic_bathy_support": small_pelagic,
        "medium_pelagic_bathy_support": medium_pelagic,
        "demersal_bathy_support": demersal,
    }


def make_geojson_preview(
    ds: xr.Dataset,
    out_file: Path,
    threshold: float = 0.65,
    max_points: int = 500,
) -> Dict[str, Any]:
    """
    Create lightweight GeoJSON point preview for high shelf-break score cells.
    """

    if "shelf_break_score" not in ds:
        return {
            "created": False,
            "reason": "shelf_break_score not available",
            "file": str(out_file),
        }

    score = ds["shelf_break_score"]
    depth = ds["depth_m"]
    slope = ds["bathymetry_slope"]

    arr = np.asarray(score.values, dtype=float)
    valid = np.where(np.isfinite(arr) & (arr >= threshold))

    rows = []

    lat_vals = np.asarray(ds["lat"].values, dtype=float)
    lon_vals = np.asarray(ds["lon"].values, dtype=float)

    for i, j in zip(valid[0], valid[1]):
        rows.append(
            {
                "lat": float(lat_vals[i]),
                "lon": float(lon_vals[j]),
                "score": safe_float(arr[i, j], 0.0),
                "depth_m": safe_float(depth.values[i, j], None),
                "slope": safe_float(slope.values[i, j], None),
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
                    "shelf_break_score": r["score"],
                    "depth_m": r["depth_m"],
                    "slope_m_per_m": r["slope"],
                    "label": "Bathymetry shelf-break candidate",
                },
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "name": "NELAYA-AI Bathymetry Shelf-break Preview",
        "features": features,
    }

    out_file.write_text(json.dumps(to_builtin(geojson), indent=2, ensure_ascii=False))

    return {
        "created": True,
        "file": str(out_file),
        "threshold": threshold,
        "point_count": len(features),
    }


def top_cells(
    ds: xr.Dataset,
    var_name: str,
    n: int = 10,
) -> List[Dict[str, Any]]:
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
                "depth_m": safe_float(ds["depth_m"].values[i, j], None),
                "slope_m_per_m": safe_float(ds["bathymetry_slope"].values[i, j], None),
                "depth_zone_code": int(ds["depth_zone_code"].values[i, j])
                if np.isfinite(ds["depth_zone_code"].values[i, j])
                else None,
            }
        )

    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=DEFAULT_INPUT, help="GEBCO elevation NetCDF file.")
    parser.add_argument("--out", default="data/physics", help="Output directory.")
    parser.add_argument(
        "--coarsen-factor",
        type=int,
        default=20,
        help="GEBCO 15 arc-sec x factor 20 ≈ 1/12 degree Copernicus grid.",
    )
    parser.add_argument(
        "--geojson-threshold",
        type=float,
        default=0.65,
        help="Threshold for shelf-break preview GeoJSON.",
    )
    args = parser.parse_args()

    input_file = Path(args.input)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not input_file.exists():
        raise SystemExit(f"Input bathymetry file not found: {input_file}")

    print("=" * 78)
    print("NELAYA-AI Bathymetry Physics Features v0.1")
    print("=" * 78)
    print(f"Input          : {input_file}")
    print(f"Output folder  : {out_dir}")
    print(f"Coarsen factor : {args.coarsen_factor}")

    ds_raw = xr.open_dataset(input_file)
    ds_raw = subset_aceh(ds_raw)

    if "elevation" not in ds_raw:
        raise SystemExit("Variable 'elevation' not found in input file.")

    elevation = ds_raw["elevation"]

    # GEBCO convention: elevation < 0 = sea depth as negative elevation.
    depth = xr.where(elevation < 0, -elevation, np.nan)
    depth.name = "depth_m"
    depth.attrs = {
        "long_name": "Positive ocean depth derived from GEBCO elevation",
        "units": "m",
        "source": str(input_file),
        "convention": "GEBCO elevation negative below sea level converted to positive ocean depth.",
    }

    ocean_mask = xr.where(np.isfinite(depth), 1.0, 0.0)
    ocean_mask.name = "ocean_mask"

    print("Computing high-resolution slope...")
    slope_hr = compute_slope_m_per_m(depth)

    factor = int(args.coarsen_factor)

    print("Coarsening to physics grid...")
    depth_c = depth.coarsen(lat=factor, lon=factor, boundary="trim").mean(skipna=True)
    slope_c = slope_hr.coarsen(lat=factor, lon=factor, boundary="trim").mean(skipna=True)
    ocean_fraction = ocean_mask.coarsen(lat=factor, lon=factor, boundary="trim").mean(skipna=True)
    ocean_fraction.name = "ocean_fraction"
    ocean_fraction.attrs = {
        "long_name": "Fraction of ocean cells inside coarsened grid cell",
        "units": "0-1",
    }

    # Clean cells with too little ocean fraction.
    valid_ocean_cell = ocean_fraction >= 0.25
    depth_c = depth_c.where(valid_ocean_cell)
    slope_c = slope_c.where(valid_ocean_cell)

    # Depth zone.
    depth_zone = classify_depth_zone(depth_c)

    print("Computing shelf-break and bathymetry support scores...")

    # Shelf-break score: transitional depth + slope.
    shelf_depth_score = (
        0.55 * gaussian_score(depth_c, center=150, width=120)
        + 0.30 * gaussian_score(depth_c, center=300, width=220)
        + 0.15 * gaussian_score(depth_c, center=700, width=450)
    )

    slope_score = linear_score_between(slope_c, low=0.015, high=0.18)
    slope_score.name = "slope_score"
    slope_score.attrs = {
        "long_name": "Normalized bathymetric slope score",
        "units": "0-1",
    }

    shelf_break_score = clip01(
        (0.65 * shelf_depth_score + 0.35 * slope_score) * ocean_fraction
    )
    shelf_break_score.name = "shelf_break_score"
    shelf_break_score.attrs = {
        "long_name": "Shelf-break / topographic transition score",
        "units": "0-1",
        "note": "First-generation topographic transition layer for Physics-informed FGI.",
    }

    species_scores = build_species_support_scores(
        depth=depth_c,
        slope=slope_c,
        shelf_break_score=shelf_break_score,
        ocean_fraction=ocean_fraction,
    )

    ds_out = xr.Dataset(
        {
            "depth_m": depth_c,
            "bathymetry_slope": slope_c,
            "ocean_fraction": ocean_fraction,
            "depth_zone_code": depth_zone,
            "slope_score": slope_score,
            "shelf_break_score": shelf_break_score,
            **species_scores,
        }
    )

    ds_out.attrs = {
        "module": "nelaya_ai_bathymetry_physics_layer",
        "version": "0.1",
        "region": "Aceh-Simeulue",
        "bbox": json.dumps(ACEH_BBOX),
        "source": str(input_file),
        "coarsen_factor": factor,
        "note": (
            "Bathymetry-derived static physics layer for FGI. "
            "This is not a hydrodynamic solver; it extracts topographic structure "
            "from GEBCO for use in Physics-informed FGI."
        ),
    }

    nc_out = out_dir / "bathymetry_features_aceh.nc"
    json_out = out_dir / "bathymetry_features_summary.json"
    geojson_out = out_dir / "bathymetry_shelfbreak_preview.geojson"

    print(f"Saving NetCDF: {nc_out}")
    ds_out.to_netcdf(nc_out)

    geojson_info = make_geojson_preview(
        ds_out,
        out_file=geojson_out,
        threshold=args.geojson_threshold,
        max_points=500,
    )

    summary = {
        "module": "nelaya_ai_bathymetry_physics_layer",
        "version": "0.1",
        "region": "Aceh-Simeulue",
        "status": "ready",
        "source_file": str(input_file),
        "outputs": {
            "netcdf": str(nc_out),
            "summary_json": str(json_out),
            "shelfbreak_geojson": geojson_info,
        },
        "bbox": ACEH_BBOX,
        "grid": {
            "lat_size": int(ds_out.sizes["lat"]),
            "lon_size": int(ds_out.sizes["lon"]),
            "coarsen_factor": factor,
            "approx_resolution_deg": {
                "lat": estimate_resolution(ds_out["lat"]),
                "lon": estimate_resolution(ds_out["lon"]),
            },
        },
        "stats": {
            "depth_m": stats(ds_out["depth_m"]),
            "bathymetry_slope": stats(ds_out["bathymetry_slope"]),
            "ocean_fraction": stats(ds_out["ocean_fraction"]),
            "shelf_break_score": stats(ds_out["shelf_break_score"]),
            "small_pelagic_bathy_support": stats(ds_out["small_pelagic_bathy_support"]),
            "medium_pelagic_bathy_support": stats(ds_out["medium_pelagic_bathy_support"]),
            "demersal_bathy_support": stats(ds_out["demersal_bathy_support"]),
        },
        "top_cells": {
            "shelf_break_score": top_cells(ds_out, "shelf_break_score", n=10),
            "small_pelagic_bathy_support": top_cells(ds_out, "small_pelagic_bathy_support", n=10),
            "medium_pelagic_bathy_support": top_cells(ds_out, "medium_pelagic_bathy_support", n=10),
            "demersal_bathy_support": top_cells(ds_out, "demersal_bathy_support", n=10),
        },
        "interpretation": {
            "what_this_means": (
                "Bathymetry layer is now ready as a static topographic intelligence layer. "
                "It can be fused with SST, CHL, current, SSH, wave, wind, and field validation "
                "to build Physics-informed FGI."
            ),
            "caution": (
                "These scores are not fish abundance predictions. They are structural habitat-support "
                "features derived from bathymetry only."
            ),
            "recommended_next_step": (
                "Fuse this static bathymetry layer with daily dynamic ocean features: current, front, "
                "convergence, SST gradient, CHL gradient, SSH gradient, wave, and wind."
            ),
        },
    }

    json_out.write_text(json.dumps(to_builtin(summary), indent=2, ensure_ascii=False))

    print("=" * 78)
    print("DONE")
    print("=" * 78)
    print(f"NetCDF  : {nc_out}")
    print(f"Summary : {json_out}")
    print(f"GeoJSON : {geojson_out}")
    print("")
    print("Quick check:")
    print(f"  cat {json_out} | jq '.grid, .stats.shelf_break_score, .top_cells.shelf_break_score[0:5]'")
    print("=" * 78)


if __name__ == "__main__":
    main()
