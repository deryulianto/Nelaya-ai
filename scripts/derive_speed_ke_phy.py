#!/usr/bin/env python
import argparse, xarray as xr, numpy as np, os
p=argparse.ArgumentParser()
p.add_argument("--src", required=True)
p.add_argument("--out", required=True)
a=p.parse_args()

ds=xr.open_dataset(a.src)
# nama dimensi bisa 'latitude/longitude' atau 'lat/lon'
lat=[d for d in ds.dims if 'lat' in d.lower()][0]
lon=[d for d in ds.dims if 'lon' in d.lower()][0]
u=ds['uo']; v=ds['vo']
# jika punya dim depth, ambil permukaan (indeks 0)
if 'depth' in u.dims: u=u.isel(depth=0); v=v.isel(depth=0)

speed = (u**2 + v**2)**0.5
ke    = 0.5*(u**2 + v**2)

out = xr.Dataset(
    data_vars={
        "speed": (speed.dims, speed.data, {"units":"m s-1","long_name":"current speed"}),
        "ke":    (ke.dims,     ke.data,    {"units":"m2 s-2","long_name":"kinetic energy (0.5*u^2+v^2)"})
    },
    coords={k: ds[k] for k in [d for d in speed.dims if d in ds.coords]}
)
os.makedirs(os.path.dirname(a.out), exist_ok=True)
out.to_netcdf(a.out)
print("Saved →", a.out)
