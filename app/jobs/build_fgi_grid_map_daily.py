from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone, date, timedelta
import argparse

import numpy as np
import xarray as xr

# Reuse model/scaler yang sudah kamu load di router fgi
from app.routers import fgi as fgi_router

ROOT = Path(__file__).resolve().parents[2]
RAW_BASE = ROOT / "data" / "raw" / "aceh_simeulue"
OUT_DIR = ROOT / "data" / "fgi_map_grid"

KINDS = {
    "sst": "sst_nrt",
    "sal": "sal_anfc",
    "chl": "chl_nrt",
}

def utc_today() -> date:
    return datetime.now(timezone.utc).date()

def ymd(d: date) -> str:
    return d.isoformat()

def _default_out_path(kind: str, d: date) -> Path:
    y = f"{d.year:04d}"
    m = f"{d.month:02d}"
    day = ymd(d)
    if kind in ("sst_nrt", "chl_nrt", "wind_nrt"):
        return RAW_BASE / kind / y / m / f"{kind}_aceh_{day}.nc"
    if kind == "wave_anfc":
        return RAW_BASE / kind / y / m / f"wave_aceh_{day}.nc"
    if kind == "ssh_anfc":
        return RAW_BASE / kind / y / m / f"ssh_aceh_{day}.nc"
    if kind == "sal_anfc":
        return RAW_BASE / kind / y / m / f"sal_aceh_{day}.nc"
    return RAW_BASE / kind / y / m / f"{kind}_aceh_{day}.nc"

def find_latest_local(kind: str, base_day: date, max_back: int = 10, min_bytes: int = 10_000) -> Path:
    for i in range(max_back + 1):
        d = base_day - timedelta(days=i)
        p = _default_out_path(kind, d)
        if p.exists() and p.is_file() and p.stat().st_size >= min_bytes:
            return p
    raise FileNotFoundError(f"No local file found for kind={kind} within {max_back} days before {base_day}")

def pick_coord_names(ds: xr.Dataset) -> tuple[str, str]:
    for lat in ("latitude", "lat", "y"):
        if lat in ds.coords or lat in ds.dims:
            lat_name = lat
            break
    else:
        raise KeyError("lat coordinate not found")
    for lon in ("longitude", "lon", "x"):
        if lon in ds.coords or lon in ds.dims:
            lon_name = lon
            break
    else:
        raise KeyError("lon coordinate not found")
    return lat_name, lon_name

def pick_var(ds: xr.Dataset, cands: list[str]) -> str:
    for v in cands:
        if v in ds.data_vars:
            return v
    # fallback: ambil first var
    if len(ds.data_vars) == 1:
        return list(ds.data_vars.keys())[0]
    raise KeyError(f"Cannot find variable in {list(ds.data_vars.keys())}, tried {cands}")

