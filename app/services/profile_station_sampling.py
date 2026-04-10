from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import threading

import numpy as np
import xarray as xr

from app.core.ocean_stations import get_station

# -----------------------------------------------------------------------------
# NetCDF/HDF5 read safety
# -----------------------------------------------------------------------------
# Tujuan:
# - mengurangi error acak saat request station dipanggil cepat / berbarengan
# - menghindari open handle HDF5 terlalu lama
# - fallback engine jika salah satu backend tidak stabil
NETCDF_READ_LOCK = threading.RLock()


@dataclass
class SamplingMeta:
    method: str = "window_mean_3x3_wet_cells"
    window: int = 3
    fallback: str = "nearest_finite_wet_cell"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


# -----------------------------------------------------------------------------
# Source file finders
# -----------------------------------------------------------------------------
def _find_temp_file(date: str) -> Path | None:
    root = _repo_root()
    yyyy, mm = date[:4], date[5:7]

    candidates = [
        root / f"data/time_series/aceh/banda_aceh_aceh_besar/temp3d/raw/temp3d_raw_{date}.nc",
        root / f"data/raw/aceh_simeulue/temp3d/{yyyy}/{mm}/temp3d_aceh_{date}.nc",
        root / f"data/raw/aceh_simeulue/temp/{yyyy}/{mm}/temp_aceh_{date}.nc",
        root / f"data/raw/aceh_simeulue/thetao/{yyyy}/{mm}/thetao_aceh_{date}.nc",
    ]

    for p in candidates:
        if p.exists():
            return p
    return None


def _find_sal_file(date: str) -> Path | None:
    root = _repo_root()
    yyyy, mm = date[:4], date[5:7]

    candidates = [
        root / f"data/time_series/aceh/banda_aceh_aceh_besar/sal3d/raw/sal3d_raw_{date}.nc",
        root / f"data/raw/aceh_simeulue/sal3d/{yyyy}/{mm}/sal3d_aceh_{date}.nc",
        root / f"data/raw/aceh_simeulue/sal/{yyyy}/{mm}/sal_aceh_{date}.nc",
        root / f"data/raw/aceh_simeulue/so/{yyyy}/{mm}/so_aceh_{date}.nc",
    ]

    for p in candidates:
        if p.exists():
            return p
    return None


# -----------------------------------------------------------------------------
# Dataset helpers
# -----------------------------------------------------------------------------
def _detect_var_name(ds: xr.Dataset, candidates: list[str]) -> str:
    for name in candidates:
        if name in ds.data_vars:
            return name
    raise KeyError(
        f"Variabel tidak ditemukan. Kandidat: {candidates}. "
        f"Tersedia: {list(ds.data_vars)}"
    )


def _detect_dim_name(ds: xr.Dataset, candidates: list[str]) -> str:
    for name in candidates:
        if name in ds.coords or name in ds.dims:
            return name
    raise KeyError(
        f"Dimensi/koordinat tidak ditemukan. Kandidat: {candidates}. "
        f"Coords: {list(ds.coords)} Dims: {list(ds.dims)}"
    )


def _pick_first_time_if_any(da: xr.DataArray) -> xr.DataArray:
    for tname in ["time", "valid_time"]:
        if tname in da.dims:
            return da.isel({tname: 0})
    return da


def _to_float(v: Any) -> float | None:
    try:
        x = float(v)
        if np.isfinite(x):
            return x
    except Exception:
        pass
    return None


def _nearest_index(values: np.ndarray, target: float) -> int:
    return int(np.nanargmin(np.abs(values - target)))


def _window_slices(center_idx: int, size: int, max_len: int) -> slice:
    half = size // 2
    a = max(0, center_idx - half)
    b = min(max_len, center_idx + half + 1)
    return slice(a, b)


