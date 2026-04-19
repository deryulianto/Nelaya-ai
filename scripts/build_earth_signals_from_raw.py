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
        raise ValueError(
            f"Cannot find lat/lon in dataset. coords={list(ds.coords)} vars={list(ds.data_vars)}"
        )
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


def load_first_valid_da(ds: xr.Dataset, var: str) -> xr.DataArray:
    da = ds[var]

    tdim = pick_time_dim(da)
    if tdim:
        n = int(da.sizes.get(tdim, 0))
        for i in range(n):
            cand = da.isel({tdim: i})
            ddim = pick_depth_dim(cand)
            if ddim:
                cand = cand.isel({ddim: 0})
            try:
                vals = np.asarray(cand.values, dtype="float64")
                if np.isfinite(vals).any():
                    return cand
            except Exception:
                pass

    return load_da(ds, var)


def subset_bbox(da: xr.DataArray, latn: str, lonn: str) -> xr.DataArray:
    try:
        lat_da = da[latn]
        lon_da = da[lonn]
        if lat_da.ndim == 1 and lon_da.ndim == 1:
            lat_vals = lat_da.values
            lon_vals = lon_da.values
            lat_slice = (
                slice(BBOX["min_lat"], BBOX["max_lat"])
                if lat_vals[0] < lat_vals[-1]
                else slice(BBOX["max_lat"], BBOX["min_lat"])
            )
            lon_slice = (
                slice(BBOX["min_lon"], BBOX["max_lon"])
                if lon_vals[0] < lon_vals[-1]
                else slice(BBOX["max_lon"], BBOX["min_lon"])
            )
            return da.sel({latn: lat_slice, lonn: lon_slice})
    except Exception:
        pass
    return da


def scalar_mean(da: xr.DataArray) -> float | None:
    try:
        v = da.mean(skipna=True).values
        val = float(np.asarray(v))
        return val if np.isfinite(val) else None
    except Exception:
        return None


def scalar_point(da: xr.DataArray, latn: str, lonn: str, lat0: float, lon0: float) -> float | None:
    try:
        v = da.sel({latn: lat0, lonn: lon0}, method="nearest").values
        val = float(np.asarray(v))
        return val if np.isfinite(val) else None
    except Exception:
        return None


def _mean_finite_values(x: np.ndarray) -> float | None:
    a = np.asarray(x).astype("float64", copy=False).ravel()
    a = a[np.isfinite(a)]
    if a.size == 0:
        return None
    return float(a.mean())


def point_or_mean_multi(
    da: xr.DataArray,
    latn: str,
    lonn: str,
    lat0: float,
    lon0: float,
    box_seq: list[float],
) -> float | None:
    """
    Cari nilai representatif di sekitar titik:
    - coba nearest finite
    - kalau NaN, coba mean finite pada window box yang makin besar
    """
    x = da
    for dim in list(x.dims):
        if dim not in (latn, lonn):
            try:
                x = x.isel({dim: 0})
            except Exception:
                pass

    v0 = scalar_point(x, latn, lonn, lat0, lon0)
    if v0 is not None:
        return v0

    try:
        lat_da = x[latn]
        lon_da = x[lonn]

        if lat_da.ndim == 1 and lon_da.ndim == 1:
            lat_vals = lat_da.values
            lon_vals = lon_da.values

            for box in box_seq:
                lat_slice = (
                    slice(lat0 - box, lat0 + box)
                    if lat_vals[0] < lat_vals[-1]
                    else slice(lat0 + box, lat0 - box)
                )
                lon_slice = (
                    slice(lon0 - box, lon0 + box)
                    if lon_vals[0] < lon_vals[-1]
                    else slice(lon0 + box, lon0 - box)
                )
                win = x.sel({latn: lat_slice, lonn: lon_slice})
                mv = _mean_finite_values(win.values)
                if mv is not None:
                    return mv
            return None

        if lat_da.ndim == 2 and lon_da.ndim == 2:
            lat2 = np.asarray(lat_da.values)
            lon2 = np.asarray(lon_da.values)
            dlon = (lon2 - lon0 + 180.0) % 360.0 - 180.0
            dist2 = (lat2 - lat0) ** 2 + dlon ** 2
            idx = int(np.nanargmin(dist2))
            i, j = np.unravel_index(idx, dist2.shape)
            d0, d1 = lat_da.dims[:2]
            ny, nx = lat2.shape

            for k in [6, 10, 14, 18]:
                i0, i1 = max(0, i - k), min(ny, i + k + 1)
                j0, j1 = max(0, j - k), min(nx, j + k + 1)
                win = x.isel({d0: slice(i0, i1), d1: slice(j0, j1)})
                mv = _mean_finite_values(win.values)
                if mv is not None:
                    return mv
            return None

    except Exception:
        return None

    return None


