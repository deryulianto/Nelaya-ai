from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import time

import copernicusmarine  # type: ignore
import yaml  # type: ignore

from ts_common import load_config, ensure_dirs


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _newest_nc(folder: Path, since_ts: float) -> Path | None:
    ncs = [p for p in folder.glob("*.nc") if p.is_file() and p.stat().st_mtime >= since_ts]
    if not ncs:
        return None
    return sorted(ncs, key=lambda p: p.stat().st_mtime)[-1]


def _get_var_cfg_raw(config_path: str, var: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return dict((raw.get("vars") or {}).get(var) or {})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/time_series_aceh.yaml")
    ap.add_argument("--var", required=True)  # contoh: temp50
    ap.add_argument("--date", help="YYYY-MM-DD (default: today - lag_days)")
    ap.add_argument("--lag-days", type=int, default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    lag = cfg.default_lag_days if args.lag_days is None else int(args.lag_days)

    day = _parse_date(args.date) if args.date else (datetime.utcnow() - timedelta(days=lag))
    day_str = day.strftime("%Y-%m-%d")

    if args.var not in cfg.vars:
        raise SystemExit(f"var '{args.var}' tidak ada di config vars.")

    spec = cfg.vars[args.var]
    raw_var = _get_var_cfg_raw(args.config, args.var)

    dataset_id = raw_var.get("dataset_id") or getattr(spec, "dataset_id", None)
    if not dataset_id or "FILL_ME" in str(dataset_id):
        raise SystemExit(f"dataset_id untuk '{args.var}' belum diisi di config.")

    var_name = raw_var.get("var_name") or getattr(spec, "var_name", None)
    if not var_name:
        raise SystemExit(f"var_name untuk '{args.var}' belum diisi (mis: thetao).")

    depth_m = raw_var.get("depth_m") or getattr(spec, "depth_m", None)
    if depth_m is None:
        raise SystemExit(f"depth_m untuk '{args.var}' belum diisi (mis: 50).")

    dirs = ensure_dirs(cfg, args.var)

    out_nc = dirs["raw"] / f"{args.var}_raw_{day_str}.nc"
    out_name = out_nc.name

    time_min = f"{day_str}T00:00:00"
    time_max = f"{day_str}T00:00:00"

    # kalau hourly → ambil full day
    if str(dataset_id).endswith("PT1H-m"):
        time_min = f"{day_str}T00:00:00"
        time_max = f"{day_str}T23:00:00"

    bbox = cfg.bbox
    since = time.time()

    subset_kwargs = dict(
        dataset_id=str(dataset_id),
        variables=[str(var_name)],
        minimum_longitude=bbox.min_lon,
        maximum_longitude=bbox.max_lon,
        minimum_latitude=bbox.min_lat,
        maximum_latitude=bbox.max_lat,
        start_datetime=time_min,
        end_datetime=time_max,
        minimum_depth=float(depth_m),
        maximum_depth=float(depth_m),
        output_directory=str(dirs["raw"]),
        output_filename=out_name,
    )

    copernicusmarine.subset(**subset_kwargs)

    if out_nc.exists():
        print(f"[OK] saved netcdf: {out_nc}")
        return

    newest = _newest_nc(dirs["raw"], since_ts=since - 5)
    if newest and newest.exists():
        newest.rename(out_nc)
        print(f"[OK] saved netcdf (renamed): {out_nc}")
        return

    raise SystemExit("[ERR] Subset selesai tapi file NetCDF tidak ditemukan.")


if __name__ == "__main__":
    main()
