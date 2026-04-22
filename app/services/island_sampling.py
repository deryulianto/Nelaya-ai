from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import math

import numpy as np
import xarray as xr
import os
import threading

os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
NETCDF_READ_LOCK = threading.RLock()


# ============================================================
# Konfigurasi zona pulau kecil Aceh
# Format bbox: (lon_min, lon_max, lat_min, lat_max)
# Catatan:
# - dibuat cukup aman dan agak longgar untuk versi awal
# - bisa kita rapikan lagi nanti sesuai kebutuhan ilmiah
# ============================================================
ISLAND_BBOX: Dict[str, Tuple[float, float, float, float]] = {
    "sabang": (94.9, 96.4, 5.2, 6.3),
    "simeulue": (95.1, 97.2, 1.6, 3.2),
    "banyak": (96.0, 98.4, 1.4, 3.4),
}


# ============================================================
# Root folder data mentah mengikuti pola NELAYA-AI
# ============================================================
RAW_ROOT = Path("data/raw/aceh_simeulue")


# ============================================================
# Pemetaan kandidat folder dan nama variabel
# ============================================================
DATASET_SPECS: Dict[str, Dict[str, Any]] = {
    "sst_c": {
        "folders": ["sst_nrt", "sst", "sea_surface_temperature"],
        "var_candidates": [
            "thetao",
            "analysed_sst",
            "sst",
            "sea_surface_temperature",
        ],
    },
    "chl_mg_m3": {
        "folders": ["chl_nrt", "chl", "chlorophyll"],
        "var_candidates": [
            "CHL",
            "chlor_a",
            "chl",
            "chlorophyll",
        ],
    },
    "wind_ms": {
        "folders": ["wind_nrt", "wind", "winds"],
        "u_candidates": [
            "eastward_wind",
            "u10",
            "uwnd",
            "u",
        ],
        "v_candidates": [
            "northward_wind",
            "v10",
            "vwnd",
            "v",
        ],
    },
    "wave_m": {
        "folders": ["wave_anfc", "wave", "waves"],
        "var_candidates": [
            "VHM0",
            "swh",
            "wave_height",
            "hs",
        ],
    },
    "ssh_cm": {
        "folders": ["ssh_anfc", "ssh", "sea_level"],
        "var_candidates": [
            "zos",
            "ssh",
            "sea_surface_height",
        ],
        "scale": 100.0,  # meter -> cm
    },
    "salinity_psu": {
        "folders": ["sal_anfc", "sal", "salinity"],
        "var_candidates": [
            "so",
            "salinity",
            "sss",
        ],
    },
}


# ============================================================
# Utilities umum
# ============================================================
def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        value = float(value)
        if math.isnan(value):
            return None
        return value
    except Exception:
        return None


def _existing_dirs(candidates: List[str]) -> List[Path]:
    paths: List[Path] = []
    for name in candidates:
        p = RAW_ROOT / name
        if p.exists() and p.is_dir():
            paths.append(p)
    return paths


def _list_nc_files(base_dirs: List[Path]) -> List[Path]:
    files: List[Path] = []
    for base in base_dirs:
        files.extend(base.rglob("*.nc"))
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _latest_nc_file(folder_candidates: List[str]) -> Optional[Path]:
    dirs = _existing_dirs(folder_candidates)
    if not dirs:
        return None
    files = _list_nc_files(dirs)
    return files[0] if files else None


