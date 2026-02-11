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


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


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

    # ✅ baru: var3d (folder key)
    ap.add_argument("--var3d", default=None, help="folder var untuk netcdf 3D (mis: temp3d)")

    # ✅ kompat: var (legacy)
    ap.add_argument("--var", default="temp3d", help="(legacy) folder var untuk netcdf 3D")

    ap.add_argument("--max-depth", type=float, default=200.0)
    ap.add_argument("--step", type=float, default=10.0)
    ap.add_argument("--var-name", default="thetao")
    args = ap.parse_args()

    var_key = str(args.var3d or args.var or "temp3d")

    day = _parse_date(args.date).strftime("%Y-%m-%d")
    base_dir = _get_base_dir(args.config)

    nc = base_dir / var_key / "raw" / f"{var_key}_raw_{day}.nc"
    if not nc.exists():
        raise SystemExit(f"NetCDF tidak ditemukan: {nc}")

    out_dir = base_dir / "temp_profile" / "series"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "temp_profile_daily_profile.csv"

    ds = xr.open_dataset(nc)
    if args.var_name not in ds:
        raise SystemExit(f"Variable '{args.var_name}' tidak ada di NetCDF.")

    da = ds[args.var_name]
    if "time" in da.dims:
        da = da.isel(time=0)

    depth_coord = _find_depth_coord(ds, da)
    depth_vals = np.asarray(ds[depth_coord].values).astype(float)

    # target kedalaman 0..max_depth per step
    target_depths = np.arange(0.0, float(args.max_depth) + 1e-6, float(args.step), dtype=float)

    rows = []
    for td in target_depths:
        idx = int(np.argmin(np.abs(depth_vals - td)))
        d = float(depth_vals[idx])

        if d > float(args.max_depth) + 1e-9:
            continue

        slice_da = da.sel({depth_coord: d}, method="nearest")
        val = _safe_float(float(slice_da.mean(skipna=True).values))
        if val is None:
            continue

        rows.append({"date": day, "depth_m": round(d, 3), "temp_c": val})

    rows.sort(key=lambda x: x["depth_m"])

    # keep existing except the same date
    existing = []
    if out_csv.exists():
        with open(out_csv, "r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                if (row.get("date") or "").strip() != day:
                    existing.append(row)

    fieldnames = ["date", "depth_m", "temp_c"]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()

        for row in existing:
            w.writerow(
                {
                    "date": (row.get("date") or "").strip(),
                    "depth_m": (row.get("depth_m") or "").strip(),
                    "temp_c": (row.get("temp_c") or "").strip(),
                }
            )

        for row in rows:
            w.writerow(row)

    print(f"[OK] temp profile saved: {out_csv} (date={day}, points={len(rows)})")


if __name__ == "__main__":
    main()
