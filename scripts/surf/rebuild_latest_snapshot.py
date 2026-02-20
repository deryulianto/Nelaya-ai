from __future__ import annotations
import json, re, math, glob
from pathlib import Path
from datetime import datetime, timezone

import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "aceh_simeulue" / "wave_anfc"
DER = ROOT / "data" / "derived" / "surf_snapshot"
SPOTS = ROOT / "data" / "surf_spots_today.json"
if not SPOTS.exists():
    SPOTS = ROOT / "data" / "surf_spots.json"

PAT = re.compile(r"wave_aceh_(\d{4}-\d{2}-\d{2})\.nc$")
HS_CAND = ["VHM0", "swh", "hs"]
TP_CAND = ["VTPK", "VTP", "tp"]
DIR_CAND = ["VMDR", "mwd", "dir"]
LAT_CAND = ["latitude", "lat"]
LON_CAND = ["longitude", "lon"]

def iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def hav_km(lat1, lon1, lat2, lon2):
    R=6371.0
    p1=math.radians(lat1); p2=math.radians(lat2)
    dphi=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

def pick(name_list, keys):
    for k in keys:
        if k in name_list:
            return k
    return None

def load_spots():
    d = json.load(open(SPOTS))
    if isinstance(d, dict) and "spots" in d:
        d = d["spots"]
    if isinstance(d, dict):
        out=[]
        for k,v in d.items():
            if isinstance(v, dict):
                vv=dict(v); vv.setdefault("id", k)
                out.append(vv)
        return out
    if isinstance(d, list):
        return d
    raise RuntimeError("Bad spots format")

def newest_nc():
    files=[]
    for p in RAW.rglob("wave_aceh_*.nc"):
        m = PAT.search(p.name)
        if m:
            files.append((m.group(1), p))
    if not files:
        raise RuntimeError("No wave_aceh_*.nc")
    files.sort(key=lambda x: x[0])
    return files[-1]

def atomic_write(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

def main():
    day, fn = newest_nc()
    ds = xr.open_dataset(fn)

    latn = pick(ds.coords, LAT_CAND) or pick(ds.variables, LAT_CAND)
    lonn = pick(ds.coords, LON_CAND) or pick(ds.variables, LON_CAND)
    timen = "time" if "time" in ds.coords else None

    hsn = pick(ds.data_vars, HS_CAND)
    tpn = pick(ds.data_vars, TP_CAND)
    drn = pick(ds.data_vars, DIR_CAND)

    if not (latn and lonn and hsn):
        raise RuntimeError(f"Missing lat/lon/hs. lat={latn} lon={lonn} hs={hsn} vars={list(ds.data_vars)[:30]}")

    # valid_utc: ambil time pertama jika ada
    valid_dt = datetime.now(timezone.utc)
    if timen:
        t0 = ds[timen].values
        if hasattr(t0, "shape") and t0.shape:
            t0 = t0[0]
        try:
            valid_dt = datetime.fromisoformat(str(t0).replace("Z","+00:00"))
        except Exception:
            pass

    spots = load_spots()
    out = {}

    for s in spots:
        sid = str(s.get("id") or s.get("slug") or s.get("name"))
        name = s.get("name") or sid
        lat = float(s.get("lat"))
        lon = float(s.get("lon"))

        sel = ds.sel({latn: lat, lonn: lon}, method="nearest")

        def take(varname):
            if not varname:
                return None
            v = sel[varname]
            if timen and timen in v.dims:
                v = v.isel({timen: 0})
            x = float(v.values)
            return None if math.isnan(x) else x

        hs = take(hsn)
        tp = take(tpn)
        dr = take(drn)

        latg = float(sel[latn].values)
        long = float(sel[lonn].values)
        dist = hav_km(lat, lon, latg, long)

        out[sid] = {
            "id": sid,
            "name": name,
            "lat": lat,
            "lon": lon,
            "hs_m": hs,
            "tp_s": tp,
            "dir_deg": dr,
            "grid_km": round(dist, 2),
        }

    payload = {
        "date": day,
        "valid_utc": iso_z(valid_dt),
        "generated_at": iso_z(datetime.now(timezone.utc)),
        "source": "Copernicus Marine (CMEMS)",
        "bbox": [92, 1, 99, 7],
        "file": str(fn),
        "spots": out,
        "note": "Auto-rebuilt from newest available wave_aceh_*.nc; nearshore gaps may produce null values.",
    }

    DER.mkdir(parents=True, exist_ok=True)
    atomic_write(DER / f"surf_wave_snapshot_{day}.json", payload)
    atomic_write(DER / "surf_wave_snapshot_latest.json", payload)

    print("[OK] date:", payload["date"])
    print("[OK] valid_utc:", payload["valid_utc"])
    print("[OK] generated_at:", payload["generated_at"])

if __name__ == "__main__":
    main()
