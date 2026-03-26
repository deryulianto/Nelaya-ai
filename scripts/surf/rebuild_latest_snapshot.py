from __future__ import annotations
import json
import re
import math
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
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
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


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
        out = []
        for k, v in d.items():
            if isinstance(v, dict):
                vv = dict(v)
                vv.setdefault("id", k)
                out.append(vv)
        return out
    if isinstance(d, list):
        return d
    raise RuntimeError("Bad spots format")


def newest_nc():
    files = []
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


def _first_time_slice(da: xr.DataArray, timen: Optional[str]) -> xr.DataArray:
    out = da
    if timen and timen in out.dims:
        out = out.isel({timen: 0})
    return out.squeeze(drop=True)


def _coord_slice(coord: xr.DataArray, vmin: float, vmax: float):
    arr = np.asarray(coord.values)
    if arr.size == 0:
        return slice(vmin, vmax)
    if float(arr[0]) <= float(arr[-1]):
        return slice(vmin, vmax)
    return slice(vmax, vmin)


def _safe_float(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except Exception:
        return None


def _take_direct(
    ds: xr.Dataset,
    latn: str,
    lonn: str,
    timen: Optional[str],
    hsn: str,
    tpn: Optional[str],
    drn: Optional[str],
    lat: float,
    lon: float,
) -> Dict[str, Any]:
    sel = ds.sel({latn: lat, lonn: lon}, method="nearest")

    def take(varname: Optional[str]) -> Optional[float]:
        if not varname:
            return None
        v = sel[varname]
        if timen and timen in v.dims:
            v = v.isel({timen: 0})
        return _safe_float(v.values)

    latg = float(sel[latn].values)
    long = float(sel[lonn].values)

    return {
        "picked_lat": latg,
        "picked_lon": long,
        "hs_m": take(hsn),
        "tp_s": take(tpn),
        "dir_deg": take(drn),
        "grid_km": hav_km(lat, lon, latg, long),
        "method": "nearest_grid",
    }


def _nearest_valid_ocean_cell(
    ds: xr.Dataset,
    latn: str,
    lonn: str,
    timen: Optional[str],
    hsn: str,
    tpn: Optional[str],
    drn: Optional[str],
    lat: float,
    lon: float,
    radius_deg: float = 0.5,
) -> Optional[Dict[str, Any]]:
    hs0 = _first_time_slice(ds[hsn], timen).transpose(latn, lonn)
    tp0 = _first_time_slice(ds[tpn], timen).transpose(latn, lonn) if tpn else None
    dr0 = _first_time_slice(ds[drn], timen).transpose(latn, lonn) if drn else None

    sub_hs = hs0.sel(
        {
            latn: _coord_slice(hs0[latn], lat - radius_deg, lat + radius_deg),
            lonn: _coord_slice(hs0[lonn], lon - radius_deg, lon + radius_deg),
        }
    )

    if sub_hs.sizes.get(latn, 0) == 0 or sub_hs.sizes.get(lonn, 0) == 0:
        return None

    lats = np.asarray(sub_hs[latn].values, dtype=float)
    lons = np.asarray(sub_hs[lonn].values, dtype=float)
    hvals = np.asarray(sub_hs.values, dtype=float)

    if hvals.ndim != 2:
        return None

    if tp0 is not None:
        sub_tp = tp0.sel({latn: sub_hs[latn], lonn: sub_hs[lonn]})
        tpvals = np.asarray(sub_tp.values, dtype=float)
    else:
        tpvals = np.full_like(hvals, np.nan)

    if dr0 is not None:
        sub_dr = dr0.sel({latn: sub_hs[latn], lonn: sub_hs[lonn]})
        drvals = np.asarray(sub_dr.values, dtype=float)
    else:
        drvals = np.full_like(hvals, np.nan)

    valid_cells_hs = int(np.isfinite(hvals).sum())
    valid_cells_tp = int(np.isfinite(tpvals).sum())

    best = None
    best_score = -1
    best_dist = 1e18

    for i in range(len(lats)):
        for j in range(len(lons)):
            hs = _safe_float(hvals[i, j])
            tp = _safe_float(tpvals[i, j])
            dr = _safe_float(drvals[i, j])

            has_hs = hs is not None
            has_tp = tp is not None
            has_dr = dr is not None

            # fallback harus minimal punya hs atau tp
            if not (has_hs or has_tp):
                continue

            score = (2 if has_hs else 0) + (2 if has_tp else 0) + (1 if has_dr else 0)
            dist = hav_km(lat, lon, float(lats[i]), float(lons[j]))

            if score > best_score or (score == best_score and dist < best_dist):
                best_score = score
                best_dist = dist
                best = {
                    "picked_lat": float(lats[i]),
                    "picked_lon": float(lons[j]),
                    "hs_m": hs,
                    "tp_s": tp,
                    "dir_deg": dr,
                    "grid_km": dist,
                    "method": "nearest_valid_ocean_grid",
                    "search_radius_deg": radius_deg,
                    "valid_cells_hs": valid_cells_hs,
                    "valid_cells_tp": valid_cells_tp,
                }

    return best


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
        raise RuntimeError(
            f"Missing lat/lon/hs. lat={latn} lon={lonn} hs={hsn} vars={list(ds.data_vars)[:30]}"
        )

    valid_dt = datetime.now(timezone.utc)
    if timen:
        t0 = ds[timen].values
        if hasattr(t0, "shape") and t0.shape:
            t0 = t0[0]
        try:
            valid_dt = datetime.fromisoformat(str(t0).replace("Z", "+00:00"))
        except Exception:
            pass

    spots = load_spots()
    out = {}

    for s in spots:
        sid = str(s.get("id") or s.get("slug") or s.get("name"))
        name = s.get("name") or sid
        region = s.get("region") or "Aceh"
        lat = float(s.get("lat"))
        lon = float(s.get("lon"))
        radius_deg = float(s.get("search_radius_deg") or 0.5)

        direct = _take_direct(ds, latn, lonn, timen, hsn, tpn, drn, lat, lon)

        hs = direct["hs_m"]
        tp = direct["tp_s"]
        dr = direct["dir_deg"]
        dist = direct["grid_km"]

        extract_meta = {
            "source_cell_method": direct["method"],
            "picked_lat": round(float(direct["picked_lat"]), 6),
            "picked_lon": round(float(direct["picked_lon"]), 6),
            "search_radius_deg": radius_deg,
            "fallback_used": False,
        }

        # jika hs/tp kosong, cari nearest valid ocean cell dalam radius
        if hs is None or tp is None:
            fb = _nearest_valid_ocean_cell(
                ds, latn, lonn, timen, hsn, tpn, drn, lat, lon, radius_deg=radius_deg
            )
            if fb is not None:
                hs = fb["hs_m"]
                tp = fb["tp_s"]
                dr = fb["dir_deg"]
                dist = fb["grid_km"]

                extract_meta = {
                    "source_cell_method": fb["method"],
                    "picked_lat": round(float(fb["picked_lat"]), 6),
                    "picked_lon": round(float(fb["picked_lon"]), 6),
                    "search_radius_deg": radius_deg,
                    "fallback_used": True,
                    "valid_cells_hs": fb.get("valid_cells_hs"),
                    "valid_cells_tp": fb.get("valid_cells_tp"),
                }

        out[sid] = {
            "id": sid,
            "name": name,
            "region": region,
            "lat": lat,
            "lon": lon,
            "hs_m": hs,
            "tp_s": tp,
            "dir_deg": dr,
            "grid_km": round(float(dist), 2) if dist is not None else None,
            "extract_meta": extract_meta,
        }

    payload = {
        "date": day,
        "valid_utc": iso_z(valid_dt),
        "generated_at": iso_z(datetime.now(timezone.utc)),
        "source": "Copernicus Marine (CMEMS)",
        "bbox": [92, 1, 99, 7],
        "file": str(fn),
        "spots": out,
        "note": "Auto-rebuilt from newest available wave_aceh_*.nc; if nearest coastal cell is null for Hs/Tp, fallback searches nearest valid ocean cell within radius.",
    }

    DER.mkdir(parents=True, exist_ok=True)
    payload["date_utc"] = payload.get("date_utc") or day
    payload["valid_at"] = payload.get("valid_at") or payload.get("valid_utc") or payload.get("generated_at")
    payload["valid_utc"] = payload.get("valid_utc") or payload.get("valid_at")
    atomic_write(DER / f"surf_wave_snapshot_{day}.json", payload)
    atomic_write(DER / "surf_wave_snapshot_latest.json", payload)

    print("[OK] date:", payload["date"])
    print("[OK] valid_utc:", payload["valid_utc"])
    print("[OK] generated_at:", payload["generated_at"])
    for sid, s in out.items():
        print(
            f"[SPOT] {sid}: hs={s['hs_m']} tp={s['tp_s']} dir={s['dir_deg']} "
            f"grid_km={s['grid_km']} method={s['extract_meta']['source_cell_method']}"
        )


if __name__ == "__main__":
    main()