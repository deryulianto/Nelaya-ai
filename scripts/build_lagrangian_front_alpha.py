#!/usr/bin/env python3
"""
Build LFI Alpha - Lagrangian Front Index proxy.

Input:
- Copernicus/NRT current NetCDF containing uo/vo or equivalent u/v fields.

Output:
- data/physics/lagrangian_front_today.json
- data/physics/lagrangian_front_today.geojson

Scientific status:
- Alpha / indicative.
- Uses Eulerian current gradients as a proxy for Lagrangian front support.
- Not yet full FTLE/LCS particle tracking.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Reduce risk of NetCDF/HDF5 thread issues
os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


EARTH_RADIUS_M = 6_371_000.0


def latest_current_file(root: Path, date: Optional[str]) -> Path:
    if date:
        matches = sorted(root.glob(f"**/current_nrt_aceh_{date}.nc"))
        if not matches:
            raise FileNotFoundError(f"No current NRT file found for date={date} under {root}")
        return matches[-1]

    matches = sorted(root.glob("**/current_nrt_aceh_*.nc"))
    if not matches:
        raise FileNotFoundError(f"No current NRT files found under {root}")
    return matches[-1]


def open_dataset_safely(path: Path):
    import xarray as xr

    errors = []
    for engine in [None, "h5netcdf", "netcdf4", "scipy"]:
        try:
            if engine is None:
                return xr.open_dataset(path)
            return xr.open_dataset(path, engine=engine)
        except Exception as exc:
            errors.append(f"{engine or 'default'}: {type(exc).__name__}: {exc}")

    raise RuntimeError("Failed to open dataset:\n" + "\n".join(errors))


def find_name(candidates: List[str], names: List[str]) -> Optional[str]:
    low = {n.lower(): n for n in names}
    for c in candidates:
        if c.lower() in low:
            return low[c.lower()]
    return None


def pick_uv_vars(ds) -> Tuple[str, str]:
    vars_ = list(ds.data_vars)
    u_name = find_name(["uo", "u", "eastward_velocity", "water_u", "current_u", "current_u_ms"], vars_)
    v_name = find_name(["vo", "v", "northward_velocity", "water_v", "current_v", "current_v_ms"], vars_)
    if not u_name or not v_name:
        raise ValueError(f"Could not identify u/v variables. Available data_vars={vars_}")
    return u_name, v_name


def pick_lat_lon(ds, da) -> Tuple[str, str]:
    names = list(ds.coords) + list(da.dims)
    lat_name = find_name(["latitude", "lat", "y"], names)
    lon_name = find_name(["longitude", "lon", "x"], names)
    if not lat_name or not lon_name:
        raise ValueError(f"Could not identify lat/lon. coords={list(ds.coords)}, dims={list(da.dims)}")
    return lat_name, lon_name


def reduce_to_2d(da, lat_name: str, lon_name: str):
    # Select first index for non-spatial dims such as time/depth
    indexers = {}
    for dim in da.dims:
        if dim not in (lat_name, lon_name):
            indexers[dim] = 0
    if indexers:
        da = da.isel(indexers)

    if lat_name in da.dims and lon_name in da.dims:
        da = da.transpose(lat_name, lon_name)

    return da


def robust_norm(x: np.ndarray, mask: np.ndarray, p_low=2, p_high=98) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    vals = x[mask & np.isfinite(x)]
    if vals.size < 10:
        return out

    lo = np.nanpercentile(vals, p_low)
    hi = np.nanpercentile(vals, p_high)
    if not np.isfinite(lo) or not np.isfinite(hi) or abs(hi - lo) < 1e-12:
        return out

    out[mask] = (x[mask] - lo) / (hi - lo)
    return np.clip(out, 0.0, 1.0)


def safe_gradient(field: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Return d(field)/dy and d(field)/dx in per meter.
    field shape: lat x lon.
    """
    lat_rad = np.deg2rad(lat)
    dlat_rad = np.gradient(np.deg2rad(lat))
    dlon_rad = np.gradient(np.deg2rad(lon))

    dy = dlat_rad[:, None] * EARTH_RADIUS_M
    dx = dlon_rad[None, :] * EARTH_RADIUS_M * np.cos(lat_rad[:, None])

    # Avoid division by zero near odd grids
    dy = np.where(np.abs(dy) < 1e-9, np.nan, dy)
    dx = np.where(np.abs(dx) < 1e-9, np.nan, dx)

    grad_lat_index = np.gradient(field, axis=0)
    grad_lon_index = np.gradient(field, axis=1)

    df_dy = grad_lat_index / dy
    df_dx = grad_lon_index / dx
    return df_dy, df_dx


