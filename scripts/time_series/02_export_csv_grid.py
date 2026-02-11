from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from ts_common import load_config, ensure_dirs


def _normalize_lat_lon_names(ds: xr.Dataset) -> xr.Dataset:
    # Copernicus bisa pakai latitude/longitude atau lat/lon
    rename = {}
    if "latitude" in ds.coords and "lat" not in ds.coords:
        rename["latitude"] = "lat"
    if "longitude" in ds.coords and "lon" not in ds.coords:
        rename["longitude"] = "lon"
    if rename:
        ds = ds.rename(rename)
    return ds


def _reduce_to_2d(da: xr.DataArray) -> xr.DataArray:
    """
    Jadikan DataArray jadi 2D (lat, lon).
    - mean over time jika ada
    - kalau ada dim lain (depth, number, step, etc), ambil index pertama
    """
    if "time" in da.dims:
        da = da.mean(dim="time", skipna=True)

    # pastikan nama lat/lon
    # (rename dilakukan di dataset, tapi jaga-jaga)
    if "latitude" in da.dims and "lat" not in da.dims:
        da = da.rename({"latitude": "lat"})
    if "longitude" in da.dims and "lon" not in da.dims:
        da = da.rename({"longitude": "lon"})

    # ambil first index untuk dim selain lat/lon
    for d in list(da.dims):
        if d not in ("lat", "lon"):
            da = da.isel({d: 0})

    # squeeze dim ukuran 1
    da = da.squeeze(drop=True)
    return da


def export_single_var(nc_path: Path, out_csv: Path, date: str, var_name: str, unit: str, source: str, region: str) -> None:
    ds = xr.open_dataset(nc_path)
    ds = _normalize_lat_lon_names(ds)

    if var_name not in ds.data_vars:
        raise SystemExit(f"Var '{var_name}' tidak ada dalam {nc_path.name}. Data vars: {list(ds.data_vars)[:30]}")

    da = _reduce_to_2d(ds[var_name])

    # to_dataframe akan menghasilkan index lat/lon
    df = da.to_dataframe(name="value").reset_index()

    # drop NaN
    df = df.dropna(subset=["value"])

    # enforce kolom standar
    df.insert(0, "date", date)
    df["unit"] = unit
    df["source"] = source
    df["region"] = region

    # urutan kolom
    df = df[["date", "lat", "lon", "value", "unit", "source", "region"]]
    df.to_csv(out_csv, index=False)


def export_current(nc_path: Path, out_csv: Path, date: str, var_u: str, var_v: str, unit: str, source: str, region: str) -> None:
    ds = xr.open_dataset(nc_path)
    ds = _normalize_lat_lon_names(ds)

    for vn in (var_u, var_v):
        if vn not in ds.data_vars:
            raise SystemExit(f"Var '{vn}' tidak ada dalam {nc_path.name}. Data vars: {list(ds.data_vars)[:30]}")

    du = _reduce_to_2d(ds[var_u])
    dv = _reduce_to_2d(ds[var_v])

    dfu = du.to_dataframe(name="value_u").reset_index()
    dfv = dv.to_dataframe(name="value_v").reset_index()

    # merge by lat/lon
    df = pd.merge(dfu, dfv, on=["lat", "lon"], how="inner")
    df = df.dropna(subset=["value_u", "value_v"])

    df["speed"] = np.sqrt(df["value_u"].astype(float) ** 2 + df["value_v"].astype(float) ** 2)

    df.insert(0, "date", date)
    df["unit"] = unit
    df["source"] = source
    df["region"] = region

    df = df[["date", "lat", "lon", "value_u", "value_v", "speed", "unit", "source", "region"]]
    df.to_csv(out_csv, index=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/time_series_aceh.yaml")
    ap.add_argument("--var", required=True, help="var key dari config (mis: sst/chlorophyll/current/temp50)")

    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    cfg = load_config(args.config)
    day_str = args.date
    spec = cfg.vars[args.var]
   
    if args.var not in cfg.vars:
       raise SystemExit(f"var '{args.var}' tidak ada di config vars.")

    dirs = ensure_dirs(cfg, args.var)

    nc_path = dirs["raw"] / f"{args.var}_raw_{day_str}.nc"
    if not nc_path.exists():
        raise SystemExit(f"Raw NetCDF belum ada: {nc_path}")

    out_csv = dirs["daily"] / f"{args.var}_daily_{day_str}.csv"

    if args.var == "current":
        export_current(
            nc_path=nc_path,
            out_csv=out_csv,
            date=day_str,
            var_u=spec.var_u or "uo",
            var_v=spec.var_v or "vo",
            unit=spec.unit,
            region=getattr(cfg, "region_label", None) or getattr(cfg, "region", "Aceh"),
            source=getattr(cfg, "source_name", "Copernicus Marine Service (CMEMS)"),
        )
    else:
        export_single_var(
            nc_path=nc_path,
            out_csv=out_csv,
            date=day_str,
            var_name=spec.var_name or "value",
            unit=spec.unit,
            region=getattr(cfg, "region_label", None) or getattr(cfg, "region", "Aceh"),
            source=getattr(cfg, "source_name", "Copernicus Marine Service (CMEMS)"),
        )

    print(f"[OK] saved grid csv: {out_csv}")


if __name__ == "__main__":
    main()
