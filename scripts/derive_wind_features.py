#!/usr/bin/env python
import argparse, os, numpy as np, xarray as xr

p = argparse.ArgumentParser()
p.add_argument("--src", required=True)
p.add_argument("--out", required=True)
a = p.parse_args()

ds  = xr.open_dataset(a.src)
lat_name = [d for d in ds.dims if 'lat' in d.lower()][0]
lon_name = [d for d in ds.dims if 'lon' in d.lower()][0]

def pick(cands):
    for k in ds.data_vars:
        lk = k.lower()
        if any(all(tok in lk for tok in c) for c in cands):
            return k
    return None

uvar = pick([('ugrd','10'),('u10',''),('u','10m')])
vvar = pick([('vgrd','10'),('v10',''),('v','10m')])
assert uvar and vvar, "Tidak menemukan u10/v10"
ds  = ds.sortby(lon_name).sortby(lat_name)

u10 = ds[uvar].rename('u10').astype('f4')
v10 = ds[vvar].rename('v10').astype('f4')
lat = ds[lat_name]; lon = ds[lon_name]

U = xr.apply_ufunc(np.hypot, u10, v10).rename("wind_speed")
rho_air, Cd = 1.225, 1.3e-3
tau_x = (rho_air*Cd) * U * u10
tau_y = (rho_air*Cd) * U * v10
tau_x = tau_x.rename("tau_x"); tau_y = tau_y.rename("tau_y")

R=6371000.0; rad=np.pi/180.0
cosphi = xr.apply_ufunc(np.cos, lat*rad)
d_taux_dy = tau_x.differentiate(lat_name) / (R*rad)
d_tauy_dx = tau_y.differentiate(lon_name) / (R*rad*cosphi)
curl_tau = (d_tauy_dx - d_taux_dy).rename("curl_tau")

rho_w=1025.0; Omega=7.2921159e-5
f = 2.0*Omega*xr.apply_ufunc(np.sin, lat*rad)
w_E = (curl_tau/(rho_w*f.where(np.abs(f)>1e-5))).rename("w_E")

out_dir=os.path.dirname(a.out); os.makedirs(out_dir, exist_ok=True)
(u10.to_dataset().merge(v10).merge(U).merge(tau_x).merge(tau_y).merge(curl_tau).merge(w_E)).to_netcdf(a.out)
print("Saved →", a.out)
