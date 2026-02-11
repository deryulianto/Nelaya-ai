from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

import numpy as np
from netCDF4 import Dataset  # type: ignore

from ts_common import load_config, ensure_dirs


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _parse_depths(s: str) -> list[float]:
    # "0,10,20,30,50,75,100,150,200"
    out: list[float] = []
    for part in (s or "").split(","):
        part = part.strip()
        if not part:
            continue
        out.append(float(part))
    if not out:
        out = [0, 10, 20, 30, 50, 75, 100, 150, 200]
    return out


def _nanmean_safe(a: np.ndarray) -> float:
    a = np.asarray(a, dtype="float64")
    if a.size == 0:
        return float("nan")
    return float(np.nanmean(a))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/time_series_aceh.yaml")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--key", default="temp_profile", help="folder key under base_dir (default: temp_profile)")
    ap.add_argument("--var-name", default="thetao")
    ap.add_argument("--depths", default="0,10,20,30,50,75,100,150,200")
    args = ap.parse_args()

    cfg = load_config(args.config)
    day = _parse_date(args.date)
    day_str = day.strftime("%Y-%m-%d")

    depths_target = _parse_depths(args.depths)

    dirs = ensure_dirs(cfg, args.key)
    raw_nc = Path(dirs["raw"]) / f"{args.key}_raw_{day_str}.nc"
    if not raw_nc.exists():
        raise SystemExit(f"Raw NetCDF belum ada: {raw_nc}")

    out_daily = Path(dirs["daily"]) / f"{args.key}_daily_{day_str}.csv"
    out_series = Path(dirs["series"]) / f"{args.key}_daily_profile.csv"  # akumulasi semua tanggal

    with Dataset(str(raw_nc), "r") as ds:
        if args.var_name not in ds.variables:
            raise SystemExit(f"Var '{args.var_name}' tidak ditemukan di netcdf.")
        v = ds.variables[args.var_name]
        # ambil depth coordinate
        # nama dimensi biasanya "depth" / "deptht" / "depthu" tergantung produk
        depth_name = None
        for cand in ["depth", "deptht", "depthu", "depthv"]:
            if cand in ds.variables:
                depth_name = cand
                break
        if depth_name is None:
            raise SystemExit("Tidak menemukan coordinate depth di netcdf.")

        depth_vals = np.asarray(ds.variables[depth_name][:], dtype="float64")

        # baca array thetao
        arr = np.asarray(v[:], dtype="float64")

        # bentuk umum: (time, depth, lat, lon) atau (depth, lat, lon) atau (time, depth, y, x)
        if arr.ndim == 4:
            arr = arr[0]  # ambil time pertama (harian)
        elif arr.ndim == 3:
            # sudah (depth, lat, lon)
            pass
        else:
            raise SystemExit(f"Dimensi {args.var_name} tidak terduga: {arr.shape}")

        # handle _FillValue
        fill = getattr(v, "_FillValue", None)
        if fill is not None:
            arr = np.where(arr == float(fill), np.nan, arr)

        rows: list[tuple[str, float, float]] = []
        for d in depths_target:
            idx = int(np.argmin(np.abs(depth_vals - d)))
            d_real = float(depth_vals[idx])
            layer = arr[idx, :, :]
            mean_val = _nanmean_safe(layer)
            rows.append((day_str, d_real, mean_val))

    # tulis daily file (untuk tanggal ini)
    out_daily.parent.mkdir(parents=True, exist_ok=True)
    with open(out_daily, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "depth_m", "temp_c"])
        for (dt, d, t) in rows:
            # biar JSON aman nanti: kalau nan -> kosong
            if not np.isfinite(t):
                w.writerow([dt, f"{d:.3f}", ""])
            else:
                w.writerow([dt, f"{d:.3f}", f"{t:.6f}"])

    # append ke series akumulasi
    out_series.parent.mkdir(parents=True, exist_ok=True)
    is_new = not out_series.exists()
    with open(out_series, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["date", "depth_m", "temp_c"])
        for (dt, d, t) in rows:
            if not np.isfinite(t):
                w.writerow([dt, f"{d:.3f}", ""])
            else:
                w.writerow([dt, f"{d:.3f}", f"{t:.6f}"])

    print(f"[OK] saved profile daily csv: {out_daily}")
    print(f"[OK] appended profile series: {out_series}")


if __name__ == "__main__":
    main()
