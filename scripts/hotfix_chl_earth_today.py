from __future__ import annotations

import json
import re
from datetime import datetime, timezone, date
from pathlib import Path

import numpy as np
import xarray as xr


ROOT = Path("/home/coastalai/NELAYA-AI-LAB")
EARTH_PATH = ROOT / "data/earth/earth_signals_today.json"
CHL_DIR = ROOT / "data/raw/aceh_simeulue/chl_nrt"


def parse_date_safe(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        pass
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def find_latest_valid_chl():
    files = sorted(CHL_DIR.rglob("*.nc"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        raise FileNotFoundError(f"Tidak ada file CHL NetCDF di {CHL_DIR}")

    for path in files[:20]:
        try:
            ds = xr.open_dataset(path)

            var_name = None
            for candidate in ["CHL", "chl", "chlorophyll", "chlor_a", "chla"]:
                if candidate in ds.data_vars:
                    var_name = candidate
                    break

            if var_name is None:
                ds.close()
                continue

            da = ds[var_name]

            time_name = None
            for candidate in ["time", "valid_time", "date"]:
                if candidate in da.dims:
                    time_name = candidate
                    break

            if time_name:
                ntime = da.sizes[time_name]
                indices = list(range(ntime - 1, -1, -1))
            else:
                indices = [None]

            for idx in indices:
                if idx is None:
                    slice_da = da
                    source_time = None
                else:
                    slice_da = da.isel({time_name: idx})
                    source_time_raw = ds[time_name].values[idx]
                    source_time = str(source_time_raw)[:10]

                arr = slice_da.values
                valid = np.isfinite(arr)
                valid_count = int(valid.sum())
                total_count = int(arr.size)

                if valid_count <= 0:
                    continue

                mean_val = float(np.nanmean(arr))
                min_val = float(np.nanmin(arr))
                max_val = float(np.nanmax(arr))
                valid_ratio = valid_count / total_count if total_count else 0.0

                ds.close()

                return {
                    "value": mean_val,
                    "min": min_val,
                    "max": max_val,
                    "valid_count": valid_count,
                    "total_count": total_count,
                    "valid_ratio": valid_ratio,
                    "source_time": source_time,
                    "source_path": str(path),
                    "var_name": var_name,
                }

            ds.close()

        except Exception as e:
            print(f"Skip file bermasalah: {path} -> {e}")

    raise RuntimeError("Tidak menemukan slice CHL valid dari file terbaru.")


def main():
    if not EARTH_PATH.exists():
        raise FileNotFoundError(f"earth_signals_today.json tidak ditemukan: {EARTH_PATH}")

    earth = json.loads(EARTH_PATH.read_text(encoding="utf-8"))
    chl = find_latest_valid_chl()

    # Tentukan tanggal acuan untuk lag.
    ref_date = (
        parse_date_safe(earth.get("date"))
        or parse_date_safe(earth.get("snapshot_date"))
        or parse_date_safe(earth.get("latest_available_date"))
        or datetime.now(timezone.utc).date()
    )

    src_date = parse_date_safe(chl.get("source_time"))
    lag_days = (ref_date - src_date).days if ref_date and src_date else None

    metrics = earth.setdefault("metrics", {})

    metrics["chl"] = {
        "value": chl["value"],
        "unit": "mg/m³",
        "source_kind": "chl_nrt",
        "source_date": chl["source_time"],
        "source_path": chl["source_path"],
        "variable": chl["var_name"],
        "valid_count": chl["valid_count"],
        "total_count": chl["total_count"],
        "valid_ratio": round(chl["valid_ratio"], 4),
        "min": chl["min"],
        "max": chl["max"],
        "data_status": "accepted_latest_valid_slice",
        "lag_days": lag_days,
        "note": "CHL diambil dari latest valid time di dalam NetCDF, bukan dari tanggal nama file.",
    }

    # Top-level alias agar router/card lama tetap bisa membaca.
    earth["chl_mg_m3"] = chl["value"]
    earth["chl_source_date"] = chl["source_time"]
    earth["chl_lag_days"] = lag_days
    earth["chl_data_status"] = "accepted_latest_valid_slice"

    EARTH_PATH.write_text(
        json.dumps(earth, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("✅ CHL hotfix applied")
    print("value_mg_m3:", chl["value"])
    print("source_time:", chl["source_time"])
    print("valid:", chl["valid_count"], "/", chl["total_count"])
    print("lag_days:", lag_days)
    print("source_path:", chl["source_path"])


if __name__ == "__main__":
    main()
