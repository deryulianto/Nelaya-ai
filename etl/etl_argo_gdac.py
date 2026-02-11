#!/usr/bin/env python3
"""
Argo GDAC -> fitur MLD & dT(0-50m)
Requires: `pip install argopy xarray pandas numpy pyarrow`
"""
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr
from argopy import DataFetcher as Argo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"data"/"argo"; OUT.mkdir(parents=True, exist_ok=True)

def compute_features(ds: xr.Dataset):
    # ambil profil permukaan & 50 m (pakai interp aman)
    pres = ds["PRES"]; temp = ds["TEMP"]; psal = ds["PSAL"]
    # filter QC dasar
    if "TEMP_QC" in ds: temp = temp.where(ds["TEMP_QC"].astype(str).isin(list("19.")))
    if "PSAL_QC" in ds: psal  = psal.where(ds["PSAL_QC"].astype(str).isin(list("19.")))
    t_surf = temp.interp(PRES=5, kwargs={"fill_value":"extrapolate"})
    t_50m  = temp.interp(PRES=50, kwargs={"fill_value":"extrapolate"})
    dT = (t_surf - t_50m).to_pandas()
    # MLD kasar: kedalaman pertama di mana ΔT > 0.5°C dari permukaan
    def mld_from_prof(pres_prof, temp_prof):
        if temp_prof.isna().all(): return np.nan
        ts = temp_prof.iloc[0]
        idx = (ts - temp_prof) > 0.5
        if not idx.any(): return np.nan
        return float(pres_prof[idx].iloc[0])
    mld = []
    for i in range(ds.dims["N_PROF"]):
        mld.append(mld_from_prof(pres.isel(N_PROF=i).to_pandas().reset_index(drop=True),
                                 temp.isel(N_PROF=i).to_pandas().reset_index(drop=True)))
    out = pd.DataFrame({
        "time": pd.to_datetime(ds["JULD"].values),
        "lat": ds["LATITUDE"].values,
        "lon": ds["LONGITUDE"].values,
        "dT_0_50": dT.values,
        "mld": mld
    })
    out = out.dropna(subset=["time","lat","lon"]).reset_index(drop=True)
    return out

if __name__ == "__main__":
    end = datetime.utcnow()
    start = end - timedelta(days=14)
    region = [ -15, 15, 90, 150 ]  # [lat_min, lat_max, lon_min, lon_max]
    ds = Argo().region(region).float(start=start, end=end).to_xarray()
    df = compute_features(ds)
    out = OUT/f"argo_feats_{end:%Y%m%d}.parquet"
    df.to_parquet(out, index=False)
    print("✅ saved:", out, "| rows:", len(df))
