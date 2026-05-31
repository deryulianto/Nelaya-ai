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
SSH_ROOT = ROOT / "data" / "raw" / "aceh_simeulue" / "ssh_anfc"
SSH_NRT_ROOT = ROOT / "data" / "raw" / "aceh_simeulue" / "ssh_nrt"
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


def robust_score_positive(arr):
    a = np.asarray(arr, dtype=float)
    out = np.full_like(a, np.nan, dtype=float)
    valid = a[np.isfinite(a)]

    if valid.size < 10:
        return out

    lo = float(np.nanpercentile(valid, 50))
    hi = float(np.nanpercentile(valid, 95))

    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        return out

    out = (a - lo) / (hi - lo)
    out = np.clip(out, 0.0, 1.0)
    out[~np.isfinite(a)] = np.nan
    return out


def clean_ssh_m(zos, attrs=None):
    attrs = attrs or {}
    arr = np.asarray(zos, dtype=float).copy()

    for key in ["_FillValue", "missing_value"]:
        if key in attrs:
            try:
                fv = float(np.asarray(attrs[key]).ravel()[0])
                arr[np.isclose(arr, fv, rtol=1e-6, atol=0.0)] = np.nan
            except Exception:
                pass

    # ZOS/SSH in meters; values outside this range are almost certainly fill/error for this use.
    arr[(arr < -5.0) | (arr > 5.0)] = np.nan
    return arr


def ssh_file_for_date(date):
    y, m, _ = date.split("-")

    candidates = [
        SSH_ROOT / y / m / f"ssh_aceh_{date}.nc",
        SSH_NRT_ROOT / y / m / f"ssh_aceh_{date}.nc",
        SSH_NRT_ROOT / "test" / f"ssh_test_{date}.nc",
    ]

    for p in candidates:
        if p.exists():
            return p

    return candidates[0]


def read_ssh_h5(path):
    with h5py.File(path, "r") as f:
        keys = list(f.keys())

        var_name = None
        for cand in ["zos", "adt", "sla", "ssh"]:
            if cand in f:
                var_name = cand
                break

        if var_name is None:
            raise RuntimeError(f"No SSH/ZOS variable found. keys={keys}")

        lat_name = "latitude" if "latitude" in f else "lat"
        lon_name = "longitude" if "longitude" in f else "lon"

        ssh = np.asarray(f[var_name][...], dtype=float)
        lat = np.asarray(f[lat_name][...], dtype=float).ravel()
        lon = np.asarray(f[lon_name][...], dtype=float).ravel()

        attrs = {}
        try:
            attrs = {
                k: v.decode() if isinstance(v, bytes) else v
                for k, v in f[var_name].attrs.items()
            }
        except Exception:
            attrs = {}

    return {
        "ssh": ssh,
        "lat": lat,
        "lon": lon,
        "var_name": var_name,
        "attrs": attrs,
    }


def compute_ssh_front(ssh_m, lat, lon):
    z = clean_ssh_m(ssh_m)

    # Expected shape can be time, lat, lon or lat, lon.
    if z.ndim == 3:
        z2 = z[0, :, :]
    elif z.ndim == 2:
        z2 = z
    else:
        raise RuntimeError(f"Unexpected SSH shape: {z.shape}")

    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)

    dlat = float(np.nanmedian(np.abs(np.gradient(lat)))) if lat.size > 1 else np.nan
    dlon = float(np.nanmedian(np.abs(np.gradient(lon)))) if lon.size > 1 else np.nan

    dy_m = max(1.0, dlat * 111_000.0)

    dz_dy = np.gradient(z2, axis=0) / dy_m

    coslat = np.cos(np.deg2rad(lat))
    dx_m = np.maximum(1.0, dlon * 111_000.0 * coslat)
    dz_dx = np.gradient(z2, axis=1) / dx_m[:, None]

    grad = np.sqrt(dz_dx ** 2 + dz_dy ** 2)

    # Scaled for readability; raw gradient remains available.
    front_score = robust_score_positive(grad)

    return z2, grad, front_score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    date = args.date
    path = ssh_file_for_date(date)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    out_npz = OUT_DIR / "ssh_front_maps_today.npz"
    out_json = OUT_DIR / "ssh_front_diagnostics_today.json"

    if not path.exists():
        diag = {
            "status": "missing",
            "version": "0.8.2-alpha.1",
            "snapshot_date": date,
            "source_file": str(path),
            "message": "SSH/ZOS file belum tersedia.",
            "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        }
        out_json.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")
        raise SystemExit(json.dumps(diag, indent=2, ensure_ascii=False))

    raw = read_ssh_h5(path)
    ssh2, grad, score = compute_ssh_front(raw["ssh"], raw["lat"], raw["lon"])

    valid = np.isfinite(score)

    diag = {
        "status": "ready",
        "version": "0.8.2-alpha.1",
        "snapshot_date": date,
        "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "source_file": str(path),
        "map_file": str(out_npz),
        "variable": raw["var_name"],
        "units": raw["attrs"].get("units") or "m",
        "ssh_m_stats": stats(ssh2),
        "ssh_gradient_m_per_m_stats": stats(grad),
        "ssh_front_score_stats": stats(score),
        "valid_grid_count": int(np.sum(valid)),
        "valid_fraction": safe_float(np.sum(valid) / max(1, score.size)),
        "interpretation": (
            "SSH/front diagnostics membaca gradien muka laut sebagai indikasi batas massa air, eddy, "
            "atau dinamika permukaan. Ini bukan klaim lokasi ikan dan harus dibaca bersama arus, thermal, "
            "SST, CHL, bathymetry, cuaca, keselamatan, dan pengalaman nelayan."
        ),
    }

    np.savez_compressed(
        out_npz,
        lat=raw["lat"],
        lon=raw["lon"],
        ssh_m=ssh2,
        ssh_gradient_m_per_m=grad,
        ssh_front_score=score,
    )

    out_json.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "snapshot_date": date,
        "ssh_status": diag["status"],
        "ssh_front_score_mean": diag["ssh_front_score_stats"]["mean"],
        "ssh_gradient_p95": diag["ssh_gradient_m_per_m_stats"]["p95"],
        "valid_fraction": diag["valid_fraction"],
        "map_file": str(out_npz),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