def build_wind_speed(
    ds: xr.Dataset,
) -> tuple[float | None, xr.DataArray | None, tuple[str, str] | None]:
    lat, lon = guess_lat_lon_names(ds)

    direct_speed_vars = [
        "wind_speed",
        "windspeed",
        "si10",
        "ws",
        "windspeed_10m",
        "wind_speed_10m",
    ]

    for vname in direct_speed_vars:
        if vname in ds.data_vars:
            da = subset_bbox(load_first_valid_da(ds, vname), lat, lon).load()
            val = scalar_mean(da)
            if val is None:
                val = _mean_finite_values(da.values)
            if val is not None:
                return val, da, (lat, lon)

    pairs = [
        ("eastward_wind", "northward_wind"),
        ("u10", "v10"),
        ("uwnd", "vwnd"),
        ("u", "v"),
    ]

    for a, b in pairs:
        if a in ds.data_vars and b in ds.data_vars:
            u = load_first_valid_da(ds, a)
            v = load_first_valid_da(ds, b)
            speed = np.hypot(u, v)
            speed = subset_bbox(speed, lat, lon).load()

            val = scalar_mean(speed)
            if val is None:
                val = _mean_finite_values(speed.values)

            if val is not None:
                return val, speed, (lat, lon)

    return None, None, None


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _gaussian_score(x: float | None, center: float, sigma: float) -> float | None:
    if x is None:
        return None
    try:
        z = (float(x) - center) / float(sigma)
        return float(np.exp(-0.5 * z * z))
    except Exception:
        return None


def _chlorophyll_score(chl: float | None) -> float | None:
    """
    Skor produktivitas berbasis CHL.
    Naik cepat pada CHL rendah, lalu jenuh pada nilai sedang-tinggi.
    """
    if chl is None:
        return None
    try:
        x = float(chl)
        if x <= 0:
            return 0.0
        score = 1.0 - np.exp(-x / 0.18)
        return _clamp01(float(score))
    except Exception:
        return None


def compute_fgi_realtime(
    sst_c: float | None,
    chl_mg_m3: float | None,
    sal_psu: float | None,
) -> float | None:
    """
    FGI realtime v1:
    - SST optimum sekitar 29.0 C
    - SAL optimum sekitar 33.2 psu
    - CHL pakai saturating productivity curve
    """
    sst_score = _gaussian_score(sst_c, center=29.0, sigma=1.2)
    sal_score = _gaussian_score(sal_psu, center=33.2, sigma=0.7)
    chl_score = _chlorophyll_score(chl_mg_m3)

    comps = []
    weights = []

    if sst_score is not None:
        comps.append(sst_score)
        weights.append(0.40)

    if chl_score is not None:
        comps.append(chl_score)
        weights.append(0.35)

    if sal_score is not None:
        comps.append(sal_score)
        weights.append(0.25)

    if not comps or not weights or sum(weights) == 0:
        return None

    score = float(np.average(comps, weights=weights))
    return _clamp01(score)


