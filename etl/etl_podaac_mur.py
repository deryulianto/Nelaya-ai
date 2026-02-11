#!/usr/bin/env python3
"""
PO.DAAC MUR L4 SST -> Parquet
Requires: `pip install xarray netCDF4 pandas pyarrow`
Also install podaac-data-downloader (pip) & set ~/.netrc for Earthdata.
"""
import subprocess, sys
from datetime import datetime, timedelta
from pathlib import Path
import xarray as xr
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT/"data"/"podaac"/"raw"; RAW.mkdir(parents=True, exist_ok=True)
TBL = ROOT/"data"/"podaac"/"parquet"; TBL.mkdir(parents=True, exist_ok=True)

def download_mur(day: datetime):
    out = RAW/f"mur_{day:%Y%m%d}.nc"
    if out.exists(): return out
    cmd = [
        "podaac-data-downloader","-c","MUR-JPL-L4-GLOB-v4.1",
        "-d", f"{day:%Y-%m-%d}T00:00:00Z,{day:%Y-%m-%d}T23:59:59Z",
        "-b","90,-15,150,15","-o", str(RAW)
    ]
    subprocess.check_call(cmd)
    latest = max(RAW.glob("*.nc"), key=lambda p: p.stat().st_mtime)
    latest.replace(out)
    return out

def nc_to_parquet(nc: Path):
    ds = xr.open_dataset(nc)
    sst_name = next((v for v in ["analysed_sst","sst"] if v in ds.variables), None)
    if sst_name is None: sys.exit("SST variable not found")
    ds = ds.rename({sst_name:"sst"})
    # time is scalar
    t = pd.to_datetime(ds.time.values).tz_localize(None) if "time" in ds.variables else pd.Timestamp(nc.stem[-8:])
    df = ds[["sst"]].to_dataframe().reset_index().rename(columns={"lat":"lat","lon":"lon"})
    df["time"] = t
    df = df.dropna()
    out = TBL/f"mur_{t:%Y%m%d}.parquet"
    df.to_parquet(out, index=False)
    print("✅ saved:", out)

if __name__ == "__main__":
    day = datetime.utcnow() - timedelta(days=1)
    nc = download_mur(day)
    nc_to_parquet(nc)
