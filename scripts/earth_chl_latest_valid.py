from __future__ import annotations

import json
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import xarray as xr


ROOT = Path("/home/coastalai/NELAYA-AI-LAB")
EARTH_PATH = ROOT / "data/earth/earth_signals_today.json"
CHL_DIR = ROOT / "data/raw/aceh_simeulue/chl_nrt"


CHL_VAR_CANDIDATES = [
    "CHL",
    "chl",
    "chlorophyll",
    "chlor_a",
    "chla",
    "chlorophyll_a",
    "mass_concentration_of_chlorophyll_a_in_sea_water",
]


def parse_date_safe(value: Any) -> Optional[date]:
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        pass
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def find_chl_var(ds: xr.Dataset) -> Optional[str]:
    for name in CHL_VAR_CANDIDATES:
        if name in ds.data_vars:
            return name

    for name in ds.data_vars:
        low = name.lower()
        if "chl" in low or "chlor" in low or "chla" in low:
            return name

    return None


def find_time_name(da: xr.DataArray) -> Optional[str]:
    for name in ["time", "valid_time", "date"]:
        if name in da.dims:
            return name
    return None


def find_latest_valid_chl(max_files: int = 30) -> Dict[str, Any]:
    files = sorted(
        CHL_DIR.rglob("*.nc"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not files:
        raise FileNotFoundError(f"Tidak ada file CHL NetCDF di {CHL_DIR}")

    checked = []

    for path in files[:max_files]:
        item = {
            "path": str(path),
            "status": "checked",
        }

        try:
            ds = xr.open_dataset(path)
            var_name = find_chl_var(ds)

            if not var_name:
                item["status"] = "no_chl_var"
                checked.append(item)
                ds.close()
                continue

            da = ds[var_name]
            time_name = find_time_name(da)

            if time_name:
                ntime = int(da.sizes[time_name])
                indices = range(ntime - 1, -1, -1)
            else:
                indices = [None]

            for idx in indices:
                if idx is None:
                    slice_da = da
                    source_time = None
                else:
                    slice_da = da.isel({time_name: idx})
                    source_time = str(ds[time_name].values[idx])[:10]

                arr = slice_da.values
                valid = np.isfinite(arr)
                valid_count = int(valid.sum())
                total_count = int(arr.size)

                if total_count <= 0 or valid_count <= 0:
                    continue

                mean_val = float(np.nanmean(arr))
                min_val = float(np.nanmin(arr))
                max_val = float(np.nanmax(arr))
                median_val = float(np.nanmedian(arr))
                valid_ratio = valid_count / total_count

                ds.close()

                return {
                    "value": mean_val,
                    "median": median_val,
                    "min": min_val,
                    "max": max_val,
                    "valid_count": valid_count,
                    "total_count": total_count,
                    "valid_ratio": valid_ratio,
                    "source_time": source_time,
                    "source_path": str(path),
                    "variable": var_name,
                    "data_status": "accepted_latest_valid_slice",
                    "checked_files": checked,
                }

            item["status"] = "all_nan_or_invalid"
            checked.append(item)
            ds.close()

        except Exception as e:
            item["status"] = "open_error"
            item["error"] = str(e)
            checked.append(item)

    raise RuntimeError("Tidak menemukan slice CHL valid dari file-file CHL terbaru.")


def main() -> None:
    if not EARTH_PATH.exists():
        raise FileNotFoundError(f"earth_signals_today.json tidak ditemukan: {EARTH_PATH}")

    earth = json.loads(EARTH_PATH.read_text(encoding="utf-8"))
    chl = find_latest_valid_chl()

    ref_date = (
        parse_date_safe(earth.get("date"))
        or parse_date_safe(earth.get("snapshot_date"))
        or parse_date_safe(earth.get("latest_available_date"))
        or datetime.now(timezone.utc).date()
    )

    source_date = parse_date_safe(chl.get("source_time"))
    lag_days = (ref_date - source_date).days if ref_date and source_date else None

    metrics = earth.setdefault("metrics", {})

    metrics["chl"] = {
        "value": chl["value"],
        "unit": "mg/m³",
        "source_kind": "chl_nrt",
        "source_date": chl["source_time"],
        "source_path": chl["source_path"],
        "variable": chl["variable"],
        "valid_count": chl["valid_count"],
        "total_count": chl["total_count"],
        "valid_ratio": round(chl["valid_ratio"], 4),
        "mean": chl["value"],
        "median": chl["median"],
        "min": chl["min"],
        "max": chl["max"],
        "lag_days": lag_days,
        "data_status": chl["data_status"],
        "note": "CHL diambil dari latest valid time slice di dalam NetCDF, bukan dari tanggal nama file.",
    }

    earth["chl_mg_m3"] = chl["value"]
    earth["chl_source_date"] = chl["source_time"]
    earth["chl_lag_days"] = lag_days
    earth["chl_valid_ratio"] = round(chl["valid_ratio"], 4)
    earth["chl_data_status"] = chl["data_status"]

    data_quality = earth.setdefault("data_quality", {})
    data_quality["chl"] = {
        "status": chl["data_status"],
        "source_date": chl["source_time"],
        "lag_days": lag_days,
        "valid_ratio": round(chl["valid_ratio"], 4),
        "valid_count": chl["valid_count"],
        "total_count": chl["total_count"],
        "source_path": chl["source_path"],
        "note": "Accepted because the latest valid CHL slice was found inside the NetCDF file.",
    }

    earth["generated_at"] = earth.get("generated_at") or datetime.now(timezone.utc).isoformat()
    earth["last_chl_repair_at"] = datetime.now(timezone.utc).isoformat()

    EARTH_PATH.write_text(
        json.dumps(earth, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("✅ CHL latest-valid repair applied")
    print("value_mg_m3 :", chl["value"])
    print("source_date :", chl["source_time"])
    print("lag_days    :", lag_days)
    print("valid_ratio :", round(chl["valid_ratio"], 4))
    print("valid_grid  :", chl["valid_count"], "/", chl["total_count"])
    print("source_path :", chl["source_path"])


if __name__ == "__main__":
    main()