def classify_fgi_band(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "medium"
    return "low"


def _inverse_risk_score(x: float | None, center: float, sigma: float) -> float | None:
    """
    Skor 1 bila dekat pusat, turun bila menjauh.
    Cocok untuk SST, CHL, SSH.
    """
    if x is None:
        return None
    try:
        z = (float(x) - center) / float(sigma)
        return _clamp01(float(np.exp(-0.5 * z * z)))
    except Exception:
        return None


def _wave_stability_score(wave_m: float | None) -> float | None:
    """
    Gelombang rendah-menengah = lebih stabil.
    Di atas ~2.5 m skor turun tajam.
    """
    if wave_m is None:
        return None
    try:
        x = float(wave_m)
        score = 1.0 / (1.0 + (x / 1.5) ** 2)
        return _clamp01(score)
    except Exception:
        return None


def compute_osi_realtime(
    sst_c: float | None,
    chl_mg_m3: float | None,
    ssh_cm: float | None,
    wave_m: float | None,
) -> float | None:
    """
    OSI realtime v1:
    - SST optimum sekitar 29.0 C
    - CHL optimum sekitar 0.25 mg/m3
    - SSH optimum sekitar 50 cm
    - Wave makin tinggi -> kestabilan turun
    """
    sst_score = _inverse_risk_score(sst_c, center=29.0, sigma=1.2)
    chl_score = _inverse_risk_score(chl_mg_m3, center=0.25, sigma=0.18)
    ssh_score = _inverse_risk_score(ssh_cm, center=50.0, sigma=8.0)
    wave_score = _wave_stability_score(wave_m)

    comps = []
    weights = []

    if sst_score is not None:
        comps.append(sst_score)
        weights.append(0.35)

    if chl_score is not None:
        comps.append(chl_score)
        weights.append(0.25)

    if ssh_score is not None:
        comps.append(ssh_score)
        weights.append(0.20)

    if wave_score is not None:
        comps.append(wave_score)
        weights.append(0.20)

    if not comps or sum(weights) == 0:
        return None

    score = float(np.average(comps, weights=weights))
    return _clamp01(score)


def classify_osi_band(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "medium"
    return "low"


def _thermal_penalty_score(sst_c: float | None) -> float | None:
    """
    Penalti termal:
    - mendekati 29 C -> penalti kecil (score tinggi)
    - makin panas / makin jauh -> score turun
    """
    if sst_c is None:
        return None
    try:
        return _clamp01(float(np.exp(-0.5 * ((float(sst_c) - 29.0) / 1.4) ** 2)))
    except Exception:
        return None


def compute_msi_realtime(
    fgi: float | None,
    osi: float | None,
    wave_m: float | None,
    sst_c: float | None,
) -> float | None:
    """
    MSI realtime v1:
    - berbasis peluang pemanfaatan (FGI)
    - kestabilan/kesehatan laut (OSI)
    - moderasi operasional gelombang
    - penalti stress termal
    """
    wave_score = _wave_stability_score(wave_m)
    thermal_score = _thermal_penalty_score(sst_c)

    comps = []
    weights = []

    if osi is not None:
        comps.append(float(osi))
        weights.append(0.45)

    if fgi is not None:
        comps.append(float(fgi))
        weights.append(0.30)

    if wave_score is not None:
        comps.append(float(wave_score))
        weights.append(0.25)

    if not comps or sum(weights) == 0:
        return None

    base_score = float(np.average(comps, weights=weights))

    if thermal_score is None:
        final_score = base_score
    else:
        final_score = base_score * (0.70 + 0.30 * thermal_score)

    return _clamp01(final_score)


def classify_msi_band(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "medium"
    return "low"


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

    def add_metric(
        key: str,
        unit: str,
        value: float | None,
        src_kind: str,
        src_date: str | None,
        src_path: Path | None,
    ):
        out["metrics"][key] = {
            "value": None if value is None else float(value),
            "unit": unit,
            "source_kind": src_kind,
            "source_date": src_date,
            "source_path": None if src_path is None else src_path.as_posix(),
        }

    # -------- SST --------
    p, pday = find_latest_local("sst_nrt", base_day, max_back=max_back)
    out["inputs"]["sst_nrt"] = {"path": None if p is None else p.as_posix(), "day": pday}
    sst_val = None
    if p:
        ds = xr.open_dataset(p)
        try:
            lat, lon = guess_lat_lon_names(ds)
            vname = pick_var(ds, ["thetao", "sst", "analysed_sst"])
            if vname:
                da = subset_bbox(load_da(ds, vname), lat, lon)
                sst_val = scalar_mean(da)
        finally:
            ds.close()
    add_metric("sst", "°C", sst_val, "sst_nrt", pday, p)

    # -------- CHL --------
    p, pday = find_latest_local("chl_nrt", base_day, max_back=max_back)
    out["inputs"]["chl_nrt"] = {"path": None if p is None else p.as_posix(), "day": pday}
    chl_val = None
    if p:
        ds = xr.open_dataset(p)
        try:
            lat, lon = guess_lat_lon_names(ds)
            vname = pick_var(ds, ["CHL", "chl", "chlor_a", "chlorophyll"])
            if vname:
                da = subset_bbox(load_da(ds, vname), lat, lon)
                chl_val = scalar_mean(da)
        finally:
            ds.close()
    add_metric("chl", "mg/m³", chl_val, "chl_nrt", pday, p)

    # -------- SSH --------
    p, pday = find_latest_local("ssh_anfc", base_day, max_back=max_back)
    out["inputs"]["ssh_anfc"] = {"path": None if p is None else p.as_posix(), "day": pday}
    ssh_val_m = None
    if p:
        ds = xr.open_dataset(p)
        try:
            lat, lon = guess_lat_lon_names(ds)
            vname = pick_var(ds, ["zos", "ssh"])
            if vname:
                da = subset_bbox(load_da(ds, vname), lat, lon)
                ssh_val_m = scalar_mean(da)
        finally:
            ds.close()
    ssh_val_cm = None if ssh_val_m is None else ssh_val_m * 100.0
    add_metric("ssh", "cm", ssh_val_cm, "ssh_anfc", pday, p)

    # -------- SAL --------
    p, pday = find_latest_local("sal_anfc", base_day, max_back=max_back)
    out["inputs"]["sal_anfc"] = {"path": None if p is None else p.as_posix(), "day": pday}
    sal_val = None
    if p:
        ds = xr.open_dataset(p)
        try:
            lat, lon = guess_lat_lon_names(ds)
            vname = pick_var(ds, ["so", "salinity", "S"])
            if vname:
                da = subset_bbox(load_da(ds, vname), lat, lon)
                sal_val = scalar_mean(da)
        finally:
            ds.close()
    add_metric("sal", "psu", sal_val, "sal_anfc", pday, p)

    # -------- WAVE (Hs) --------
    p, pday = find_latest_local("wave_anfc", base_day, max_back=max_back)
    out["inputs"]["wave_anfc"] = {"path": None if p is None else p.as_posix(), "day": pday}
    wave_val = None
    if p:
        ds = xr.open_dataset(p)
        try:
            lat, lon = guess_lat_lon_names(ds)
            vname = pick_var(ds, ["VHM0", "hs", "swh", "wave_height"])
            if vname:
                da = subset_bbox(load_da(ds, vname), lat, lon)
                wave_val = scalar_mean(da)
        finally:
            ds.close()
    add_metric("wave", "m", wave_val, "wave_anfc", pday, p)

    # -------- WIND --------
    wind_val = None
    wind_da_for_points: xr.DataArray | None = None
    wind_latlon: tuple[str, str] | None = None
    p = None
    pday = None

    for i in range(max_back + 1):
        cand_day = base_day - timedelta(days=i)
        cand_p = default_out_path("wind_nrt", cand_day)

        if not is_ok_file(cand_p):
            continue

        ds = xr.open_dataset(cand_p)
        try:
            cand_val, cand_da, cand_latlon = build_wind_speed(ds)
        finally:
            ds.close()

        if cand_val is not None:
            p = cand_p
            pday = ymd(cand_day)
            wind_val = cand_val
            wind_da_for_points = cand_da
            wind_latlon = cand_latlon
            break

    out["inputs"]["wind_nrt"] = {"path": None if p is None else p.as_posix(), "day": pday}
    add_metric("wind", "m/s", wind_val, "wind_nrt", pday, p)

    # ---------- Quick compare points ----------
    def sample_from_file(
        kind_key: str,
        var_candidates: list[str],
        lat0: float,
        lon0: float,
        *,
        conv=None,
        box_seq: list[float],
    ) -> float | None:
        info = out["inputs"].get(kind_key) or {}
        path = info.get("path")
        if not path:
            return None
        ds = xr.open_dataset(Path(path))
        try:
            latn, lonn = guess_lat_lon_names(ds)
            vname = pick_var(ds, var_candidates)
            if not vname:
                return None
            da = load_da(ds, vname)
            da = da.load()
            val = point_or_mean_multi(da, latn, lonn, lat0, lon0, box_seq=box_seq)
            if val is None:
                return None
            return conv(val) if conv else val
        finally:
            ds.close()

    for key, pt in POINTS.items():
        lat0 = float(pt["lat"])
        lon0 = float(pt["lon"])

        rec = {"point": {"lat": lat0, "lon": lon0}, "metrics": {}}

        rec["metrics"]["sst_c"] = sample_from_file(
            "sst_nrt",
            ["thetao", "sst", "analysed_sst"],
            lat0,
            lon0,
            box_seq=[0.12, 0.20, 0.35],
        )

        rec["metrics"]["chl"] = sample_from_file(
            "chl_nrt",
            ["CHL", "chl", "chlor_a", "chlorophyll"],
            lat0,
            lon0,
            box_seq=[0.20, 0.35, 0.50, 0.80, 1.20, 1.80],
        )

        rec["metrics"]["hs_m"] = sample_from_file(
            "wave_anfc",
            ["VHM0", "hs", "swh", "wave_height"],
            lat0,
            lon0,
            box_seq=[0.12, 0.20, 0.35, 0.50],
        )

        rec["metrics"]["ssh_cm"] = sample_from_file(
            "ssh_anfc",
            ["zos", "ssh"],
            lat0,
            lon0,
            conv=lambda x: x * 100.0,
            box_seq=[0.12, 0.20, 0.35, 0.50],
        )

        if wind_da_for_points is not None and wind_latlon is not None:
            latn, lonn = wind_latlon
            rec["metrics"]["wind_ms"] = point_or_mean_multi(
                wind_da_for_points,
                latn,
                lonn,
                lat0,
                lon0,
                box_seq=[0.20, 0.35, 0.50, 0.80, 1.20, 1.80, 2.50],
            )
        else:
            rec["metrics"]["wind_ms"] = None

        out["quick_compare"][key] = rec

    # alias flat keys
    m = out["metrics"]
    out["sst_c"] = (m.get("sst") or {}).get("value")
    out["chl_mg_m3"] = (m.get("chl") or {}).get("value")
    out["wind_ms"] = (m.get("wind") or {}).get("value")
    out["wave_m"] = (m.get("wave") or {}).get("value")
    out["ssh_cm"] = (m.get("ssh") or {}).get("value")
    out["sal_psu"] = (m.get("sal") or {}).get("value")

    # -------- FGI realtime --------
    fgi_val = compute_fgi_realtime(
        sst_c=out.get("sst_c"),
        chl_mg_m3=out.get("chl_mg_m3"),
        sal_psu=out.get("sal_psu"),
    )
    fgi_band = classify_fgi_band(fgi_val)

    out["metrics"]["fgi"] = {
        "value": None if fgi_val is None else float(fgi_val),
        "unit": "index",
        "source_kind": "fgi_realtime_v1",
        "source_date": out.get("date_utc"),
        "source_path": None,
        "band": fgi_band,
        "note": "FGI realtime v1 from current SST, CHL, SAL",
        "inputs": {
            "sst_c": out.get("sst_c"),
            "chl_mg_m3": out.get("chl_mg_m3"),
            "sal_psu": out.get("sal_psu"),
        },
    }

    # -------- OSI realtime --------
    osi_val = compute_osi_realtime(
        sst_c=out.get("sst_c"),
        chl_mg_m3=out.get("chl_mg_m3"),
        ssh_cm=out.get("ssh_cm"),
        wave_m=out.get("wave_m"),
    )
    osi_band = classify_osi_band(osi_val)

    out["metrics"]["osi"] = {
        "value": None if osi_val is None else float(osi_val),
        "unit": "index",
        "source_kind": "osi_realtime_v1",
        "source_date": out.get("date_utc"),
        "source_path": None,
        "band": osi_band,
        "note": "OSI realtime v1 from current SST, CHL, SSH, wave",
        "inputs": {
            "sst_c": out.get("sst_c"),
            "chl_mg_m3": out.get("chl_mg_m3"),
            "ssh_cm": out.get("ssh_cm"),
            "wave_m": out.get("wave_m"),
        },
    }

    # -------- MSI realtime --------
    msi_val = compute_msi_realtime(
        fgi=fgi_val,
        osi=osi_val,
        wave_m=out.get("wave_m"),
        sst_c=out.get("sst_c"),
    )
    msi_band = classify_msi_band(msi_val)

    out["metrics"]["msi"] = {
        "value": None if msi_val is None else float(msi_val),
        "unit": "index",
        "source_kind": "msi_realtime_v1",
        "source_date": out.get("date_utc"),
        "source_path": None,
        "band": msi_band,
        "note": "MSI realtime v1 from FGI, OSI, wave, and thermal penalty",
        "inputs": {
            "fgi": fgi_val,
            "osi": osi_val,
            "wave_m": out.get("wave_m"),
            "sst_c": out.get("sst_c"),
        },
    }

    if all(out.get(k) is None for k in ["sst_c", "chl_mg_m3", "wind_ms", "wave_m", "ssh_cm"]):
        out["ok"] = False

    return out


def main() -> int:
    base = utc_today()
    obj = compute_metrics(base_day=base, max_back=10)

    out_dir = ROOT / "data" / "earth"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "earth_signals_today.json"
    yesterday_path = out_dir / "earth_signals_yesterday.json"

    # simpan file lama sebagai versi kemarin hanya jika tanggalnya berbeda
    if out_path.exists():
        try:
            old_obj = json.loads(out_path.read_text(encoding="utf-8"))
            old_date = old_obj.get("date_utc")
            new_date = obj.get("date_utc")

            if old_date and new_date and str(old_date) != str(new_date):
                yesterday_path.write_text(
                    json.dumps(old_obj, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass

    out_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote {out_path} (ok={obj.get('ok')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())