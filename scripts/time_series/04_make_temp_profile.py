from __future__ import annotations

import argparse
from pathlib import Path
from datetime import datetime
import csv
import math

import numpy as np  # type: ignore
import xarray as xr  # type: ignore
import yaml  # type: ignore

ROOT = Path(__file__).resolve().parents[2]


def _parse_date(s: str) -> str:
    return datetime.strptime(s, "%Y-%m-%d").date().isoformat()


def _safe_float(x) -> float | None:
    try:
        v = float(x)
        if not math.isfinite(v):
            return None
        return v
    except Exception:
        return None


def _get_base_dir(cfg_path: str) -> Path:
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    base_dir = raw.get("base_dir")
    if not base_dir:
        raise SystemExit("base_dir belum ada di config.")
    return (ROOT / str(base_dir)).resolve()


def _find_depth_coord(ds: xr.Dataset, da: xr.DataArray) -> str:
    for cand in ["depth", "deptht", "lev", "z"]:
        if cand in da.dims or cand in ds.coords:
            return cand
    raise SystemExit("Tidak menemukan koordinat kedalaman (depth).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/time_series_aceh.yaml")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--var3d", default="temp3d", help="folder var untuk netcdf 3D (mis: temp3d)")
    ap.add_argument("--max-depth", type=float, default=200.0)
    ap.add_argument("--step", type=float, default=10.0)
    ap.add_argument("--var-name", default="thetao")
    args = ap.parse_args()

    day = _parse_date(args.date)
    base_dir = _get_base_dir(args.config)

    var3d = str(args.var3d or "temp3d").strip()
    nc = base_dir / var3d / "raw" / f"{var3d}_raw_{day}.nc"
    if not nc.exists():
        raise SystemExit(f"NetCDF tidak ditemukan: {nc}")

    ds = xr.open_dataset(nc)
    if args.var_name not in ds:
        raise SystemExit(f"Variable '{args.var_name}' tidak ada di NetCDF: {nc}")

    da = ds[args.var_name]
    if "time" in da.dims:
        da = da.isel(time=0)

    depth_coord = _find_depth_coord(ds, da)
    depth_vals = np.asarray(ds[depth_coord].values).astype(float)

    target_depths = np.arange(0.0, float(args.max_depth) + 1e-6, float(args.step), dtype=float)

    pts = []
    for td in target_depths:
        idx = int(np.argmin(np.abs(depth_vals - td)))
        d = float(depth_vals[idx])
        if d > float(args.max_depth) + 1e-9:
            continue

        slice_da = da.sel({depth_coord: d}, method="nearest")
        # mean spasial (lon/lat)
        val = _safe_float(float(slice_da.mean(skipna=True).values))
        if val is None:
            continue
        pts.append({"depth_m": round(d, 3), "temp_c": float(val)})

    pts.sort(key=lambda x: x["depth_m"])

    # ---- output DAILY (buat endpoint prioritas) ----
    out_daily_dir = base_dir / "temp_profile" / "daily"
    out_daily_dir.mkdir(parents=True, exist_ok=True)
    out_daily = out_daily_dir / f"temp_profile_daily_{day}.csv"

    with out_daily.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["depth_m", "temp_c"])
        w.writeheader()
        for row in pts:
            w.writerow(row)

    # ---- output SERIES (long format) ----
    out_series_dir = base_dir / "temp_profile" / "series"
    out_series_dir.mkdir(parents=True, exist_ok=True)
    out_series = out_series_dir / "temp_profile_daily_profile.csv"

    existing = []
    if out_series.exists():
        with out_series.open("r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                if (row.get("date") or "").strip() != day:
                    existing.append(row)

    with out_series.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "depth_m", "temp_c"])
        w.writeheader()

        for row in existing:
            w.writerow(
                {
                    "date": (row.get("date") or "").strip(),
                    "depth_m": (row.get("depth_m") or "").strip(),
                    "temp_c": (row.get("temp_c") or "").strip(),
                }
            )

        for row in pts:
            w.writerow({"date": day, "depth_m": row["depth_m"], "temp_c": row["temp_c"]})

    print(f"[OK] temp_profile DAILY  : {out_daily} (points={len(pts)})")
    print(f"[OK] temp_profile SERIES : {out_series} (date={day}, points={len(pts)})")


if __name__ == "__main__":
    main()
