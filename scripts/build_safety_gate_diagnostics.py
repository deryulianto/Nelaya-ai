#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import xarray as xr
import numpy as np

ROOT = Path(".")
RAW = ROOT / "data" / "raw" / "aceh_simeulue"
WAVE_ROOT = RAW / "wave_anfc"
WIND_ROOT = RAW / "wind_nrt"
OUT_DIR = ROOT / "data" / "physics"


def safe_float(x, default=None):
    try:
        v = float(x)
        if math.isfinite(v):
            return v
    except Exception:
        pass
    return default


def stats(arr):
    a = np.asarray(arr, dtype=float)
    valid = a[np.isfinite(a)]

    if valid.size == 0:
        return {
            "count": 0,
            "nan_ratio": 1.0,
            "min": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "max": None,
            "mean": None,
            "std": None,
        }

    return {
        "count": int(valid.size),
        "nan_ratio": float(1.0 - valid.size / max(1, a.size)),
        "min": safe_float(np.nanmin(valid)),
        "p25": safe_float(np.nanpercentile(valid, 25)),
        "p50": safe_float(np.nanpercentile(valid, 50)),
        "p75": safe_float(np.nanpercentile(valid, 75)),
        "p90": safe_float(np.nanpercentile(valid, 90)),
        "p95": safe_float(np.nanpercentile(valid, 95)),
        "max": safe_float(np.nanmax(valid)),
        "mean": safe_float(np.nanmean(valid)),
        "std": safe_float(np.nanstd(valid)),
    }


def find_latest(kind: str, date: str, max_back: int = 7) -> tuple[Path, str | None]:
    base = datetime.strptime(date, "%Y-%m-%d").date()

    for back in range(max_back + 1):
        d = base - timedelta(days=back)
        y = d.strftime("%Y")
        m = d.strftime("%m")
        ds = d.strftime("%Y-%m-%d")

        if kind == "wave":
            p = WAVE_ROOT / y / m / f"wave_aceh_{ds}.nc"
        elif kind == "wind":
            p = WIND_ROOT / y / m / f"wind_nrt_aceh_{ds}.nc"
        else:
            raise ValueError(kind)

        if p.exists() and p.stat().st_size > 0:
            return p, ds

    return Path(""), None



def wind_file_is_valid(path: Path) -> tuple[bool, dict]:
    try:
        raw_u = read_h5_grid(path, ["eastward_wind", "u10", "uwnd", "u"])
        raw_v = read_h5_grid(path, ["northward_wind", "v10", "vwnd", "v"])

        u = clean_physical(to_2d_mean(raw_u["array"]), -100.0, 100.0, raw_u["attrs"])
        v = clean_physical(to_2d_mean(raw_v["array"]), -100.0, 100.0, raw_v["attrs"])
        sp = np.sqrt(u ** 2 + v ** 2)

        valid = np.isfinite(sp)
        frac = float(np.sum(valid) / max(1, sp.size))
        mean = safe_float(np.nanmean(sp))

        return frac >= 0.25 and mean is not None, {
            "valid_fraction": frac,
            "mean_ms": mean,
            "finite_count": int(np.sum(valid)),
            "grid_count": int(sp.size),
        }
    except Exception as exc:
        return False, {
            "error": f"{type(exc).__name__}: {exc}",
        }


def find_latest_valid_wind(date: str, max_back: int = 14) -> tuple[Path, str | None, dict]:
    base = datetime.strptime(date, "%Y-%m-%d").date()
    attempts = []

    for back in range(max_back + 1):
        d = base - timedelta(days=back)
        y = d.strftime("%Y")
        m = d.strftime("%m")
        ds = d.strftime("%Y-%m-%d")
        path = WIND_ROOT / y / m / f"wind_nrt_aceh_{ds}.nc"

        if not path.exists() or path.stat().st_size <= 0:
            attempts.append({"date": ds, "file": str(path), "status": "missing"})
            continue

        ok, info = wind_file_is_valid(path)
        attempts.append({"date": ds, "file": str(path), "status": "valid" if ok else "invalid", **info})

        if ok:
            return path, ds, {"attempts": attempts}

    return Path(""), None, {"attempts": attempts}

