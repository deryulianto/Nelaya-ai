#!/usr/bin/env python3
"""
ERDDAP tabledap -> CSV/Parquet
Requires: `pip install pandas pyarrow`
"""
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import urllib.parse as url

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"data"/"erddap"; OUT.mkdir(parents=True, exist_ok=True)

# contoh server & dataset_id (ganti sesuai kebutuhan)
SERVER = "https://coastwatch.pfeg.noaa.gov/erddap"
DATASET = "cwwcNDBCMet"  # contoh NDBC met-ocean

def fetch_erddap(start, end):
    base = f"{SERVER}/tabledap/{DATASET}.csv"
    query = {
        "time>=": start.isoformat(),
        "time<=": end.isoformat(),
        "latitude>=": -15, "latitude<=": 15,
        "longitude>=": 90, "longitude<=": 150
    }
    cols = "time,latitude,longitude,waterTemperature"
    params = "&".join([f"{k}{v}" for k,v in query.items()])
    url_full = f"{base}?{cols}&{params}"
    df = pd.read_csv(url_full)
    df = df.rename(columns={"time":"time","latitude":"lat","longitude":"lon","waterTemperature":"sst_insitu"})
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time","lat","lon","sst_insitu"])
    return df

if __name__ == "__main__":
    end = datetime.utcnow()
    start = end - timedelta(days=7)
    df = fetch_erddap(start, end)
    out = OUT/f"erddap_buoy_{end:%Y%m%d}.parquet"
    df.to_parquet(out, index=False)
    print("✅ saved:", out, "| rows:", len(df))