def _open_dataset_safe(nc_path: Path) -> xr.Dataset:
    """
    Buka dataset dengan cara yang lebih aman untuk file NetCDF/HDF5.
    Dataset dibaca ke memory agar handle file cepat dilepas.

    Prioritas engine:
    1) h5netcdf
    2) netcdf4
    3) default xarray

    Lock dipakai untuk mengurangi race/segfault saat request datang berbarengan.
    """
    last_err: Exception | None = None

    with NETCDF_READ_LOCK:
        for engine in ("h5netcdf", "netcdf4", None):
            try:
                kwargs = dict(
                    mask_and_scale=True,
                    decode_cf=True,
                    cache=False,
                )
                if engine is None:
                    with xr.open_dataset(nc_path, **kwargs) as ds:
                        loaded = ds.load()
                    return loaded

                with xr.open_dataset(nc_path, engine=engine, **kwargs) as ds:
                    loaded = ds.load()
                return loaded

            except Exception as e:
                last_err = e

    raise RuntimeError(f"Failed to open dataset safely: {nc_path} ({last_err})")


# -----------------------------------------------------------------------------
# Core sampler
# -----------------------------------------------------------------------------
def _sample_profile_core(
    nc_path: Path,
    var_candidates: list[str],
    station_lat: float,
    station_lon: float,
    max_depth: int,
) -> tuple[list[tuple[float, float]], dict]:
    ds = _open_dataset_safe(nc_path)

    var_name = _detect_var_name(ds, var_candidates)
    lat_name = _detect_dim_name(ds, ["latitude", "lat"])
    lon_name = _detect_dim_name(ds, ["longitude", "lon"])
    depth_name = _detect_dim_name(ds, ["depth", "depthu", "depthv", "lev"])

    da = ds[var_name]
    da = _pick_first_time_if_any(da)

    lats = np.asarray(ds[lat_name].values, dtype=float)
    lons = np.asarray(ds[lon_name].values, dtype=float)
    depths = np.asarray(ds[depth_name].values, dtype=float)

    iy = _nearest_index(lats, station_lat)
    ix = _nearest_index(lons, station_lon)

    # window mean 3x3
    ysl = _window_slices(iy, 3, len(lats))
    xsl = _window_slices(ix, 3, len(lons))

    sub = da.isel({lat_name: ysl, lon_name: xsl})
    prof = sub.mean(dim=[lat_name, lon_name], skipna=True)

    values = np.asarray(prof.values, dtype=float)

    # fallback 1: nearest cell
    if not np.isfinite(values).any():
        prof = da.isel({lat_name: iy, lon_name: ix})
        values = np.asarray(prof.values, dtype=float)

    # fallback 2: expand 5x5
    if not np.isfinite(values).any():
        ysl = _window_slices(iy, 5, len(lats))
        xsl = _window_slices(ix, 5, len(lons))
        sub = da.isel({lat_name: ysl, lon_name: xsl})
        prof = sub.mean(dim=[lat_name, lon_name], skipna=True)
        values = np.asarray(prof.values, dtype=float)

    points: list[tuple[float, float]] = []
    for z, v in zip(depths, values):
        zf = _to_float(z)
        vf = _to_float(v)
        if zf is None or vf is None:
            continue
        if zf > float(max_depth):
            continue
        points.append((zf, vf))

    points.sort(key=lambda x: x[0])

    sampling = SamplingMeta()

    return points, {
        "sampling": {
            "method": sampling.method,
            "window": sampling.window,
            "fallback": sampling.fallback,
        },
        "source_file": str(nc_path),
        "var_name": var_name,
    }


# -----------------------------------------------------------------------------
# Response builder
# -----------------------------------------------------------------------------
def _build_profile_response(
    *,
    station: dict,
    date: str,
    points: list[tuple[float, float]],
    key_name: str,
    source_file: str,
    sampling: dict,
    trace: str,
) -> dict:
    out_points = [{"depth_m": float(z), key_name: float(v)} for z, v in points]

    return {
        "mode": "station",
        "station": station["id"],
        "region": station["label"],
        "label": station["label"],
        "basin": station["basin"],
        "date": date,
        "location": {
            "lat": float(station["lat"]),
            "lon": float(station["lon"]),
        },
        "sampling": sampling,
        "points": out_points,
        "source": Path(source_file).name if source_file else None,
        "note": "Station profile derived from fixed-location ocean sampling.",
        "meta": {
            "generated_at": None,
            "trace": trace,
        },
    }