def take_surface_time(da: xr.DataArray) -> xr.DataArray:
    if "time" in da.dims:
        da = da.isel(time=0)
    # depth sudah disubset di downloader; kalau masih ada, ambil paling atas
    for dnm in ("depth", "depthu", "depthv"):
        if dnm in da.dims:
            da = da.isel({dnm: 0})
    return da

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD (default: today UTC)")
    ap.add_argument("--max-back", type=int, default=10)
    ap.add_argument("--stride", type=int, default=4, help="downsample grid (bigger=lighter)")
    args = ap.parse_args()

    d0 = utc_today()
    if args.date:
        d0 = datetime.strptime(args.date, "%Y-%m-%d").date()

    # pilih file lokal terbaru (fallback mundur)
    sst_path = find_latest_local(KINDS["sst"], d0, args.max_back)
    sal_path = find_latest_local(KINDS["sal"], d0, args.max_back)
    chl_path = find_latest_local(KINDS["chl"], d0, args.max_back)

    # buka dataset
    ds_sst = xr.open_dataset(sst_path)
    ds_sal = xr.open_dataset(sal_path)
    ds_chl = xr.open_dataset(chl_path)

    latn, lonn = pick_coord_names(ds_sst)

    v_sst = pick_var(ds_sst, ["thetao", "sst", "analysed_sst"])
    v_sal = pick_var(ds_sal, ["so", "salinity", "sal"])
    v_chl = pick_var(ds_chl, ["CHL", "chl", "chlor_a", "chlorophyll"])

    da_sst = take_surface_time(ds_sst[v_sst])
    da_sal = take_surface_time(ds_sal[v_sal])
    da_chl = take_surface_time(ds_chl[v_chl])

    # downsample base grid agar ringan
    stride = max(1, int(args.stride))
    da_sst = da_sst.isel({latn: slice(None, None, stride), lonn: slice(None, None, stride)})

    # interp sal & chl ke grid sst
    # pastikan punya coord lat/lon yang sama namanya
    lat_s = da_sst[latn]
    lon_s = da_sst[lonn]

    # samakan nama coord kalau beda (lat/lon)
    def norm_latlon(da: xr.DataArray) -> xr.DataArray:
        lat2, lon2 = pick_coord_names(da.to_dataset(name="tmp"))
        if lat2 != latn:
            da = da.rename({lat2: latn})
        if lon2 != lonn:
            da = da.rename({lon2: lonn})
        return da

    da_sal = norm_latlon(da_sal).interp({latn: lat_s, lonn: lon_s}, method="linear")
    da_chl = norm_latlon(da_chl).interp({latn: lat_s, lonn: lon_s}, method="linear")

    sst = da_sst.values.astype(np.float32)
    sal = da_sal.values.astype(np.float32)
    chl = da_chl.values.astype(np.float32)

    # flatten + mask
    sst_f = sst.ravel()
    sal_f = sal.ravel()
    chl_f = chl.ravel()

    ok = np.isfinite(sst_f) & np.isfinite(sal_f) & np.isfinite(chl_f)
    X = np.stack([sst_f[ok], sal_f[ok], chl_f[ok]], axis=1)

    # score batch via model internal
    if (not fgi_router.TORCH_AVAILABLE) or (fgi_router.MODEL is None) or (fgi_router.SCALER is None):
        raise RuntimeError("FGI model/scaler not ready (MODEL/SCALER missing)")

    Xs = fgi_router.SCALER.transform(X)
    Xt = fgi_router.torch.tensor(Xs, dtype=fgi_router.torch.float32)  # type: ignore
    with fgi_router.torch.no_grad():  # type: ignore
        raw = fgi_router.MODEL(Xt).squeeze(1).cpu().numpy().astype(np.float32)  # type: ignore

    p = raw.copy()
    m = (p < 0.0) | (p > 1.0)
    p[m] = 1.0 / (1.0 + np.exp(-p[m]))
    p = np.clip(p, 0.0, 1.0)

    # reconstruct full grid with NaN
    score_full = np.full(sst_f.shape, np.nan, dtype=np.float32)
    score_full[ok] = p
    score_grid = score_full.reshape(sst.shape)

    lats = da_sst[latn].values
    lons = da_sst[lonn].values

    # build GeoJSON points
    feats = []
    # iterate grid indices (still light because already stride)
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            sc = float(score_grid[i, j])
            if not np.isfinite(sc):
                continue
            band = "High" if sc >= 0.75 else ("Medium" if sc >= 0.50 else "Low")
            feats.append({
                "type": "Feature",
                "properties": {
                    "date_utc": sst_path.stem[-10:],  # ambil YYYY-MM-DD dari nama file
                    "score": round(sc, 6),
                    "band": band,
                    "sst_c": float(sst[i, j]),
                    "sal_psu": float(sal[i, j]),
                    "chl_mg_m3": float(chl[i, j]),
                },
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    date_tag = sst_path.stem[-10:]
    out1 = OUT_DIR / f"fgi_grid_{date_tag}.geojson"
    out2 = OUT_DIR / "latest.geojson"

    fc = {
        "type": "FeatureCollection",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": {
            "mode": "grid_points_v1",
            "stride": stride,
            "inputs": {
                "sst": str(sst_path),
                "sal": str(sal_path),
                "chl": str(chl_path),
            },
            "count": len(feats),
        },
        "features": feats,
    }

    out1.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    out2.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] wrote {out1}")
    print(f"[OK] wrote {out2}")

if __name__ == "__main__":
    main()
