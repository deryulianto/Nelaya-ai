from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CUR_DIR = ROOT / "data/raw/aceh_simeulue/cur_nrt"
OUT = ROOT / "data/earth/current_today.json"


def _read_var(h: h5py.File, name: str) -> np.ndarray:
    if name not in h:
        raise KeyError(f"{name} not found. keys={list(h.keys())}")

    d = h[name]
    arr = np.array(d[...], dtype="float64")

    fill = d.attrs.get("_FillValue")
    if fill is not None:
        arr[arr == float(np.asarray(fill))] = np.nan

    missing = d.attrs.get("missing_value")
    if missing is not None:
        arr[arr == float(np.asarray(missing))] = np.nan

    scale = d.attrs.get("scale_factor", 1.0)
    offset = d.attrs.get("add_offset", 0.0)

    arr = arr * float(np.asarray(scale)) + float(np.asarray(offset))
    return arr


files = sorted(CUR_DIR.rglob("*.nc"))
if not files:
    raise SystemExit("No current NRT file found")

f = files[-1]

with h5py.File(f, "r") as h:
    u = _read_var(h, "uo")
    v = _read_var(h, "vo")

speed = np.sqrt(u**2 + v**2)

obj = {
    "ok": True,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "source_path": str(f),
    "current_ms": float(np.nanmean(speed)),
    "current_u_ms": float(np.nanmean(u)),
    "current_v_ms": float(np.nanmean(v)),
    "reader": "h5py_safe_v1",
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

print("[OK] wrote", OUT)
print(json.dumps(obj, indent=2))