def read_h5_grid(path: Path, var_candidates: list[str]) -> dict:
    """
    Read wave/wind using xarray+h5netcdf so scale_factor/add_offset,
    _FillValue, and CF decoding are handled safely.
    """
    ds = xr.open_dataset(path, engine="h5netcdf", cache=False)

    keys = list(ds.data_vars)
    var_name = None
    for v in var_candidates:
        if v in ds.data_vars:
            var_name = v
            break

    if var_name is None:
        raise RuntimeError(f"No variable from {var_candidates}. vars={keys}")

    lat_name = "latitude" if "latitude" in ds.coords else "lat"
    lon_name = "longitude" if "longitude" in ds.coords else "lon"

    arr = np.asarray(ds[var_name].values, dtype=float)
    lat = np.asarray(ds[lat_name].values, dtype=float).ravel()
    lon = np.asarray(ds[lon_name].values, dtype=float).ravel()
    attrs = dict(ds[var_name].attrs)

    return {
        "array": arr,
        "lat": lat,
        "lon": lon,
        "var_name": var_name,
        "attrs": attrs,
    }


def clean_physical(arr, min_val, max_val, attrs=None):
    attrs = attrs or {}
    a = np.asarray(arr, dtype=float).copy()

    for key in ["_FillValue", "missing_value"]:
        if key in attrs:
            try:
                fv = float(np.asarray(attrs[key]).ravel()[0])
                a[np.isclose(a, fv, rtol=1e-6, atol=0.0)] = np.nan
            except Exception:
                pass

    a[(a < min_val) | (a > max_val)] = np.nan
    return a


def to_2d_mean(arr):
    a = np.asarray(arr, dtype=float)
    if a.ndim == 3:
        return np.nanmean(a, axis=0)
    if a.ndim == 2:
        return a
    raise RuntimeError(f"Unexpected array shape: {a.shape}")


def nearest_regrid(src2d, src_lat, src_lon, dst_lat, dst_lon):
    src_lat = np.asarray(src_lat, dtype=float)
    src_lon = np.asarray(src_lon, dtype=float)
    dst_lat = np.asarray(dst_lat, dtype=float)
    dst_lon = np.asarray(dst_lon, dtype=float)

    lat_idx = np.abs(src_lat[:, None] - dst_lat[None, :]).argmin(axis=0)
    lon_idx = np.abs(src_lon[:, None] - dst_lon[None, :]).argmin(axis=0)

    return np.asarray(src2d, dtype=float)[np.ix_(lat_idx, lon_idx)]


def ramp(x, lo, hi):
    x = np.asarray(x, dtype=float)
    out = (x - lo) / max(1e-9, hi - lo)
    return np.clip(out, 0.0, 1.0)


def wave_risk_score(wave_m):
    """
    Small-fisher oriented wave risk.
    0 means low risk, 1 means high risk.
    """
    w = np.asarray(wave_m, dtype=float)
    risk = np.full_like(w, np.nan, dtype=float)

    risk = np.where(np.isfinite(w), 0.0, risk)
    risk = np.where((w > 0.75) & (w <= 1.50), 0.40 * ramp(w, 0.75, 1.50), risk)
    risk = np.where((w > 1.50) & (w <= 2.50), 0.40 + 0.40 * ramp(w, 1.50, 2.50), risk)
    risk = np.where(w > 2.50, 0.80 + 0.20 * ramp(w, 2.50, 3.50), risk)

    risk[~np.isfinite(w)] = np.nan
    return np.clip(risk, 0.0, 1.0)


def wind_risk_score(wind_ms):
    """
    Small-fisher oriented wind risk.
    0 means low risk, 1 means high risk.
    """
    u = np.asarray(wind_ms, dtype=float)
    risk = np.full_like(u, np.nan, dtype=float)

    risk = np.where(np.isfinite(u), 0.0, risk)
    risk = np.where((u > 5.0) & (u <= 8.0), 0.25 * ramp(u, 5.0, 8.0), risk)
    risk = np.where((u > 8.0) & (u <= 12.0), 0.25 + 0.35 * ramp(u, 8.0, 12.0), risk)
    risk = np.where(u > 12.0, 0.60 + 0.40 * ramp(u, 12.0, 16.0), risk)

    risk[~np.isfinite(u)] = np.nan
    return np.clip(risk, 0.0, 1.0)


