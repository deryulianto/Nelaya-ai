#!/usr/bin/env python3
"""
CMEMS subset -> NetCDF -> Parquet (harian)
Requires: `pip install copernicusmarine xarray pandas pyarrow`
Login once: `copernicusmarine login`
"""
import os, subprocess, sys, shutil
from datetime import datetime, timedelta
from pathlib import Path
import xarray as xr
import pandas as pd

# Parameter: area Indonesia (90E–150E, 15S–15N)
BBOX = "90,-15,150,15"
# Ganti dengan dataset-id yang kamu pilih (contoh multi-year global PHY/BGC)
DATASET_ID = os.getenv("CMEMS_DATASET_ID", "<ISI_DATASET_ID>")  # TODO

ROOT = Path(__file__).resolve().parents[1]
OUT_RAW = ROOT/"data"/"cmems"/"raw"
OUT_TBL = ROOT/"data"/"cmems"/"parquet"
OUT_RAW.mkdir(parents=True, exist_ok=True); OUT_TBL.mkdir(parents=True, exist_ok=True)

def subset_cmems(day: datetime):
    out_nc = OUT_RAW / f"cmems_{day:%Y%m%d}.nc"
    if out_nc.exists(): return out_nc
    cmd = [
        "copernicusmarine","subset",
        "--dataset-id", DATASET_ID,
        "--variables","thetao","so","uo","vo","chl",
        "--bbox", BBOX,
        "--date-min", day.strftime("%Y-%m-%d"),
        "--date-max", day.strftime("%Y-%m-%d"),
        "--output-directory", str(OUT_RAW),
        "--format","netcdf","--force-download"
    ]
    subprocess.check_call(cmd)
    # File nama default; cari *.nc terbaru dan rename
    latest = max(OUT_RAW.glob("*.nc"), key=lambda p: p.stat().st_mtime)
    latest.replace(out_nc)
    return out_nc

def nc_to_parquet(nc: Path):
    ds = xr.open_dataset(nc)
    # pilih permukaan (level 0) bila ada dimensi depth/lev
    if "depth" in ds.dims: ds = ds.sel(depth=ds.depth.min())
    if "time" in ds.dims:
        ds = ds.isel(time=0)
        t = pd.to_datetime(ds.time.values).tz_localize(None)
    else:
        t = pd.Timestamp(nc.stem.split("_")[-1])

    df = ds.to_dataframe().reset_index()
    keep = [c for c in ["thetao","so","uo","vo","chl","latitude","longitude"] if c in df.columns]
    df = df[keep].rename(columns={"thetao":"sst","so":"sal","latitude":"lat","longitude":"lon"})
    df["time"] = t
    df = df.dropna(how="any")
    out_parq = OUT_TBL / f"cmems_{t:%Y%m%d}.parquet"
    df.to_parquet(out_parq, index=False)
    print("✅ saved:", out_parq)

if __name__ == "__main__":
    day = datetime.utcnow() - timedelta(days=1)  # ambil data H-1
    if "<ISI_DATASET_ID>" in DATASET_ID:
        sys.exit("⚠️ Set env CMEMS_DATASET_ID dulu.")
    nc = subset_cmems(day)
    nc_to_parquet(nc)
