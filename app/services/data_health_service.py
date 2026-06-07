from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import xarray as xr


DATA_SPECS = {
    "chl_nrt": {
        "required_vars": ["CHL", "chl", "chlorophyll"],
    },
    "sst_nrt": {
        "required_vars": ["analysed_sst", "sst", "thetao"],
    },
    "wind_nrt": {
        "required_vars": ["eastward_wind", "northward_wind", "u10", "v10"],
    },
    "wave_anfc": {
        "required_vars": ["VHM0", "VTM10", "VMDR"],
    },
    "ssh_anfc": {
        "required_vars": ["zos", "adt", "sla"],
    },
    "sal_anfc": {
        "required_vars": ["so", "salinity"],
    },
    "phy_cur": {
        "required_vars": ["uo", "vo"],
    },
}


def _find_matching_vars(ds, required_vars):
    found = []
    for var in required_vars:
        if var in ds.data_vars:
            found.append(var)
    return found


def _detect_coord_name(ds, candidates):
    for name in candidates:
        if name in ds.coords or name in ds.dims:
            return name
    return None


def _normalize_np_datetime_to_date(value) -> str | None:
    try:
        return str(np.datetime64(value, "D"))
    except Exception:
        return None


def check_netcdf_file(kind: str, file_path: str, snapshot_date: str | None = None) -> dict:
    path = Path(file_path)

    result = {
        "kind": kind,
        "snapshot_date": snapshot_date,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "file_path": str(path),
        "file_exists": path.exists(),
        "file_size_bytes": None,
        "status": "unknown",
        "message": "",
        "variables_found": [],
        "data_vars": [],
        "dims_found": [],
        "time_values": [],
        "internal_dates": [],
        "internal_latest_date": None,
        "date_match": None,
        "lon_range": None,
        "lat_range": None,
        "valid_ratio": None,
        "nan_ratio": None,
        "min_value": None,
        "max_value": None,
    }

    if not path.exists():
        result["status"] = "missing"
        result["message"] = "File tidak ditemukan."
        return result

    result["file_size_bytes"] = path.stat().st_size

    if result["file_size_bytes"] == 0:
        result["status"] = "corrupt"
        result["message"] = "File ada tetapi ukurannya 0 byte."
        return result

    try:
        ds = xr.open_dataset(path)
    except Exception as exc:
        result["status"] = "corrupt"
        result["message"] = f"File tidak bisa dibuka sebagai NetCDF: {exc}"
        return result

    result["data_vars"] = list(ds.data_vars)
    result["dims_found"] = list(ds.dims)

    spec = DATA_SPECS.get(kind, {})
    required_vars = spec.get("required_vars", [])

    found_vars = _find_matching_vars(ds, required_vars)
    result["variables_found"] = found_vars

    if not found_vars:
        result["status"] = "partial"
        result["message"] = (
            f"Tidak ditemukan variabel utama untuk {kind}. "
            f"Variabel tersedia: {list(ds.data_vars)}"
        )
        return result

    lon_name = _detect_coord_name(ds, ["longitude", "lon", "x"])
    lat_name = _detect_coord_name(ds, ["latitude", "lat", "y"])
    time_name = _detect_coord_name(ds, ["time"])

    if lon_name:
        try:
            lon_values = ds[lon_name].values
            result["lon_range"] = [
                float(np.nanmin(lon_values)),
                float(np.nanmax(lon_values)),
            ]
        except Exception:
            result["lon_range"] = None

    if lat_name:
        try:
            lat_values = ds[lat_name].values
            result["lat_range"] = [
                float(np.nanmin(lat_values)),
                float(np.nanmax(lat_values)),
            ]
        except Exception:
            result["lat_range"] = None

    if time_name:
        try:
            time_values_raw = ds[time_name].values
            result["time_values"] = [str(v) for v in time_values_raw[:5]]

            internal_dates = []
            for v in time_values_raw:
                d = _normalize_np_datetime_to_date(v)
                if d:
                    internal_dates.append(d)

            result["internal_dates"] = sorted(list(set(internal_dates)))
            result["internal_latest_date"] = max(internal_dates) if internal_dates else None
        except Exception:
            result["time_values"] = []
            result["internal_dates"] = []
            result["internal_latest_date"] = None

    primary_var = found_vars[0]

    try:
        arr = ds[primary_var].values
        total_count = arr.size

        if total_count == 0:
            result["status"] = "invalid"
            result["message"] = "Variabel utama tidak memiliki nilai."
            return result

        finite_mask = np.isfinite(arr)
        valid_count = int(finite_mask.sum())

        valid_ratio = valid_count / total_count
        nan_ratio = 1 - valid_ratio

        result["valid_ratio"] = round(valid_ratio, 6)
        result["nan_ratio"] = round(nan_ratio, 6)

        if valid_count == 0:
            result["status"] = "invalid"
            result["message"] = "Semua nilai variabel utama NaN atau tidak valid."
            return result

        result["min_value"] = float(np.nanmin(arr))
        result["max_value"] = float(np.nanmax(arr))

    except Exception as exc:
        result["status"] = "invalid"
        result["message"] = f"Gagal membaca nilai variabel utama: {exc}"
        return result

    if result["valid_ratio"] < 0.01:
        result["status"] = "invalid"
        result["message"] = "Rasio nilai valid terlalu rendah."
        return result

    if snapshot_date and result.get("internal_latest_date"):
        internal_latest = result["internal_latest_date"]

        if internal_latest < snapshot_date:
            result["status"] = "stale"
            result["date_match"] = False
            result["message"] = (
                f"File tersedia dan nilai valid, tetapi tanggal internal terbaru "
                f"({internal_latest}) lebih tua dari snapshot_date ({snapshot_date})."
            )
            return result

        result["date_match"] = True

    result["status"] = "available"
    result["message"] = "Data tersedia, bisa dibaca, dan memiliki nilai valid."
    return result
