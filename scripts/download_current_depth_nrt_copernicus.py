#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT = Path(".")
OUT_ROOT = ROOT / "data" / "raw" / "aceh_simeulue" / "cur_depth_nrt"
REPORT_FILE = ROOT / "data" / "physics" / "current_depth_download_report.json"

DATASET_ID = "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m"


def run_cmd(cmd: list[str]) -> tuple[int, str]:
    print("[RUN]", " ".join(cmd), flush=True)
    p = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return p.returncode, p.stdout


def inspect_netcdf(path: Path) -> dict:
    try:
        import numpy as np
        import xarray as xr

        ds = xr.open_dataset(path, cache=False, decode_times=False)

        coords = list(ds.coords)
        dims = {k: int(v) for k, v in ds.sizes.items()}
        vars_ = list(ds.data_vars)

        depth_name = None
        for cand in ["depth", "depthu", "depthv", "lev"]:
            if cand in ds.coords or cand in ds.dims:
                depth_name = cand
                break

        depth_values = []
        if depth_name:
            vals = ds[depth_name].values
            vals = np.asarray(vals).astype(float).ravel()
            depth_values = [float(x) for x in vals if np.isfinite(x)]

        return {
            "ok": True,
            "dims": dims,
            "coords": coords,
            "data_vars": vars_,
            "depth_name": depth_name,
            "depth_values_m": depth_values,
            "depth_count": len(depth_values),
            "uo_dims": list(ds["uo"].dims) if "uo" in ds else None,
            "vo_dims": list(ds["vo"].dims) if "vo" in ds else None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-back", type=int, default=7)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD. Jika kosong, coba hari ini mundur.")
    parser.add_argument("--min-lon", type=float, default=92.0)
    parser.add_argument("--max-lon", type=float, default=99.0)
    parser.add_argument("--min-lat", type=float, default=1.0)
    parser.add_argument("--max-lat", type=float, default=7.0)
    parser.add_argument("--min-depth", type=float, default=0.0)
    parser.add_argument("--max-depth", type=float, default=120.0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    today = datetime.now(ZoneInfo("Asia/Jakarta")).date()

    if args.date:
        dates = [datetime.strptime(args.date, "%Y-%m-%d").date()]
    else:
        dates = [today - timedelta(days=i) for i in range(0, args.days_back + 1)]

    attempts = []

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    for d in dates:
        date_str = d.strftime("%Y-%m-%d")
        y = d.strftime("%Y")
        m = d.strftime("%m")

        out_dir = OUT_ROOT / y / m
        out_dir.mkdir(parents=True, exist_ok=True)

        out_name = f"current_depth_nrt_aceh_{date_str}.nc"
        out_path = out_dir / out_name

        if out_path.exists() and not args.overwrite:
            info = inspect_netcdf(out_path)
            report = {
                "ok": True,
                "status": "existing_file_used",
                "date": date_str,
                "file": str(out_path),
                "dataset_id": DATASET_ID,
                "inspect": info,
                "attempts": attempts,
            }
            REPORT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False))
            print("[OK] existing:", out_path)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return

        if out_path.exists() and args.overwrite:
            out_path.unlink()

        cmd = [
            "copernicusmarine",
            "subset",
            "--dataset-id",
            DATASET_ID,
            "--variable",
            "uo",
            "--variable",
            "vo",
            "--minimum-longitude",
            str(args.min_lon),
            "--maximum-longitude",
            str(args.max_lon),
            "--minimum-latitude",
            str(args.min_lat),
            "--maximum-latitude",
            str(args.max_lat),
            "--start-datetime",
            f"{date_str}T00:00:00",
            "--end-datetime",
            f"{date_str}T23:59:59",
            "--minimum-depth",
            str(args.min_depth),
            "--maximum-depth",
            str(args.max_depth),
            "--output-directory",
            str(out_dir.resolve()),
            "--output-filename",
            out_name,
            "--force-download",
        ]

        code, output = run_cmd(cmd)

        attempt = {
            "date": date_str,
            "returncode": code,
            "target_file": str(out_path),
            "output_tail": output[-3000:],
        }
        attempts.append(attempt)

        if code == 0 and out_path.exists() and out_path.stat().st_size > 0:
            info = inspect_netcdf(out_path)
            report = {
                "ok": True,
                "status": "downloaded",
                "date": date_str,
                "file": str(out_path),
                "dataset_id": DATASET_ID,
                "bbox": {
                    "min_lon": args.min_lon,
                    "max_lon": args.max_lon,
                    "min_lat": args.min_lat,
                    "max_lat": args.max_lat,
                    "min_depth": args.min_depth,
                    "max_depth": args.max_depth,
                },
                "inspect": info,
                "attempts": attempts,
            }
            REPORT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False))
            print("[OK] downloaded:", out_path)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return

        print(f"[WARN] failed for {date_str}", flush=True)

    report = {
        "ok": False,
        "status": "all_attempts_failed",
        "dataset_id": DATASET_ID,
        "attempts": attempts,
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
