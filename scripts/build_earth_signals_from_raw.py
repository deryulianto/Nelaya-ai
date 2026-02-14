from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, date, timedelta, timezone

import numpy as np  # type: ignore
import xarray as xr  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
RAW_BASE = ROOT / "data" / "raw" / "aceh_simeulue"

BBOX = dict(min_lon=92.0, max_lon=99.0, min_lat=1.0, max_lat=7.0)

POINTS = {
    "selat_malaka": {"lat": 5.30, "lon": 97.20},
    "samudra_hindia": {"lat": 4.60, "lon": 94.80},
}

MIN_BYTES = 10_000


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def ymd(d: date) -> str:
    return d.isoformat()


def default_out_path(kind: str, d: date) -> Path:
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


def is_ok_file(p: Path) -> bool:
    try:
        return p.exists() and p.is_file() and p.stat().st_size >= MIN_BYTES
    except Exception:
        return False


def find_latest_local(kind: str, base_day: date, max_back: int = 10) -> tuple[Path | None, str | None]:
    for i in range(max_back + 1):
        d = base_day - timedelta(days=i)
        p = default_out_path(kind, d)
        if is_ok_file(p):
            return p, ymd(d)
    # fallback: file terbaru by mtime (kalau namanya beda)
    folder = RAW_BASE / kind
    if folder.exists():
        cands = [p for p in folder.rglob("*.nc") if p.is_file() and p.stat().st_size >= MIN_BYTES]
        if cands:
            newest = sorted(cands, key=lambda x: x.stat().st_mtime)[-1]
            return newest, None
    return None, None


def guess_lat_lon_names(ds: xr.Dataset) -> tuple[str, str]:
    lat_candidates = ["latitude", "lat", "nav_lat", "y"]
    lon_candidates = ["longitude", "lon", "nav_lon", "x"]
    lat = next((n for n in lat_candidates if n in ds.coords or n in ds.variables), None)
    lon = next((n for n in lon_candidates if n in ds.coords or n in ds.variables), None)
    if not lat or not lon:
        raise ValueError(f"Cannot find lat/lon coords in dataset. coords={list(ds.coords)} vars={list(ds.data_vars)}")
    return lat, lon


def pick_time_dim(da: xr.DataArray) -> str | None:
    for n in ["time", "time_counter", "t"]:
        if n in da.dims:
            return n
    return None


def pick_depth_dim(da: xr.DataArray) -> str | None:
    for n in ["depth", "deptht", "z"]:
        if n in da.dims:
            return n
    return None


def subset_bbox(da: xr.DataArray, lat_name: str, lon_name: str) -> xr.DataArray:
    # pastikan slice sesuai arah koordinat
    lat_vals = da[lat_name].values
    lon_vals = da[lon_name].values

    lat_slice = slice(BBOX["min_lat"], BBOX["max_lat"]) if lat_vals[0] < lat_vals[-1] else slice(BBOX["max_lat"], BBOX["min_lat"])
    lon_slice = slice(BBOX["min_lon"], BBOX["max_lon"]) if lon_vals[0] < lon_vals[-1] else slice(BBOX["max_lon"], BBOX["min_lon"])

    return da.sel({lat_name: lat_slice, lon_name: lon_slice})


def scalar_mean(da: xr.DataArray) -> float | None:
    v = da.mean(skipna=True).values
    try:
        val = float(np.asarray(v))
        if np.isfinite(val):
            return val
    except Exception:
        pass
    return None


def scalar_point(da: xr.DataArray, lat_name: str, lon_name: str, lat: float, lon: float) -> float | None:
    try:
        v = da.sel({lat_name: lat, lon_name: lon}, method="nearest").values
        val = float(np.asarray(v))
        if np.isfinite(val):
            return val
    except Exception:
        return None
    return None


def pick_var(ds: xr.Dataset, candidates: list[str]) -> str | None:
    for v in candidates:
        if v in ds.data_vars:
            return v
    return None


