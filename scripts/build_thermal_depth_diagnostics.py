#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import h5py
import numpy as np

ROOT = Path(".")
THERMAL_ROOT = ROOT / "data" / "raw" / "aceh_simeulue" / "thermal_depth_nrt"
OUT_DIR = ROOT / "data" / "physics"

TARGET_DEPTHS = {
    "shallow_30m": 30.0,
    "mid_50m": 50.0,
    "deep_75m": 75.0,
    "tuna_100m": 100.0,
}


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


def clean_temperature_c(temp, attrs=None):
    attrs = attrs or {}
    arr = np.asarray(temp, dtype=float).copy()

    for key in ["_FillValue", "missing_value"]:
        if key in attrs:
            try:
                fv = float(attrs[key])
                arr[np.isclose(arr, fv, rtol=1e-6, atol=0.0)] = np.nan
            except Exception:
                pass

    arr[(arr < -5.0) | (arr > 45.0)] = np.nan
    return arr


def thermal_suitability_score(temp_c):
    t = clean_temperature_c(temp_c)
    out = np.zeros_like(t, dtype=float)

    cold0 = 12.0
    opt_lo = 20.0
    opt_hi = 29.5
    warm1 = 32.5

    m = (t >= cold0) & (t < opt_lo)
    out[m] = (t[m] - cold0) / max(1e-9, opt_lo - cold0)

    m = (t >= opt_lo) & (t <= opt_hi)
    out[m] = 1.0

    m = (t > opt_hi) & (t <= warm1)
    out[m] = 1.0 - (t[m] - opt_hi) / max(1e-9, warm1 - opt_hi)

    out[~np.isfinite(t)] = np.nan
    return np.clip(out, 0.0, 1.0)


def thermal_file_for_date(date):
    y, m, _ = date.split("-")
    return THERMAL_ROOT / y / m / f"thermal_depth_nrt_aceh_{date}.nc"


def nearest_depth(depths, target):
    idx = int(np.nanargmin(np.abs(np.asarray(depths, dtype=float) - target)))
    return idx, float(depths[idx])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    date = args.date
    path = thermal_file_for_date(date)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    out_npz = OUT_DIR / "thermal_depth_maps_today.npz"
    out_json = OUT_DIR / "thermal_depth_diagnostics_today.json"

    if not path.exists():
        diag = {
            "status": "missing",
            "version": "0.8.1-alpha.1",
            "snapshot_date": date,
            "source_file": str(path),
            "message": "Thermal thetao file tidak tersedia.",
            "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        }
        out_json.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")
        raise SystemExit(json.dumps(diag, indent=2, ensure_ascii=False))

    with h5py.File(path, "r") as f:
        thetao = np.asarray(f["thetao"][...], dtype=float)
        depth = np.asarray(f["depth"][...], dtype=float).ravel()
        lat = np.asarray(f["latitude"][...], dtype=float).ravel()
        lon = np.asarray(f["longitude"][...], dtype=float).ravel()

        attrs = {}
        try:
            attrs = {
                k: v.decode() if isinstance(v, bytes) else v
                for k, v in f["thetao"].attrs.items()
            }
        except Exception:
            attrs = {}

    if thetao.ndim == 4:
        thetao_3d = thetao[0, :, :, :]
    elif thetao.ndim == 3:
        thetao_3d = thetao
    else:
        raise SystemExit(f"Unexpected thetao shape: {thetao.shape}")

    temp_layers = []
    score_layers = []
    layer_summary = {}

    for key, target in TARGET_DEPTHS.items():
        idx, actual = nearest_depth(depth, target)
        temp = clean_temperature_c(thetao_3d[idx, :, :], attrs)
        score = thermal_suitability_score(temp)

        temp_layers.append(temp)
        score_layers.append(score)

        layer_summary[key] = {
            "target_depth_m": target,
            "actual_depth_m": actual,
            "temperature_stats_c": stats(temp),
            "thermal_score_stats": stats(score),
        }

    temp_mean = np.nanmean(np.stack(temp_layers, axis=0), axis=0)
    thermal_score = np.nanmean(np.stack(score_layers, axis=0), axis=0)
    valid = np.isfinite(thermal_score)

    diag = {
        "status": "ready",
        "version": "0.8.1-alpha.1",
        "snapshot_date": date,
        "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "source_file": str(path),
        "map_file": str(out_npz),
        "variable": "thetao",
        "units": attrs.get("units") or attrs.get("unit_long") or "degrees_C",
        "target_depth_layers": layer_summary,
        "temperature_mean_30_100_stats_c": stats(temp_mean),
        "thermal_score_stats": stats(thermal_score),
        "valid_grid_count": int(np.sum(valid)),
        "valid_fraction": safe_float(np.sum(valid) / max(1, thermal_score.size)),
        "interpretation": (
            "Thermal diagnostics membaca suhu bawah permukaan 30–100 m sebagai gate ekologis awal. "
            "Ini belum memasukkan dissolved oxygen, CHL/BGC, SSH/front, atau validasi tangkapan."
        ),
    }

    np.savez_compressed(
        out_npz,
        lat=lat,
        lon=lon,
        thermal_score=thermal_score,
        temperature_mean_30_100_c=temp_mean,
    )

    out_json.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "snapshot_date": date,
        "thermal_status": diag["status"],
        "temp_mean_30_100": diag["temperature_mean_30_100_stats_c"]["mean"],
        "thermal_score_mean": diag["thermal_score_stats"]["mean"],
        "valid_fraction": diag["valid_fraction"],
        "map_file": str(out_npz),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
