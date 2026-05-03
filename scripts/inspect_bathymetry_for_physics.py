#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Inspect bathymetry data for NELAYA-AI Physics-informed FGI.

Purpose:
- Find bathymetry files inside data/raw/aceh_simeulue or selected folder.
- Detect lon/lat/depth variable.
- Infer depth convention:
    1) negative below sea level, e.g. -200 m
    2) positive depth, e.g. 200 m
- Check coverage over Aceh bbox.
- Estimate depth, shelf zone, slope, and usability for FGI physics layer.
- Save report to data/physics/bathymetry_report.json

Run:
    python scripts/inspect_bathymetry_for_physics.py

Optional:
    python scripts/inspect_bathymetry_for_physics.py --root data/raw/aceh_simeulue --out data/physics
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

import numpy as np

try:
    import xarray as xr
except Exception as e:
    raise SystemExit(
        "xarray belum tersedia. Aktifkan .venv lalu install bila perlu:\n"
        "pip install xarray netCDF4 h5netcdf\n\n"
        f"Detail error: {e}"
    )


ACEH_BBOX = {
    "min_lon": 92.0,
    "max_lon": 99.0,
    "min_lat": 1.0,
    "max_lat": 7.0,
}

DEPTH_VAR_HINTS = [
    "depth",
    "elevation",
    "elev",
    "z",
    "bathymetry",
    "bathy",
    "topo",
    "band1",
    "Band1",
    "ETOPO",
    "gebco",
    "altitude",
]

LON_HINTS = ["lon", "longitude", "x", "LONGITUDE", "LON"]
LAT_HINTS = ["lat", "latitude", "y", "LATITUDE", "LAT"]