def dominant_driver(conv_n: float, shear_n: float, vort_n: float, spgrad_n: float) -> str:
    drivers = {
        "current_convergence": conv_n,
        "current_shear": shear_n,
        "current_vorticity": vort_n,
        "speed_gradient": spgrad_n,
    }
    best = max(drivers, key=drivers.get)
    if best == "current_convergence":
        return "current_convergence_dominant"
    if best == "current_shear":
        return "current_shear_dominant"
    if best == "current_vorticity":
        return "current_vorticity_dominant"
    return "current_speed_gradient_dominant"


def interpret_driver(driver: str) -> str:
    if driver == "current_convergence_dominant":
        return "indikasi zona pertemuan massa air permukaan"
    if driver == "current_shear_dominant":
        return "indikasi penajaman/pergeseran arus yang dapat membentuk front dinamis"
    if driver == "current_vorticity_dominant":
        return "indikasi pusaran/rotasi lokal pada medan arus permukaan"
    return "indikasi perubahan tajam kecepatan arus permukaan"


def top_spaced_cells(
    lfi: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    mask: np.ndarray,
    top_k: int = 25,
    min_distance_deg: float = 0.12,
) -> List[Tuple[int, int]]:
    candidates = np.argwhere(mask & np.isfinite(lfi))
    if candidates.size == 0:
        return []

    scores = lfi[candidates[:, 0], candidates[:, 1]]
    order = np.argsort(scores)[::-1]

    selected: List[Tuple[int, int]] = []
    for idx in order:
        i, j = int(candidates[idx, 0]), int(candidates[idx, 1])
        la, lo = float(lat[i]), float(lon[j])

        too_close = False
        for si, sj in selected:
            dla = la - float(lat[si])
            dlo = lo - float(lon[sj])
            if math.sqrt(dla * dla + dlo * dlo) < min_distance_deg:
                too_close = True
                break

        if not too_close:
            selected.append((i, j))

        if len(selected) >= top_k:
            break

    return selected


def label_strength(max_lfi: float, top_mean: float) -> str:
    if max_lfi >= 0.78 or top_mean >= 0.68:
        return "kuat"
    if max_lfi >= 0.58 or top_mean >= 0.48:
        return "sedang"
    if max_lfi >= 0.35:
        return "lemah"
    return "sangat lemah"


