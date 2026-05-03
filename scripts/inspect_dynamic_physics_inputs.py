#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Inspect latest dynamic NetCDF inputs for NELAYA-AI Ocean Dynamic Physics Layer.

Output:
  data/physics/dynamic_inputs_report.json

Purpose:
  - Pick latest file from each dynamic folder.
  - Read dims, coords, data_vars.
  - Detect likely variable names.
  - Check whether each file can be opened safely.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import xarray as xr


os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


ROOT = Path("data/raw/aceh_simeulue")
OUT_DIR = Path("data/physics")

SOURCES = {
    "current": ROOT / "cur_nrt",
    "ssh": ROOT / "ssh_anfc",
    "sst": ROOT / "sst_nrt",
    "chl": ROOT / "chl_nrt",
    "wave": ROOT / "wave_anfc",
    "wind": ROOT / "wind_nrt",
}

DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")

VAR_HINTS = {
    "current_u": ["uo", "u", "eastward_sea_water_velocity", "eastward_current"],
    "current_v": ["vo", "v", "northward_sea_water_velocity", "northward_current"],
    "ssh": ["zos", "adt", "sla", "ssh", "sea_surface_height"],
    "sst": ["analysed_sst", "sst", "sea_surface_temperature", "thetao"],
    "chl": ["chlor_a", "chl", "CHL", "mass_concentration_of_chlorophyll_a"],
    "wave": ["VHM0", "hs", "swh", "significant_wave_height"],
    "wind_u": ["u10", "uas", "eastward_wind", "u_wind"],
    "wind_v": ["v10", "vas", "northward_wind", "v_wind"],
    "wind_speed": ["wind_speed", "wind", "si10", "wind10m"],
}


def to_builtin(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_builtin(v) for v in obj]
    if isinstance(obj, tuple):
        return [to_builtin(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    return obj


def extract_date(path: Path) -> Optional[str]:
    m = DATE_RE.search(path.name)
    if m:
        return m.group(1)
    return None


def list_nc_files(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    return sorted(
        [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in [".nc", ".nc4"]]
    )


def pick_latest_file(folder: Path) -> Optional[Path]:
    files = list_nc_files(folder)
    dated = []

    for p in files:
        d = extract_date(p)
        if d:
            dated.append((d, p))

    if dated:
        dated.sort(key=lambda x: (x[0], str(x[1])))
        return dated[-1][1]

    if files:
        return files[-1]

    return None


def open_dataset_any(path: Path) -> xr.Dataset:
    engines = ["scipy", "netcdf4", "h5netcdf", None]
    errors = []

    for engine in engines:
        try:
            if engine is None:
                return xr.open_dataset(path, cache=False, decode_times=False)
            return xr.open_dataset(path, engine=engine, cache=False, decode_times=False)
        except Exception as e:
            errors.append(f"{engine}: {type(e).__name__}: {e}")

    raise RuntimeError("Cannot open with scipy/netcdf4/h5netcdf/auto. Errors: " + " | ".join(errors))


def detect_var(ds: xr.Dataset, hints: List[str]) -> Optional[str]:
    names = list(ds.data_vars) + list(ds.variables)

    for h in hints:
        for n in names:
            if n == h:
                return str(n)

    for h in hints:
        h_low = h.lower()
        for n in names:
            if h_low in str(n).lower():
                return str(n)

    return None


def inspect_file(kind: str, path: Optional[Path]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "kind": kind,
        "file": str(path) if path else None,
        "date_from_filename": extract_date(path) if path else None,
        "ok": False,
    }

    if path is None:
        result["error"] = "No file found."
        return result

    try:
        ds = open_dataset_any(path)
        result["ok"] = True
        result["dims"] = {str(k): int(v) for k, v in ds.sizes.items()}
        result["coords"] = [str(c) for c in ds.coords]
        result["data_vars"] = [str(v) for v in ds.data_vars]
        result["variables_detected"] = {
            key: detect_var(ds, hints)
            for key, hints in VAR_HINTS.items()
        }
        result["attrs_keys"] = list(map(str, ds.attrs.keys()))
    except Exception as e:
        result["error"] = str(e)

    return to_builtin(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "module": "dynamic_physics_input_inspection",
        "version": "0.1",
        "root": str(ROOT),
        "sources": {},
        "latest_files": {},
        "readiness": {},
    }

    for kind, folder in SOURCES.items():
        latest = pick_latest_file(folder)
        report["latest_files"][kind] = str(latest) if latest else None
        report["sources"][kind] = inspect_file(kind, latest)

    essential = ["current", "ssh", "sst", "chl"]
    optional = ["wave", "wind"]

    essential_ok = all(report["sources"][k].get("ok") for k in essential)
    optional_ok = {k: report["sources"][k].get("ok") for k in optional}

    detected = {}
    for kind, src in report["sources"].items():
        detected[kind] = src.get("variables_detected", {})

    current_ok = bool(
        detected.get("current", {}).get("current_u")
        and detected.get("current", {}).get("current_v")
    )
    ssh_ok = bool(detected.get("ssh", {}).get("ssh"))
    sst_ok = bool(detected.get("sst", {}).get("sst"))
    chl_ok = bool(detected.get("chl", {}).get("chl"))

    report["readiness"] = {
        "essential_files_ok": essential_ok,
        "current_u_vo_detected": current_ok,
        "ssh_detected": ssh_ok,
        "sst_detected": sst_ok,
        "chl_detected": chl_ok,
        "optional_files_ok": optional_ok,
        "ready_for_dynamic_physics_v01": bool(
            essential_ok and current_ok and ssh_ok and sst_ok and chl_ok
        ),
        "recommended_snapshot_logic": (
            "Use the latest date with current+ssh+sst+chl available; "
            "wave and wind can support safety/confidence when available."
        ),
    }

    out_file = out_dir / "dynamic_inputs_report.json"
    out_file.write_text(json.dumps(to_builtin(report), indent=2, ensure_ascii=False))

    print("=" * 78)
    print("NELAYA-AI Dynamic Physics Input Inspection")
    print("=" * 78)
    print(f"Saved: {out_file}")

    for kind, src in report["sources"].items():
        print("-" * 78)
        print(f"{kind.upper()}")
        print(f"file: {src.get('file')}")
        print(f"date: {src.get('date_from_filename')}")
        print(f"ok  : {src.get('ok')}")
        print(f"dims: {src.get('dims')}")
        print(f"vars: {src.get('data_vars')}")
        print(f"detected: {src.get('variables_detected')}")
        if src.get("error"):
            print(f"error: {src.get('error')}")

    print("=" * 78)
    print("READINESS")
    print(json.dumps(report["readiness"], indent=2, ensure_ascii=False))
    print("=" * 78)


if __name__ == "__main__":
    main()
