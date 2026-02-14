from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import time

import yaml  # type: ignore
import copernicusmarine  # type: ignore

ROOT = Path(__file__).resolve().parents[2]


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _load_raw(cfg_path: str) -> dict:
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _ensure_dirs(base_dir: Path, var_key: str, raw_dirname: str) -> Path:
    d = base_dir / var_key / raw_dirname
    d.mkdir(parents=True, exist_ok=True)
    return d


def _newest_nc(folder: Path, since_ts: float) -> Path | None:
    ncs = [p for p in folder.glob("*.nc") if p.is_file() and p.stat().st_mtime >= since_ts]
    if not ncs:
        return None
    return sorted(ncs, key=lambda p: p.stat().st_mtime)[-1]


def _pick_dataset_id(day: datetime, vcfg: dict, var_key: str) -> str:
    """
    Pilih dataset_id untuk temp3d:
    - Kalau ada dataset_id_my / dataset_id_nrt:
        day <= today-60d -> MY
        else -> NRT (kalau ada) else MY
    - Kalau tidak -> dataset_id tunggal
    """
    did_my = (vcfg.get("dataset_id_my") or "").strip()
    did_nrt = (vcfg.get("dataset_id_nrt") or "").strip()
    did_one = (vcfg.get("dataset_id") or "").strip()

    if did_my or did_nrt:
        cutoff = (datetime.utcnow() - timedelta(days=60)).date()
        if day.date() <= cutoff:
            if not did_my:
                raise SystemExit(f"dataset_id_my untuk '{var_key}' belum diset di config.")
            return did_my

        if did_nrt:
            return did_nrt
        if did_my:
            return did_my
        raise SystemExit(f"Tidak ada dataset_id_my/nrt valid untuk '{var_key}'.")

    if (not did_one) or ("FILL_ME" in did_one):
        raise SystemExit(f"dataset_id untuk '{var_key}' belum diisi di config.")
    return did_one


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/time_series_aceh.yaml")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today - lag_days)")
    ap.add_argument("--lag-days", type=int, default=None)
    ap.add_argument("--var", default="temp3d")  # folder key
    args = ap.parse_args()

    raw = _load_raw(args.config)

    lag = int(raw.get("default_lag_days", 1) if args.lag_days is None else args.lag_days)
    day = _parse_date(args.date) if args.date else (datetime.utcnow() - timedelta(days=lag))
    day_str = day.strftime("%Y-%m-%d")

    base_dir = (ROOT / str(raw.get("base_dir"))).resolve()
    raw_dirname = str(raw.get("raw_dirname", "raw"))

    var_key = str(args.var).strip()
    vcfg = (raw.get("vars") or {}).get(var_key) or {}

    dataset_id = _pick_dataset_id(day, vcfg, var_key)
    var_name = str(vcfg.get("var_name") or "thetao").strip()

    bbox = raw.get("bbox") or {}
    min_lon = float(bbox.get("min_lon"))
    max_lon = float(bbox.get("max_lon"))
    min_lat = float(bbox.get("min_lat"))
    max_lat = float(bbox.get("max_lat"))

    # depth range 3D
    # default aman: surface physics sering mulai ~0.494 m
    min_depth = float(vcfg.get("min_depth", 0.49402499198913574))
    max_depth = float(vcfg.get("max_depth", 200))

    out_dir = _ensure_dirs(base_dir, var_key, raw_dirname)
    out_nc = out_dir / f"{var_key}_raw_{day_str}.nc"

    # ambil full day range (lebih “tahan banting” daripada start=end=00:00)
    time_min = f"{day_str}T00:00:00"
    time_max = f"{day_str}T23:59:59"

    subset_kwargs = dict(
        dataset_id=dataset_id,
        variables=[var_name],
        minimum_longitude=min_lon,
        maximum_longitude=max_lon,
        minimum_latitude=min_lat,
        maximum_latitude=max_lat,
        start_datetime=time_min,
        end_datetime=time_max,
        minimum_depth=min_depth,
        maximum_depth=max_depth,
        output_directory=str(out_dir),
        output_filename=out_nc.name,
    )

    since = time.time()
    copernicusmarine.subset(**subset_kwargs)

    if out_nc.exists():
        print(f"[OK] saved netcdf: {out_nc}")
        return

    newest = _newest_nc(out_dir, since_ts=since - 5)
    if newest and newest.exists():
        newest.rename(out_nc)
        print(f"[OK] saved netcdf (renamed): {out_nc}")
        return

    raise SystemExit(f"[ERR] Subset selesai tapi file NetCDF tidak ditemukan: {out_nc}")


if __name__ == "__main__":
    main()