def safety_label(score):
    s = safe_float(score)
    if s is None:
        return "tidak tersedia"
    if s >= 0.75:
        return "relatif aman"
    if s >= 0.55:
        return "hati-hati"
    if s >= 0.35:
        return "risiko meningkat"
    return "risiko tinggi"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--max-back", type=int, default=7)
    args = parser.parse_args()

    date = args.date
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    out_npz = OUT_DIR / "safety_gate_maps_today.npz"
    out_json = OUT_DIR / "safety_gate_diagnostics_today.json"

    wave_path, wave_date = find_latest("wave", date, args.max_back)
    wind_path, wind_date, wind_selection = find_latest_valid_wind(date, max(args.max_back, 14))

    if not wave_date or not wind_date:
        diag = {
            "status": "missing",
            "version": "0.8.3-alpha.1",
            "snapshot_date": date,
            "wave_file": str(wave_path) if wave_path else None,
            "wind_file": str(wind_path) if wind_path else None,
            "wave_source_date": wave_date,
            "wind_source_date": wind_date,
            "wind_selection": locals().get("wind_selection"),
            "message": "Wave/wind file belum lengkap atau wind tidak valid.",
            "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        }
        out_json.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")
        raise SystemExit(json.dumps(diag, indent=2, ensure_ascii=False))

    wave_raw = read_h5_grid(wave_path, ["VHM0", "hs", "swh", "significant_wave_height"])
    wind_u = read_h5_grid(wind_path, ["eastward_wind", "u10", "uwnd", "u"])
    wind_v = read_h5_grid(wind_path, ["northward_wind", "v10", "vwnd", "v"])

    wave = clean_physical(to_2d_mean(wave_raw["array"]), 0.0, 20.0, wave_raw["attrs"])

    u = clean_physical(to_2d_mean(wind_u["array"]), -100.0, 100.0, wind_u["attrs"])
    v = clean_physical(to_2d_mean(wind_v["array"]), -100.0, 100.0, wind_v["attrs"])
    wind_speed_src = np.sqrt(u ** 2 + v ** 2)

    # Regrid wind to wave grid.
    wind_speed = nearest_regrid(
        wind_speed_src,
        wind_u["lat"],
        wind_u["lon"],
        wave_raw["lat"],
        wave_raw["lon"],
    )

    wave_risk = wave_risk_score(wave)
    wind_risk = wind_risk_score(wind_speed)
    combined_risk = np.nanmax(np.stack([wave_risk, wind_risk], axis=0), axis=0)
    safety_score = 1.0 - combined_risk
    safety_score[~np.isfinite(combined_risk)] = np.nan

    valid = np.isfinite(safety_score)

    mean_safety = safe_float(np.nanmean(safety_score))

    diag = {
        "status": "ready",
        "version": "0.8.3-alpha.1",
        "snapshot_date": date,
        "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "wave_file": str(wave_path),
        "wind_file": str(wind_path),
        "wave_source_date": wave_date,
        "wind_source_date": wind_date,
        "wind_selection": wind_selection,
        "map_file": str(out_npz),
        "variables": {
            "wave": wave_raw["var_name"],
            "wind_u": wind_u["var_name"],
            "wind_v": wind_v["var_name"],
        },
        "wave_m_stats": stats(wave),
        "wind_speed_ms_stats": stats(wind_speed),
        "wave_risk_score_stats": stats(wave_risk),
        "wind_risk_score_stats": stats(wind_risk),
        "combined_risk_score_stats": stats(combined_risk),
        "safety_score_stats": stats(safety_score),
        "valid_grid_count": int(np.sum(valid)),
        "valid_fraction": safe_float(np.sum(valid) / max(1, safety_score.size)),
        "safety_label": safety_label(mean_safety),
        "interpretation": (
            "Safety Gate membaca gelombang dan angin sebagai batas kehati-hatian operasional. "
            "Skor ini bukan jaminan keselamatan, tetapi membantu menahan interpretasi peluang laut "
            "agar tidak mengabaikan risiko bagi nelayan kecil."
        ),
    }

    np.savez_compressed(
        out_npz,
        lat=wave_raw["lat"],
        lon=wave_raw["lon"],
        wave_m=wave,
        wind_speed_ms=wind_speed,
        wave_risk_score=wave_risk,
        wind_risk_score=wind_risk,
        combined_risk_score=combined_risk,
        safety_score=safety_score,
    )

    out_json.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "snapshot_date": date,
        "safety_status": diag["status"],
        "wave_source_date": wave_date,
        "wind_source_date": wind_date,
        "wave_mean_m": diag["wave_m_stats"]["mean"],
        "wind_mean_ms": diag["wind_speed_ms_stats"]["mean"],
        "safety_score_mean": diag["safety_score_stats"]["mean"],
        "safety_label": diag["safety_label"],
        "valid_fraction": diag["valid_fraction"],
        "map_file": str(out_npz),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