def load_da(ds: xr.Dataset, var: str) -> xr.DataArray:
    da = ds[var]
    tdim = pick_time_dim(da)
    if tdim:
        da = da.isel({tdim: 0})
    ddim = pick_depth_dim(da)
    if ddim:
        da = da.isel({ddim: 0})
    return da


def compute_metrics(base_day: date, max_back: int = 10) -> dict:
    out: dict = {
        "ok": True,
        "region": {"name": "Aceh, Indonesia", "bbox": BBOX},
        "date_utc": ymd(base_day),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {},
        "metrics": {},
        "quick_compare": {},
    }

    def add_metric(key: str, unit: str, value: float | None, src_kind: str, src_date: str | None, src_path: Path | None):
        out["metrics"][key] = {
            "value": None if value is None else float(value),
            "unit": unit,
            "source_kind": src_kind,
            "source_date": src_date,
            "source_path": None if src_path is None else src_path.as_posix(),
        }

    # -------- SST (thetao) --------
    p, pday = find_latest_local("sst_nrt", base_day, max_back=max_back)
    out["inputs"]["sst_nrt"] = {"path": None if p is None else p.as_posix(), "day": pday}
    sst_val = None
    if p:
        ds = xr.open_dataset(p)
        lat, lon = guess_lat_lon_names(ds)
        vname = pick_var(ds, ["thetao", "sst", "analysed_sst"])
        if vname:
            da = subset_bbox(load_da(ds, vname), lat, lon)
            sst_val = scalar_mean(da)
    add_metric("sst", "°C", sst_val, "sst_nrt", pday, p)

    # -------- CHL --------
    p, pday = find_latest_local("chl_nrt", base_day, max_back=max_back)
    out["inputs"]["chl_nrt"] = {"path": None if p is None else p.as_posix(), "day": pday}
    chl_val = None
    if p:
        ds = xr.open_dataset(p)
        lat, lon = guess_lat_lon_names(ds)
        vname = pick_var(ds, ["CHL", "chl", "chlor_a", "chlorophyll"])
        if vname:
            da = subset_bbox(load_da(ds, vname), lat, lon)
            chl_val = scalar_mean(da)
    add_metric("chl", "mg/m³", chl_val, "chl_nrt", pday, p)

    # -------- SSH (zos) --------
    p, pday = find_latest_local("ssh_anfc", base_day, max_back=max_back)
    out["inputs"]["ssh_anfc"] = {"path": None if p is None else p.as_posix(), "day": pday}
    ssh_val_m = None
    if p:
        ds = xr.open_dataset(p)
        lat, lon = guess_lat_lon_names(ds)
        vname = pick_var(ds, ["zos", "ssh"])
        if vname:
            da = subset_bbox(load_da(ds, vname), lat, lon)
            ssh_val_m = scalar_mean(da)
    ssh_val_cm = None if ssh_val_m is None else ssh_val_m * 100.0
    add_metric("ssh", "cm", ssh_val_cm, "ssh_anfc", pday, p)

    # -------- SAL (so) --------
    p, pday = find_latest_local("sal_anfc", base_day, max_back=max_back)
    out["inputs"]["sal_anfc"] = {"path": None if p is None else p.as_posix(), "day": pday}
    sal_val = None
    if p:
        ds = xr.open_dataset(p)
        lat, lon = guess_lat_lon_names(ds)
        vname = pick_var(ds, ["so", "salinity", "S"])
        if vname:
            da = subset_bbox(load_da(ds, vname), lat, lon)
            sal_val = scalar_mean(da)
    add_metric("sal", "psu", sal_val, "sal_anfc", pday, p)

    # -------- WAVE (VHM0) --------
    p, pday = find_latest_local("wave_anfc", base_day, max_back=max_back)
    out["inputs"]["wave_anfc"] = {"path": None if p is None else p.as_posix(), "day": pday}
    wave_val = None
    if p:
        ds = xr.open_dataset(p)
        lat, lon = guess_lat_lon_names(ds)
        vname = pick_var(ds, ["VHM0", "hs", "swh", "wave_height"])
        if vname:
            da = subset_bbox(load_da(ds, vname), lat, lon)
            wave_val = scalar_mean(da)
    add_metric("wave", "m", wave_val, "wave_anfc", pday, p)

    # -------- WIND (u,v → speed) --------
    p, pday = find_latest_local("wind_nrt", base_day, max_back=max_back)
    out["inputs"]["wind_nrt"] = {"path": None if p is None else p.as_posix(), "day": pday}
    wind_val = None
    wind_da_for_points = None
    latlon_for_points = None

    if p:
        ds = xr.open_dataset(p)
        lat, lon = guess_lat_lon_names(ds)

        pairs = [
            ("eastward_wind", "northward_wind"),
            ("u10", "v10"),
            ("uwnd", "vwnd"),
            ("u", "v"),
        ]
        u = v = None
        for a, b in pairs:
            if a in ds.data_vars and b in ds.data_vars:
                u = load_da(ds, a)
                v = load_da(ds, b)
                break
        if u is not None and v is not None:
            speed = np.sqrt(u**2 + v**2)
            speed = subset_bbox(speed, lat, lon)
            wind_val = scalar_mean(speed)
            wind_da_for_points = speed
            latlon_for_points = (lat, lon)

    add_metric("wind", "m/s", wind_val, "wind_nrt", pday, p)

    # ---------- Quick compare points ----------
    def point_pack(lat: float, lon: float) -> dict:
        return {"lat": lat, "lon": lon}

    for key, pt in POINTS.items():
        rec = {"point": point_pack(pt["lat"], pt["lon"]), "metrics": {}}

        def sample_from(kind_key: str, var_candidates: list[str], conv=None):
            info = out["inputs"].get(kind_key) or {}
            path = info.get("path")
            if not path:
                return None
            ds = xr.open_dataset(Path(path))
            latn, lonn = guess_lat_lon_names(ds)
            vname = pick_var(ds, var_candidates)
            if not vname:
                return None
            da = load_da(ds, vname)
            val = scalar_point(da, latn, lonn, pt["lat"], pt["lon"])
            if val is None:
                return None
            return conv(val) if conv else val

        rec["metrics"]["sst_c"] = sample_from("sst_nrt", ["thetao", "sst", "analysed_sst"])
        rec["metrics"]["chl"] = sample_from("chl_nrt", ["CHL", "chl", "chlor_a", "chlorophyll"])
        rec["metrics"]["hs_m"] = sample_from("wave_anfc", ["VHM0", "hs", "swh", "wave_height"])
        rec["metrics"]["ssh_cm"] = sample_from("ssh_anfc", ["zos", "ssh"], conv=lambda x: x * 100.0)

        # wind speed kalau punya speed da yang sudah dihitung
        if wind_da_for_points is not None and latlon_for_points is not None:
            latn, lonn = latlon_for_points
            rec["metrics"]["wind_ms"] = scalar_point(wind_da_for_points, latn, lonn, pt["lat"], pt["lon"])
        else:
            rec["metrics"]["wind_ms"] = None

        out["quick_compare"][key] = rec

    # alias flat keys (biar kompatibel sama UI yang nunggu nama tertentu)
    m = out["metrics"]
    out["sst_c"] = (m.get("sst") or {}).get("value")
    out["chl_mg_m3"] = (m.get("chl") or {}).get("value")
    out["wind_ms"] = (m.get("wind") or {}).get("value")
    out["wave_m"] = (m.get("wave") or {}).get("value")
    out["ssh_cm"] = (m.get("ssh") or {}).get("value")
    out["sal_psu"] = (m.get("sal") or {}).get("value")

    # ok false kalau semua kosong
    if all(out.get(k) is None for k in ["sst_c", "chl_mg_m3", "wind_ms", "wave_m", "ssh_cm"]):
        out["ok"] = False

    return out


def main() -> int:
    base = utc_today()
    obj = compute_metrics(base_day=base, max_back=10)

    out_dir = ROOT / "data" / "earth"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "earth_signals_today.json"

    out_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote {out_path} (ok={obj.get('ok')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
