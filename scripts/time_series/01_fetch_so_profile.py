from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import time

import copernicusmarine  # type: ignore
import yaml  # type: ignore


ROOT = Path(__file__).resolve().parents[2]


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _newest_nc(folder: Path, since_ts: float) -> Path | None:
    ncs = [p for p in folder.glob("*.nc") if p.is_file() and p.stat().st_mtime >= since_ts]
    if not ncs:
        return None
    return sorted(ncs, key=lambda p: p.stat().st_mtime)[-1]


def _load_raw_cfg(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return raw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/time_series_aceh.yaml")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today - lag_days)")
    ap.add_argument("--lag-days", type=int, default=None)

    ap.add_argument(
        "--dataset-id",
        default="cmems_mod_glo_phy-so_anfc_0.083deg_P1D-m",
        help="Dataset id salinity 3D (default: cmems_mod_glo_phy-so_anfc_0.083deg_P1D-m)",
    )
    ap.add_argument("--var-name", default="so")
    ap.add_argument(
        "--key",
        default="sal3d",
        help="folder key under base_dir (default: sal3d)",
    )
    ap.add_argument("--start-depth", type=float, default=0.0)
    ap.add_argument("--end-depth", type=float, default=200.0)

    args = ap.parse_args()

    raw = _load_raw_cfg(args.config)
    base_dir = raw.get("base_dir")
    if not base_dir:
        raise SystemExit("base_dir belum ada di config.")

    bbox = raw.get("bbox") or {}
    min_lon = bbox.get("min_lon")
    max_lon = bbox.get("max_lon")
    min_lat = bbox.get("min_lat")
    max_lat = bbox.get("max_lat")

    if None in (min_lon, max_lon, min_lat, max_lat):
        raise SystemExit("bbox belum lengkap di config.")

    lag = int(raw.get("default_lag_days", 0)) if args.lag_days is None else int(args.lag_days)
    day = _parse_date(args.date) if args.date else (datetime.utcnow() - timedelta(days=lag))
    day_str = day.strftime("%Y-%m-%d")

    out_dir = (ROOT / str(base_dir) / args.key / "raw").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_nc = out_dir / f"{args.key}_raw_{day_str}.nc"

    since_ts = time.time()

    subset_kwargs = dict(
        dataset_id=args.dataset_id,
        variables=[args.var_name],
        minimum_longitude=float(min_lon),
        maximum_longitude=float(max_lon),
        minimum_latitude=float(min_lat),
        maximum_latitude=float(max_lat),
        start_datetime=f"{day_str}T00:00:00",
        end_datetime=f"{day_str}T23:59:59",
        minimum_depth=float(args.start_depth),
        maximum_depth=float(args.end_depth),
        output_directory=str(out_dir),
        output_filename=out_nc.name,
        force_download=True,
    )

    print(f"[RUN] fetch so profile 3D -> {out_nc}")
    copernicusmarine.subset(**subset_kwargs)

    newest = _newest_nc(out_dir, since_ts)
    if newest is None:
        if out_nc.exists():
            newest = out_nc
        else:
            raise SystemExit(f"Gagal menemukan output NetCDF baru di {out_dir}")

    if newest != out_nc:
        newest.replace(out_nc)

    print(f"[OK] saved raw profile nc: {out_nc}")


if __name__ == "__main__":
    main()
