from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import time

import copernicusmarine  # type: ignore

from ts_common import load_config, ensure_dirs


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _newest_nc(folder: Path, since_ts: float) -> Path | None:
    ncs = [p for p in folder.glob("*.nc") if p.is_file() and p.stat().st_mtime >= since_ts]
    if not ncs:
        return None
    return sorted(ncs, key=lambda p: p.stat().st_mtime)[-1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/time_series_aceh.yaml")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today - lag_days)")
    ap.add_argument("--lag-days", type=int, default=None)

    ap.add_argument(
        "--dataset-id",
        default="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
        help="Dataset id thetao 3D (default: cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m)",
    )
    ap.add_argument("--var-name", default="thetao")
    ap.add_argument("--min-depth", type=float, default=0.0)
    ap.add_argument("--max-depth", type=float, default=200.0)

    ap.add_argument("--key", default="temp_profile", help="folder key under base_dir (default: temp_profile)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    lag = cfg.default_lag_days if args.lag_days is None else int(args.lag_days)

    day = _parse_date(args.date) if args.date else (datetime.utcnow() - timedelta(days=lag))
    day_str = day.strftime("%Y-%m-%d")

    # simpan ke base_dir/<key>/raw
    dirs = ensure_dirs(cfg, args.key)

    out_nc = Path(dirs["raw"]) / f"{args.key}_raw_{day_str}.nc"
    out_name = out_nc.name

    time_min = f"{day_str}T00:00:00"
    time_max = f"{day_str}T00:00:00"

    bbox = cfg.bbox

    subset_kwargs = dict(
        dataset_id=args.dataset_id,
        variables=[args.var_name],
        minimum_longitude=bbox.min_lon,
        maximum_longitude=bbox.max_lon,
        minimum_latitude=bbox.min_lat,
        maximum_latitude=bbox.max_lat,
        start_datetime=time_min,
        end_datetime=time_max,
        minimum_depth=float(args.min_depth),
        maximum_depth=float(args.max_depth),
        output_directory=str(dirs["raw"]),
        output_filename=out_name,
    )

    since = time.time()
    copernicusmarine.subset(**subset_kwargs)

    if out_nc.exists():
        print(f"[OK] saved netcdf: {out_nc}")
        return

    newest = _newest_nc(Path(dirs["raw"]), since_ts=since - 10)
    if newest and newest.exists():
        newest.rename(out_nc)
        print(f"[OK] saved netcdf (renamed): {out_nc}")
        return

    print("[ERR] Subset selesai tapi file NetCDF tidak ditemukan.")
    print("[INFO] raw dir:", dirs["raw"])
    for p in sorted(Path(dirs["raw"]).glob("*"))[-20:]:
        print(" -", p.name)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
