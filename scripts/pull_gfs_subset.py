#!/usr/bin/env python
import argparse, os, xarray as xr
p=argparse.ArgumentParser()
p.add_argument("--run-date",required=True); p.add_argument("--hour",default="00")
p.add_argument("--lon-min",type=float,required=True); p.add_argument("--lon-max",type=float,required=True)
p.add_argument("--lat-min",type=float,required=True); p.add_argument("--lat-max",type=float,required=True)
p.add_argument("--out",required=True)
a=p.parse_args()
url=f"https://nomads.ncep.noaa.gov/dods/gfs_0p25_1hr/gfs{a.run_date.replace('-','')}/gfs_0p25_1hr_{a.hour}z"
ds=xr.open_dataset(url)  # OPeNDAP 443
lat=[d for d in ds.dims if 'lat' in d.lower()][0]
lon=[d for d in ds.dims if 'lon' in d.lower()][0]
u=[k for k in ds.data_vars if ('ugrd' in k.lower() and '10' in k.lower()) or k.lower() in ('u10','u10m')][0]
v=[k for k in ds.data_vars if ('vgrd' in k.lower() and '10' in k.lower()) or k.lower() in ('v10','v10m')][0]
latv=ds[lat]
lat_slc = slice(a.lat_max, a.lat_min) if latv[0] > latv[-1] else slice(a.lat_min, a.lat_max)
sub=ds[[u,v]].isel(time=slice(0,24)).sel({lat:lat_slc, lon:slice(a.lon_min,a.lon_max)})
os.makedirs(os.path.dirname(a.out), exist_ok=True)
sub.to_netcdf(a.out)
print("Saved →",a.out,"| Vars:",u,v,"| Dims:",lat,lon)
