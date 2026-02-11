#!/usr/bin/env python
import argparse, os, glob, xarray as xr
p = argparse.ArgumentParser()
p.add_argument("--in-dir", required=True)
p.add_argument("--out", required=True)
a = p.parse_args()

hrs = sorted(glob.glob(os.path.join(a.in_dir, "hour_???.nc")))
if not hrs:
    raise SystemExit(f"No hourly nc in {a.in_dir}")
dsets = [xr.open_dataset(h) for h in hrs]
ds = xr.concat(dsets, dim="time")
os.makedirs(os.path.dirname(a.out), exist_ok=True)
ds.to_netcdf(a.out)
print("Saved day ->", a.out, "| hours:", ds.sizes.get("time", 0))