# -----------------------------------------------------------------------------
# Public API - temperature
# -----------------------------------------------------------------------------
def get_temp_profile_station(date: str, station_id: str, max_depth: int = 200) -> dict:
    station = get_station(station_id)
    if not station:
        return {
            "error": f"Unknown station: {station_id}",
            "points": [],
        }

    nc_path = _find_temp_file(date)
    if not nc_path:
        return {
            "mode": "station",
            "station": station["id"],
            "region": station["label"],
            "label": station["label"],
            "basin": station["basin"],
            "date": date,
            "location": {"lat": station["lat"], "lon": station["lon"]},
            "points": [],
            "error": f"Temperature source file not found for {date}",
        }

    try:
        points, meta = _sample_profile_core(
            nc_path=nc_path,
            var_candidates=["thetao", "temperature", "temp", "analysed_sst"],
            station_lat=float(station["lat"]),
            station_lon=float(station["lon"]),
            max_depth=max_depth,
        )
    except Exception as e:
        return {
            "mode": "station",
            "station": station["id"],
            "region": station["label"],
            "label": station["label"],
            "basin": station["basin"],
            "date": date,
            "location": {"lat": station["lat"], "lon": station["lon"]},
            "points": [],
            "error": f"Failed to read temperature profile for {station_id} on {date}: {e}",
        }

    if not points:
        return {
            "mode": "station",
            "station": station["id"],
            "region": station["label"],
            "label": station["label"],
            "basin": station["basin"],
            "date": date,
            "location": {"lat": station["lat"], "lon": station["lon"]},
            "points": [],
            "error": f"No valid temperature profile points for {station_id} on {date}",
        }

    return _build_profile_response(
        station=station,
        date=date,
        points=points,
        key_name="temp_c",
        source_file=meta["source_file"],
        sampling=meta["sampling"],
        trace=f"temp-profile-station:{station_id}",
    )


# -----------------------------------------------------------------------------
# Public API - salinity
# -----------------------------------------------------------------------------
def get_sal_profile_station(date: str, station_id: str, max_depth: int = 200) -> dict:
    station = get_station(station_id)
    if not station:
        return {
            "error": f"Unknown station: {station_id}",
            "points": [],
        }

    nc_path = _find_sal_file(date)
    if not nc_path:
        return {
            "mode": "station",
            "station": station["id"],
            "region": station["label"],
            "label": station["label"],
            "basin": station["basin"],
            "date": date,
            "location": {"lat": station["lat"], "lon": station["lon"]},
            "points": [],
            "error": f"Salinity source file not found for {date}",
        }

    try:
        points, meta = _sample_profile_core(
            nc_path=nc_path,
            var_candidates=["so", "salinity", "sal", "salt"],
            station_lat=float(station["lat"]),
            station_lon=float(station["lon"]),
            max_depth=max_depth,
        )
    except Exception as e:
        return {
            "mode": "station",
            "station": station["id"],
            "region": station["label"],
            "label": station["label"],
            "basin": station["basin"],
            "date": date,
            "location": {"lat": station["lat"], "lon": station["lon"]},
            "points": [],
            "error": f"Failed to read salinity profile for {station_id} on {date}: {e}",
        }

    if not points:
        return {
            "mode": "station",
            "station": station["id"],
            "region": station["label"],
            "label": station["label"],
            "basin": station["basin"],
            "date": date,
            "location": {"lat": station["lat"], "lon": station["lon"]},
            "points": [],
            "error": f"No valid salinity profile points for {station_id} on {date}",
        }

    return _build_profile_response(
        station=station,
        date=date,
        points=points,
        key_name="sal_psu",
        source_file=meta["source_file"],
        sampling=meta["sampling"],
        trace=f"sal-profile-station:{station_id}",
    )