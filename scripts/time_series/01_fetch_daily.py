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
    """Ambil vars[var] dari YAML mentah (tanpa tergantung schema/dataclass)."""
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return dict((raw.get("vars") or {}).get(var) or {})


def _surface_depth_for_dataset(dataset_id: str) -> float:
    """
    Workaround: beberapa dataset global physics tidak punya depth=0,
    tapi depth minimum ~0.494 m. Kita set default aman ini.
    """
    return 0.49402499198913574


def _pick_dataset_id(var: str, spec, day: datetime, raw_var: dict) -> str:
    """
    Pilih dataset_id secara deterministik untuk SEMUA metric:
    - Jika ada dataset_id_my / dataset_id_nrt:
        - tanggal <= today-60 → MY
        - tanggal > today-60  → NRT (kalau ada) else MY
    - Jika tidak ada my/nrt → pakai dataset_id biasa
    """
    did_my = raw_var.get("dataset_id_my") or getattr(spec, "dataset_id_my", None)
    did_nrt = raw_var.get("dataset_id_nrt") or getattr(spec, "dataset_id_nrt", None)

    if did_my or did_nrt:
        cutoff = (datetime.utcnow() - timedelta(days=60)).date()
        if day.date() <= cutoff:
            if not did_my:
                raise SystemExit(f"dataset_id_my untuk {var} belum diset.")
            return str(did_my)

        # terbaru → prefer NRT kalau ada
        if did_nrt:
            return str(did_nrt)
        if did_my:
            return str(did_my)
        raise SystemExit(f"Tidak ada dataset {var} yang valid (my/nrt kosong).")

    # fallback lama: dataset_id tunggal
    did = raw_var.get("dataset_id") or getattr(spec, "dataset_id", None)
    if not did or "FILL_ME" in str(did):
        raise SystemExit(f"dataset_id untuk '{var}' belum diisi di config.")
    return str(did)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/time_series_aceh.yaml")
    ap.add_argument("--var", required=True, choices=["sst", "chlorophyll", "current"])
    ap.add_argument("--date", help="YYYY-MM-DD (default: today - lag_days)")
    ap.add_argument("--lag-days", type=int, default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    lag = cfg.default_lag_days if args.lag_days is None else int(args.lag_days)

    day = _parse_date(args.date) if args.date else (datetime.utcnow() - timedelta(days=lag))
    day_str = day.strftime("%Y-%m-%d")

    spec = cfg.vars[args.var]
    raw_var = _get_var_cfg_raw(args.config, args.var)
    dataset_id = _pick_dataset_id(args.var, spec, day, raw_var)

    dirs = ensure_dirs(cfg, args.var)

    out_nc = dirs["raw"] / f"{args.var}_raw_{day_str}.nc"
    out_name = out_nc.name

    # default: produk harian sering timestamp 00:00
    time_min = f"{day_str}T00:00:00"
    time_max = f"{day_str}T00:00:00"

    # kalau dataset hourly surface (PT1H) → ambil full day
    if dataset_id.endswith("PT1H-m"):
        time_min = f"{day_str}T00:00:00"
        time_max = f"{day_str}T23:00:00"

    bbox = cfg.bbox

    # variables
    if args.var == "current":
        if not spec.var_u or not spec.var_v:
            raise SystemExit("Config current harus punya var_u dan var_v (mis: uo, vo).")
        variables = [spec.var_u, spec.var_v]
    else:
        if not spec.var_name:
            raise SystemExit(f"Config '{args.var}' harus punya var_name (mis: thetao / CHL).")
        variables = [spec.var_name]

    subset_kwargs = dict(
        dataset_id=dataset_id,
        variables=variables,
        minimum_longitude=bbox.min_lon,
        maximum_longitude=bbox.max_lon,
        minimum_latitude=bbox.min_lat,
        maximum_latitude=bbox.max_lat,
        start_datetime=time_min,
        end_datetime=time_max,
        output_directory=str(dirs["raw"]),
        output_filename=out_name,
    )

    # ✅ IMPORTANT: untuk dataset physics 3D (sst/current) kunci depth "surface"
    # Banyak produk GLO PHY tidak punya depth=0.0 → minimalnya ~0.494 m
    if args.var in ("sst", "current"):
        d0 = _surface_depth_for_dataset(dataset_id)
        subset_kwargs.update(
            minimum_depth=float(d0),
            maximum_depth=float(d0),
        )

    since = time.time()

    # Eksekusi subset
    copernicusmarine.subset(**subset_kwargs)

    if out_nc.exists():
        print(f"[OK] saved netcdf: {out_nc}")
        return

    newest = _newest_nc(dirs["raw"], since_ts=since - 5)
    if newest and newest.exists():
        newest.rename(out_nc)
        print(f"[OK] saved netcdf (renamed): {out_nc}")
        return

    print("[ERR] Subset selesai tapi file NetCDF tidak ditemukan.")
    print("[INFO] raw dir:", dirs["raw"])
    for p in sorted(dirs["raw"].glob("*"))[-20:]:
        print(" -", p.name)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