def build_lfi(input_path: Path, out_json: Path, out_geojson: Path, top_k: int) -> Dict[str, Any]:
    ds = open_dataset_safely(input_path)

    u_var, v_var = pick_uv_vars(ds)
    lat_name, lon_name = pick_lat_lon(ds, ds[u_var])

    u_da = reduce_to_2d(ds[u_var], lat_name, lon_name)
    v_da = reduce_to_2d(ds[v_var], lat_name, lon_name)

    lat = np.asarray(ds[lat_name].values, dtype=float)
    lon = np.asarray(ds[lon_name].values, dtype=float)

    # Handle 2D lat/lon by reducing if needed
    if lat.ndim == 2:
        lat = lat[:, 0]
    if lon.ndim == 2:
        lon = lon[0, :]

    u = np.asarray(u_da.values, dtype=float)
    v = np.asarray(v_da.values, dtype=float)

    if u.shape != v.shape:
        raise ValueError(f"u/v shape mismatch: {u.shape} vs {v.shape}")
    if u.shape != (lat.size, lon.size):
        raise ValueError(f"Unexpected shape. u={u.shape}, lat={lat.size}, lon={lon.size}")

    # Basic physical sanity mask
    speed = np.sqrt(u * u + v * v)
    mask = (
        np.isfinite(u)
        & np.isfinite(v)
        & np.isfinite(speed)
        & (np.abs(u) < 5.0)
        & (np.abs(v) < 5.0)
        & (speed < 5.0)
    )

    # Fill invalid with nan; gradient will propagate some nan
    u2 = np.where(mask, u, np.nan)
    v2 = np.where(mask, v, np.nan)
    s2 = np.where(mask, speed, np.nan)

    du_dy, du_dx = safe_gradient(u2, lat, lon)
    dv_dy, dv_dx = safe_gradient(v2, lat, lon)
    ds_dy, ds_dx = safe_gradient(s2, lat, lon)

    divergence = du_dx + dv_dy
    convergence = -divergence
    convergence_pos = np.where(convergence > 0, convergence, 0.0)

    shear = np.sqrt((du_dx - dv_dy) ** 2 + (du_dy + dv_dx) ** 2)
    vorticity = dv_dx - du_dy
    speed_gradient = np.sqrt(ds_dx ** 2 + ds_dy ** 2)

    valid = (
        mask
        & np.isfinite(convergence_pos)
        & np.isfinite(shear)
        & np.isfinite(vorticity)
        & np.isfinite(speed_gradient)
    )

    conv_n = robust_norm(convergence_pos, valid)
    shear_n = robust_norm(shear, valid)
    vort_n = robust_norm(np.abs(vorticity), valid)
    spgrad_n = robust_norm(speed_gradient, valid)

    lfi = (
        0.40 * conv_n
        + 0.35 * shear_n
        + 0.15 * spgrad_n
        + 0.10 * vort_n
    )
    lfi = np.where(valid & np.isfinite(lfi), np.clip(lfi, 0.0, 1.0), np.nan)

    selected = top_spaced_cells(lfi, lat, lon, valid, top_k=top_k)

    top_zones = []
    for rank, (i, j) in enumerate(selected, start=1):
        c = float(conv_n[i, j]) if np.isfinite(conv_n[i, j]) else 0.0
        sh = float(shear_n[i, j]) if np.isfinite(shear_n[i, j]) else 0.0
        vo = float(vort_n[i, j]) if np.isfinite(vort_n[i, j]) else 0.0
        sg = float(spgrad_n[i, j]) if np.isfinite(spgrad_n[i, j]) else 0.0
        driver = dominant_driver(c, sh, vo, sg)

        top_zones.append(
            {
                "rank": rank,
                "lat": round(float(lat[i]), 5),
                "lon": round(float(lon[j]), 5),
                "lfi_score": round(float(lfi[i, j]), 4),
                "current_speed_ms": round(float(speed[i, j]), 4),
                "u_ms": round(float(u[i, j]), 4),
                "v_ms": round(float(v[i, j]), 4),
                "components": {
                    "convergence_score": round(c, 4),
                    "shear_score": round(sh, 4),
                    "vorticity_score": round(vo, 4),
                    "speed_gradient_score": round(sg, 4),
                },
                "driver": driver,
                "interpretation": interpret_driver(driver),
            }
        )

    valid_lfi = lfi[valid & np.isfinite(lfi)]
    mean_lfi = float(np.nanmean(valid_lfi)) if valid_lfi.size else None
    max_lfi = float(np.nanmax(valid_lfi)) if valid_lfi.size else None

    top_scores = [z["lfi_score"] for z in top_zones[:10]]
    top_mean = float(np.mean(top_scores)) if top_scores else 0.0
    strength = label_strength(max_lfi or 0.0, top_mean)

    date_from_name = None
    stem = input_path.stem
    if stem.startswith("current_nrt_aceh_"):
        date_from_name = stem.replace("current_nrt_aceh_", "")

    result = {
        "version": "0.1-alpha",
        "product": "LFI - Lagrangian Front Index Alpha",
        "date": date_from_name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "method": "surface_current_gradient_proxy",
        "method_note": (
            "Alpha proxy based on surface current convergence, shear, vorticity, "
            "and current-speed gradient. This is not yet full FTLE/LCS particle tracking."
        ),
        "input": {
            "source_path": str(input_path),
            "u_variable": u_var,
            "v_variable": v_var,
            "lat_name": lat_name,
            "lon_name": lon_name,
            "grid_shape": {"lat": int(lat.size), "lon": int(lon.size)},
            "bbox": {
                "lat_min": round(float(np.nanmin(lat)), 5),
                "lat_max": round(float(np.nanmax(lat)), 5),
                "lon_min": round(float(np.nanmin(lon)), 5),
                "lon_max": round(float(np.nanmax(lon)), 5),
            },
        },
        "summary": {
            "mean_lfi": round(mean_lfi, 4) if mean_lfi is not None else None,
            "max_lfi": round(max_lfi, 4) if max_lfi is not None else None,
            "top10_mean_lfi": round(top_mean, 4),
            "front_strength_label": strength,
            "valid_grid_cells": int(np.sum(valid)),
            "main_message": (
                f"LFI Alpha mendeteksi indikasi dukungan front dinamis permukaan kategori {strength}. "
                "Sinyal ini perlu dibaca sebagai dukungan oseanografi awal, bukan prediksi pasti lokasi ikan."
            ),
        },
        "top_zones": top_zones,
        "weights": {
            "convergence": 0.40,
            "shear": 0.35,
            "speed_gradient": 0.15,
            "vorticity": 0.10,
        },
        "scientific_caution": (
            "LFI Alpha bersifat indikatif. Resolusi data arus global/regional belum cukup untuk klaim presisi "
            "pada skala mikro-pesisir, muara kecil, atau zona sangat dekat pantai. Validasi trip nelayan tetap diperlukan."
        ),
        "next_step": [
            "Integrasi ringan ke FGI sebagai fgi_lagrangian_aware dengan bobot awal 10-15%.",
            "Bangun particle drift 24-72 jam untuk LFI Beta.",
            "Bangun FTLE/LCS forward-backward untuk LFI Scientific.",
        ],
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    features = []
    for z in top_zones:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [z["lon"], z["lat"]],
                },
                "properties": z,
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "name": "lagrangian_front_today_alpha",
        "features": features,
    }
    out_geojson.write_text(json.dumps(geojson, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        ds.close()
    except Exception:
        pass

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Date YYYY-MM-DD. Default: latest file.")
    parser.add_argument("--root", default="data/raw/aceh_simeulue/cur_nrt")
    parser.add_argument("--out-json", default="data/physics/lagrangian_front_today.json")
    parser.add_argument("--out-geojson", default="data/physics/lagrangian_front_today.geojson")
    parser.add_argument("--top-k", type=int, default=25)
    args = parser.parse_args()

    root = Path(args.root)
    input_path = latest_current_file(root, args.date)
    result = build_lfi(
        input_path=input_path,
        out_json=Path(args.out_json),
        out_geojson=Path(args.out_geojson),
        top_k=args.top_k,
    )

    print(json.dumps({
        "ok": True,
        "date": result.get("date"),
        "input": result["input"]["source_path"],
        "summary": result["summary"],
        "top_zone": result["top_zones"][0] if result["top_zones"] else None,
        "outputs": {
            "json": args.out_json,
            "geojson": args.out_geojson,
        }
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