def _find_coord_name(ds: xr.Dataset, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in ds.coords:
            return c
        if c in ds.variables:
            return c
    return None


def _get_lon_lat_names(ds: xr.Dataset) -> Tuple[str, str]:
    lon_name = _find_coord_name(ds, ["longitude", "lon", "x"])
    lat_name = _find_coord_name(ds, ["latitude", "lat", "y"])
    if lon_name is None or lat_name is None:
        raise ValueError("Koordinat lon/lat tidak ditemukan pada dataset.")
    return lon_name, lat_name


def _normalize_longitude_if_needed(ds: xr.Dataset, lon_name: str, lon_min: float, lon_max: float) -> xr.Dataset:
    """
    Jika dataset memakai 0..360 dan bbox kita -180..180 / sekitar Aceh,
    ubah ke -180..180 agar slice lebih aman.
    """
    lon_vals = ds[lon_name].values
    if np.nanmax(lon_vals) > 180:
        new_lon = (((lon_vals + 180) % 360) - 180).astype(float)
        ds = ds.assign_coords({lon_name: new_lon}).sortby(lon_name)
    return ds


def _slice_coord(ds: xr.Dataset, coord_name: str, vmin: float, vmax: float) -> xr.Dataset:
    vals = ds[coord_name].values
    if vals[0] <= vals[-1]:
        return ds.sel({coord_name: slice(vmin, vmax)})
    return ds.sel({coord_name: slice(vmax, vmin)})


def _subset_bbox(ds: xr.Dataset, bbox: Tuple[float, float, float, float]) -> xr.Dataset:
    lon_min, lon_max, lat_min, lat_max = bbox
    lon_name, lat_name = _get_lon_lat_names(ds)

    ds = _normalize_longitude_if_needed(ds, lon_name, lon_min, lon_max)
    ds = _slice_coord(ds, lon_name, lon_min, lon_max)
    ds = _slice_coord(ds, lat_name, lat_min, lat_max)
    return ds


def _pick_first_var(ds: xr.Dataset, candidates: List[str]) -> Optional[str]:
    for name in candidates:
        if name in ds.data_vars:
            return name
    for name in candidates:
        if name in ds.variables:
            return name
    return None

def _pick_var_by_tokens(
    ds: xr.Dataset,
    positive_tokens: List[str],
    negative_tokens: Optional[List[str]] = None,
) -> Optional[str]:
    negative_tokens = negative_tokens or []

    candidates = list(ds.data_vars) + [v for v in ds.variables if v not in ds.data_vars]
    for name in candidates:
        lname = name.lower()
        if all(tok.lower() in lname for tok in positive_tokens):
            if not any(tok.lower() in lname for tok in negative_tokens):
                return name
    return None



def _select_surface_if_needed(da: xr.DataArray) -> xr.DataArray:
    """
    Banyak produk punya dim waktu/depth/member/expver.
    Ambil index 0 untuk dim non-spasial yang umum, tapi jangan sentuh lat/lon.
    """
    preferred_non_spatial = [
        "time",
        "depth",
        "depthu",
        "depthv",
        "depthw",
        "deptht",
        "expver",
        "member",
        "ensemble",
    ]

    for dim in preferred_non_spatial:
        if dim in da.dims and da.sizes.get(dim, 0) > 0:
            da = da.isel({dim: 0})

    spatial_dim_candidates = {"latitude", "lat", "y", "longitude", "lon", "x"}
    remaining_dims = [d for d in da.dims if d not in spatial_dim_candidates]
    for dim in remaining_dims:
        if da.sizes.get(dim, 0) > 0:
            da = da.isel({dim: 0})

    return da


def _nanmean_dataarray(da: xr.DataArray) -> Optional[float]:
    try:
        val = da.mean(skipna=True).values
        if isinstance(val, np.ndarray):
            if val.size == 0:
                return None
            val = val.item()
        return _to_float(val)
    except Exception:
        return None


def _read_mean_scalar_from_file(
    file_path: Path,
    var_candidates: List[str],
    bbox: Tuple[float, float, float, float],
    scale: float = 1.0,
) -> Optional[float]:
    try:
        with NETCDF_READ_LOCK:
            with xr.open_dataset(file_path) as ds:
                ds = _subset_bbox(ds, bbox)
                var_name = _pick_first_var(ds, var_candidates)
                if var_name is None:
                    return None
                da = ds[var_name]
                da = _select_surface_if_needed(da)
                value = _nanmean_dataarray(da)
                if value is None:
                    return None
                return value * scale
    except Exception:
        return None


def _read_wind_speed_from_file(
    file_path: Path,
    u_candidates: List[str],
    v_candidates: List[str],
    bbox: Tuple[float, float, float, float],
) -> Optional[float]:
    try:
        with NETCDF_READ_LOCK:
            with xr.open_dataset(file_path) as ds:
                ds = _subset_bbox(ds, bbox)

                u_name = _pick_first_var(ds, u_candidates)
                v_name = _pick_first_var(ds, v_candidates)

                if u_name is None:
                    u_name = (
                        _pick_var_by_tokens(ds, ["east", "wind"])
                        or _pick_var_by_tokens(ds, ["u10"], ["longitude", "latitude"])
                        or _pick_var_by_tokens(ds, ["uwnd"])
                        or _pick_var_by_tokens(ds, ["u"], ["longitude", "latitude"])
                    )

                if v_name is None:
                    v_name = (
                        _pick_var_by_tokens(ds, ["north", "wind"])
                        or _pick_var_by_tokens(ds, ["v10"], ["longitude", "latitude"])
                        or _pick_var_by_tokens(ds, ["vwnd"])
                        or _pick_var_by_tokens(ds, ["v"], ["longitude", "latitude"])
                    )

                if u_name is None or v_name is None:
                    return None

                u = _select_surface_if_needed(ds[u_name])
                v = _select_surface_if_needed(ds[v_name])

                speed = np.sqrt((u ** 2) + (v ** 2))
                return _nanmean_dataarray(speed)
    except Exception:
        return None


def _guess_dataset_date_from_path(file_path: Path) -> Optional[str]:
    """
    Coba ekstrak YYYY-MM-DD dari nama file.
    """
    text = file_path.name
    for token in text.replace("_", "-").split("-"):
        pass

    import re

    m = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    return None


# ============================================================
# Sampling utama per pulau
# ============================================================
def sample_island_metrics(island_key: str) -> Dict[str, Any]:
    if island_key not in ISLAND_BBOX:
        raise ValueError(f"island_key tidak dikenal: {island_key}")

    bbox = ISLAND_BBOX[island_key]

    metrics: Dict[str, Optional[float]] = {
        "sst_c": None,
        "chl_mg_m3": None,
        "wind_ms": None,
        "wave_m": None,
        "ssh_cm": None,
        "salinity_psu": None,
    }

    sources: Dict[str, Optional[str]] = {
        "sst_c": None,
        "chl_mg_m3": None,
        "wind_ms": None,
        "wave_m": None,
        "ssh_cm": None,
        "salinity_psu": None,
    }

    dataset_dates: Dict[str, Optional[str]] = {
        "sst_c": None,
        "chl_mg_m3": None,
        "wind_ms": None,
        "wave_m": None,
        "ssh_cm": None,
        "salinity_psu": None,
    }

    # SST
    spec = DATASET_SPECS["sst_c"]
    file_path = _latest_nc_file(spec["folders"])
    if file_path is not None:
        metrics["sst_c"] = _read_mean_scalar_from_file(
            file_path=file_path,
            var_candidates=spec["var_candidates"],
            bbox=bbox,
        )
        sources["sst_c"] = str(file_path)
        dataset_dates["sst_c"] = _guess_dataset_date_from_path(file_path)

    # CHL
    spec = DATASET_SPECS["chl_mg_m3"]
    file_path = _latest_nc_file(spec["folders"])
    if file_path is not None:
        metrics["chl_mg_m3"] = _read_mean_scalar_from_file(
            file_path=file_path,
            var_candidates=spec["var_candidates"],
            bbox=bbox,
        )
        sources["chl_mg_m3"] = str(file_path)
        dataset_dates["chl_mg_m3"] = _guess_dataset_date_from_path(file_path)

    # WIND
    spec = DATASET_SPECS["wind_ms"]
    file_path = _latest_nc_file(spec["folders"])
    if file_path is not None:
        metrics["wind_ms"] = _read_wind_speed_from_file(
            file_path=file_path,
            u_candidates=spec["u_candidates"],
            v_candidates=spec["v_candidates"],
            bbox=bbox,
        )
        sources["wind_ms"] = str(file_path)
        dataset_dates["wind_ms"] = _guess_dataset_date_from_path(file_path)

    # WAVE
    spec = DATASET_SPECS["wave_m"]
    file_path = _latest_nc_file(spec["folders"])
    if file_path is not None:
        metrics["wave_m"] = _read_mean_scalar_from_file(
            file_path=file_path,
            var_candidates=spec["var_candidates"],
            bbox=bbox,
        )
        sources["wave_m"] = str(file_path)
        dataset_dates["wave_m"] = _guess_dataset_date_from_path(file_path)

    # SSH
    spec = DATASET_SPECS["ssh_cm"]
    file_path = _latest_nc_file(spec["folders"])
    if file_path is not None:
        metrics["ssh_cm"] = _read_mean_scalar_from_file(
            file_path=file_path,
            var_candidates=spec["var_candidates"],
            bbox=bbox,
            scale=spec.get("scale", 1.0),
        )
        sources["ssh_cm"] = str(file_path)
        dataset_dates["ssh_cm"] = _guess_dataset_date_from_path(file_path)

    # SALINITY
    spec = DATASET_SPECS["salinity_psu"]
    file_path = _latest_nc_file(spec["folders"])
    if file_path is not None:
        metrics["salinity_psu"] = _read_mean_scalar_from_file(
            file_path=file_path,
            var_candidates=spec["var_candidates"],
            bbox=bbox,
        )
        sources["salinity_psu"] = str(file_path)
        dataset_dates["salinity_psu"] = _guess_dataset_date_from_path(file_path)

    available_count = sum(v is not None for v in metrics.values())

    return {
        "island_key": island_key,
        "bbox": {
            "lon_min": bbox[0],
            "lon_max": bbox[1],
            "lat_min": bbox[2],
            "lat_max": bbox[3],
        },
        "metrics": metrics,
        "sources": sources,
        "dataset_dates": dataset_dates,
        "available_metric_count": available_count,
        "sampled_at": datetime.utcnow().isoformat() + "Z",
        "mode": "bbox-mean-from-raw-netcdf",
    }


def sample_all_islands() -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for island_key in ISLAND_BBOX.keys():
        result[island_key] = sample_island_metrics(island_key)
    return result