def to_builtin(obj: Any) -> Any:
    """Convert numpy/xarray scalars to JSON-safe Python values."""
    if isinstance(obj, dict):
        return {str(k): to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_builtin(v) for v in obj]
    if isinstance(obj, tuple):
        return [to_builtin(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        value = float(obj)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def find_candidate_files(root: Path) -> List[Path]:
    exts = {".nc", ".nc4", ".cdf", ".grd"}
    candidates = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            name = p.name.lower()
            if any(k in name for k in ["bathy", "bathymetry", "gebco", "etopo", "depth", "topo"]):
                candidates.append(p)

    if not candidates:
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                candidates.append(p)

    return sorted(candidates)


def detect_coord(ds: xr.Dataset, hints: List[str]) -> Optional[str]:
    names = list(ds.coords) + list(ds.dims) + list(ds.variables)
    for h in hints:
        for n in names:
            if n == h:
                return n
    for n in names:
        low = n.lower()
        for h in hints:
            if h.lower() in low:
                return n
    return None


def detect_depth_var(ds: xr.Dataset) -> Optional[str]:
    data_vars = list(ds.data_vars)

    for h in DEPTH_VAR_HINTS:
        for v in data_vars:
            if v == h:
                return v

    for v in data_vars:
        low = v.lower()
        if any(h.lower() in low for h in DEPTH_VAR_HINTS):
            return v

    # fallback: first numeric 2D variable
    for v in data_vars:
        da = ds[v]
        if np.issubdtype(da.dtype, np.number) and da.ndim >= 2:
            return v

    return None


def normalize_lon_if_needed(ds: xr.Dataset, lon_name: str) -> xr.Dataset:
    lon = ds[lon_name]
    lon_values = np.asarray(lon.values)

    if np.nanmax(lon_values) > 180:
        ds = ds.assign_coords({lon_name: (((lon + 180) % 360) - 180)})
        ds = ds.sortby(lon_name)

    return ds


def subset_bbox(ds: xr.Dataset, lon_name: str, lat_name: str) -> xr.Dataset:
    ds = normalize_lon_if_needed(ds, lon_name)

    lon_vals = np.asarray(ds[lon_name].values)
    lat_vals = np.asarray(ds[lat_name].values)

    lon_slice = slice(ACEH_BBOX["min_lon"], ACEH_BBOX["max_lon"])
    if lat_vals[0] <= lat_vals[-1]:
        lat_slice = slice(ACEH_BBOX["min_lat"], ACEH_BBOX["max_lat"])
    else:
        lat_slice = slice(ACEH_BBOX["max_lat"], ACEH_BBOX["min_lat"])

    try:
        return ds.sel({lon_name: lon_slice, lat_name: lat_slice})
    except Exception:
        return ds


def safe_stats(arr: np.ndarray) -> Dict[str, Any]:
    a = np.asarray(arr, dtype=float)
    valid = a[np.isfinite(a)]

    if valid.size == 0:
        return {
            "count": 0,
            "nan_ratio": 1.0,
            "min": None,
            "p01": None,
            "p05": None,
            "p50": None,
            "p95": None,
            "p99": None,
            "max": None,
            "mean": None,
        }

    total = a.size
    return {
        "count": int(valid.size),
        "nan_ratio": float(1.0 - valid.size / total) if total else None,
        "min": float(np.nanmin(valid)),
        "p01": float(np.nanpercentile(valid, 1)),
        "p05": float(np.nanpercentile(valid, 5)),
        "p50": float(np.nanpercentile(valid, 50)),
        "p95": float(np.nanpercentile(valid, 95)),
        "p99": float(np.nanpercentile(valid, 99)),
        "max": float(np.nanmax(valid)),
        "mean": float(np.nanmean(valid)),
    }


def infer_depth_convention(arr: np.ndarray) -> Dict[str, Any]:
    a = np.asarray(arr, dtype=float)
    valid = a[np.isfinite(a)]

    if valid.size == 0:
        return {
            "convention": "unknown",
            "reason": "No valid numeric values.",
            "below_zero_ratio": None,
            "above_zero_ratio": None,
        }

    below = np.mean(valid < 0)
    above = np.mean(valid > 0)
    med = np.nanmedian(valid)
    amin = np.nanmin(valid)
    amax = np.nanmax(valid)

    if below > 0.5 and amin < -10:
        convention = "negative_below_sea"
        reason = "Mayoritas nilai laut tampaknya negatif; kedalaman laut kemungkinan disimpan sebagai elevasi negatif."
    elif above > 0.5 and amax > 10 and med > 0:
        convention = "positive_depth"
        reason = "Mayoritas nilai tampaknya positif; kedalaman laut kemungkinan sudah berupa depth positif."
    else:
        convention = "mixed_or_unclear"
        reason = "Nilai campuran atau tidak jelas; perlu diperiksa manual."

    return {
        "convention": convention,
        "reason": reason,
        "below_zero_ratio": float(below),
        "above_zero_ratio": float(above),
        "median": float(med),
        "min": float(amin),
        "max": float(amax),
    }


def convert_to_positive_depth(arr: np.ndarray, convention: str) -> np.ndarray:
    a = np.asarray(arr, dtype=float)

    if convention == "negative_below_sea":
        depth = np.where(a < 0, -a, np.nan)
    elif convention == "positive_depth":
        depth = np.where(a > 0, a, np.nan)
    else:
        # fallback heuristic
        valid = a[np.isfinite(a)]
        if valid.size and np.nanmedian(valid) < 0:
            depth = np.where(a < 0, -a, np.nan)
        else:
            depth = np.where(a > 0, a, np.nan)

    return depth


def estimate_resolution(coord_values: np.ndarray) -> Optional[float]:
    vals = np.asarray(coord_values, dtype=float)
    vals = vals[np.isfinite(vals)]
    if vals.size < 2:
        return None
    diffs = np.diff(np.sort(np.unique(vals)))
    diffs = diffs[np.isfinite(diffs)]
    if diffs.size == 0:
        return None
    return float(np.nanmedian(np.abs(diffs)))


def estimate_slope(depth: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> Dict[str, Any]:
    """
    Estimate slope magnitude from depth grid.
    Slope is approximate m/m using spherical degree-to-meter approximation.
    """
    d = np.asarray(depth, dtype=float)

    if d.ndim != 2:
        return {
            "available": False,
            "reason": f"Depth array is not 2D. ndim={d.ndim}",
        }

    lon_res = estimate_resolution(lon)
    lat_res = estimate_resolution(lat)

    if lon_res is None or lat_res is None:
        return {
            "available": False,
            "reason": "Cannot estimate lon/lat resolution.",
        }

    mean_lat = float(np.nanmean(lat))
    dy_m = lat_res * 111_320.0
    dx_m = lon_res * 111_320.0 * max(0.1, math.cos(math.radians(mean_lat)))

    if dx_m <= 0 or dy_m <= 0:
        return {
            "available": False,
            "reason": "Invalid dx/dy.",
        }

    # Fill missing values lightly with median only for gradient stability.
    valid = d[np.isfinite(d)]
    if valid.size == 0:
        return {
            "available": False,
            "reason": "No valid depth values.",
        }

    fill = float(np.nanmedian(valid))
    dd = np.where(np.isfinite(d), d, fill)

    try:
        grad_y, grad_x = np.gradient(dd, dy_m, dx_m)
        slope = np.sqrt(grad_x**2 + grad_y**2)
        slope = np.where(np.isfinite(d), slope, np.nan)
        stats = safe_stats(slope)
        return {
            "available": True,
            "unit": "m_per_m",
            "note": "Approximate bathymetric slope from positive depth.",
            "stats": stats,
        }
    except Exception as e:
        return {
            "available": False,
            "reason": str(e),
        }


def classify_usability(report: Dict[str, Any]) -> Dict[str, Any]:
    warnings = []
    score = 100

    coverage = report.get("coverage", {})
    stats = report.get("positive_depth_stats", {})
    convention = report.get("depth_convention", {}).get("convention")

    if not coverage.get("bbox_intersects_aceh", False):
        warnings.append("Coverage tidak jelas atau tidak memotong bbox Aceh.")
        score -= 40

    nan_ratio = stats.get("nan_ratio")
    if nan_ratio is not None and nan_ratio > 0.7:
        warnings.append("Terlalu banyak NaN pada subset Aceh.")
        score -= 30

    if convention == "mixed_or_unclear":
        warnings.append("Konvensi kedalaman belum jelas; perlu validasi manual.")
        score -= 20

    max_depth = stats.get("max")
    if max_depth is None or max_depth < 20:
        warnings.append("Rentang kedalaman terlalu kecil; mungkin bukan bathymetry laut.")
        score -= 30

    lon_res = report.get("resolution_deg", {}).get("lon")
    lat_res = report.get("resolution_deg", {}).get("lat")

    if lon_res is None or lat_res is None:
        warnings.append("Resolusi koordinat tidak dapat dihitung.")
        score -= 15
    elif lon_res > 0.2 or lat_res > 0.2:
        warnings.append("Resolusi relatif kasar; masih bisa untuk regional, tetapi kurang ideal untuk hotspot kecil.")
        score -= 10

    score = max(0, min(100, score))

    if score >= 80:
        verdict = "usable"
        label = "Sangat mungkin bisa digunakan untuk Physics-informed FGI."
    elif score >= 60:
        verdict = "usable_with_caution"
        label = "Bisa digunakan, tetapi perlu kehati-hatian dan mungkin perlu regrid/cek manual."
    else:
        verdict = "not_ready"
        label = "Belum siap digunakan tanpa perbaikan atau pemeriksaan manual."

    return {
        "score": score,
        "verdict": verdict,
        "label": label,
        "warnings": warnings,
    }


def inspect_netcdf(path: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "file": str(path),
        "file_name": path.name,
        "format": "netcdf_like",
        "ok": False,
    }

    try:
        ds = xr.open_dataset(path)
    except Exception as e:
        result["error"] = f"Cannot open dataset: {e}"
        return result

    result["dataset_dims"] = {str(k): int(v) for k, v in ds.sizes.items()}
    result["data_vars"] = list(map(str, ds.data_vars))
    result["coords"] = list(map(str, ds.coords))

    lon_name = detect_coord(ds, LON_HINTS)
    lat_name = detect_coord(ds, LAT_HINTS)
    depth_var = detect_depth_var(ds)

    result["detected"] = {
        "lon_name": lon_name,
        "lat_name": lat_name,
        "depth_var": depth_var,
    }

    if not lon_name or not lat_name or not depth_var:
        result["error"] = "Cannot detect lon/lat/depth variable."
        return result

    try:
        ds_sub = subset_bbox(ds, lon_name, lat_name)
        da = ds_sub[depth_var]

        # If variable has time/band dimension, pick first slice for inspection.
        while da.ndim > 2:
            first_dim = da.dims[0]
            da = da.isel({first_dim: 0})

        arr = np.asarray(da.values, dtype=float)
        lon = np.asarray(ds_sub[lon_name].values, dtype=float)
        lat = np.asarray(ds_sub[lat_name].values, dtype=float)

        lon_min = float(np.nanmin(lon)) if lon.size else None
        lon_max = float(np.nanmax(lon)) if lon.size else None
        lat_min = float(np.nanmin(lat)) if lat.size else None
        lat_max = float(np.nanmax(lat)) if lat.size else None

        bbox_intersects = (
            lon_min is not None
            and lon_max is not None
            and lat_min is not None
            and lat_max is not None
            and lon_max >= ACEH_BBOX["min_lon"]
            and lon_min <= ACEH_BBOX["max_lon"]
            and lat_max >= ACEH_BBOX["min_lat"]
            and lat_min <= ACEH_BBOX["max_lat"]
        )

        result["subset_shape"] = list(arr.shape)
        result["coverage"] = {
            "lon_min": lon_min,
            "lon_max": lon_max,
            "lat_min": lat_min,
            "lat_max": lat_max,
            "bbox_target": ACEH_BBOX,
            "bbox_intersects_aceh": bool(bbox_intersects),
        }
        result["resolution_deg"] = {
            "lon": estimate_resolution(lon),
            "lat": estimate_resolution(lat),
        }

        raw_stats = safe_stats(arr)
        convention = infer_depth_convention(arr)
        depth = convert_to_positive_depth(arr, convention["convention"])
        depth_stats = safe_stats(depth)

        valid_depth = depth[np.isfinite(depth)]
        if valid_depth.size:
            shelf_0_50 = float(np.mean((valid_depth >= 0) & (valid_depth <= 50)))
            shelf_50_200 = float(np.mean((valid_depth > 50) & (valid_depth <= 200)))
            slope_200_1000 = float(np.mean((valid_depth > 200) & (valid_depth <= 1000)))
            deep_gt_1000 = float(np.mean(valid_depth > 1000))
        else:
            shelf_0_50 = shelf_50_200 = slope_200_1000 = deep_gt_1000 = None

        result["raw_value_stats"] = raw_stats
        result["depth_convention"] = convention
        result["positive_depth_stats"] = depth_stats
        result["depth_zone_fraction"] = {
            "0_50m": shelf_0_50,
            "50_200m": shelf_50_200,
            "200_1000m": slope_200_1000,
            "gt_1000m": deep_gt_1000,
        }
        result["slope_estimate"] = estimate_slope(depth, lon, lat)
        result["ok"] = True
        result["usability"] = classify_usability(result)

    except Exception as e:
        result["error"] = f"Inspection failed: {e}"

    return to_builtin(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/raw/aceh_simeulue", help="Root folder to search bathymetry files.")
    parser.add_argument("--out", default="data/physics", help="Output folder for report JSON.")
    args = parser.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not root.exists():
        raise SystemExit(f"Folder tidak ditemukan: {root}")

    candidates = find_candidate_files(root)

    report: Dict[str, Any] = {
        "module": "bathymetry_inspection",
        "version": "0.1",
        "region": "Aceh-Simeulue",
        "root": str(root),
        "bbox": ACEH_BBOX,
        "candidate_count": len(candidates),
        "candidates": [str(p) for p in candidates],
        "results": [],
        "best_candidate": None,
    }

    if not candidates:
        print("Tidak ditemukan file bathymetry/netcdf di folder:", root)
        print("Coba cek manual:")
        print("find data/raw/aceh_simeulue -iname '*bathy*' -o -iname '*gebco*' -o -iname '*etopo*' -o -iname '*depth*'")
        out_file = out_dir / "bathymetry_report.json"
        out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        return

    for path in candidates:
        print(f"\nInspecting: {path}")
        res = inspect_netcdf(path)
        report["results"].append(res)

    usable = [
        r for r in report["results"]
        if r.get("ok") and r.get("usability", {}).get("score", 0) > 0
    ]

    if usable:
        usable_sorted = sorted(
            usable,
            key=lambda r: r.get("usability", {}).get("score", 0),
            reverse=True,
        )
        report["best_candidate"] = {
            "file": usable_sorted[0].get("file"),
            "score": usable_sorted[0].get("usability", {}).get("score"),
            "verdict": usable_sorted[0].get("usability", {}).get("verdict"),
            "label": usable_sorted[0].get("usability", {}).get("label"),
            "detected": usable_sorted[0].get("detected"),
        }

    out_file = out_dir / "bathymetry_report.json"
    out_file.write_text(json.dumps(to_builtin(report), indent=2, ensure_ascii=False))

    print("\n" + "=" * 72)
    print("NELAYA-AI Bathymetry Inspection Report")
    print("=" * 72)
    print(f"Candidate files : {len(candidates)}")
    print(f"Report saved    : {out_file}")

    if report["best_candidate"]:
        b = report["best_candidate"]
        print("\nBest candidate:")
        print(f"  File    : {b['file']}")
        print(f"  Score   : {b['score']}")
        print(f"  Verdict : {b['verdict']}")
        print(f"  Note    : {b['label']}")
        print(f"  Detect  : {b['detected']}")
    else:
        print("\nBelum ada kandidat yang jelas bisa digunakan.")

    print("\nRingkasan semua kandidat:")
    for r in report["results"]:
        print("-" * 72)
        print(f"File    : {r.get('file_name')}")
        print(f"OK      : {r.get('ok')}")
        if r.get("ok"):
            u = r.get("usability", {})
            c = r.get("depth_convention", {})
            d = r.get("positive_depth_stats", {})
            cov = r.get("coverage", {})
            print(f"Score   : {u.get('score')}")
            print(f"Verdict : {u.get('verdict')}")
            print(f"Depth convention : {c.get('convention')}")
            print(f"Depth max/median : {d.get('max')} / {d.get('p50')}")
            print(f"Coverage lon/lat : {cov.get('lon_min')}–{cov.get('lon_max')} / {cov.get('lat_min')}–{cov.get('lat_max')}")
            if u.get("warnings"):
                print("Warnings:")
                for w in u["warnings"]:
                    print(f"  - {w}")
        else:
            print(f"Error   : {r.get('error')}")


if __name__ == "__main__":
    main()
