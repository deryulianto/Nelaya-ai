#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sync current metrics from ocean_dynamic_physics_today.json into earth_signals_today.json.

Why:
- Some frontend cards read earth_signals_today.json.
- Physics-informed FGI reads ocean_dynamic_physics_today.json.
- This script keeps current metrics consistent across NELAYA-AI.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Optional


ROOT = Path(".")
EARTH_FILE = ROOT / "data" / "earth" / "earth_signals_today.json"
DYNAMIC_FILE = ROOT / "data" / "physics" / "ocean_dynamic_physics_today.json"

DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def safe_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def extract_date(text: Any) -> Optional[str]:
    if text is None:
        return None
    m = DATE_RE.search(str(text))
    return m.group(1) if m else None


def direction_components(speed: Optional[float], bearing_deg: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    """
    Bearing convention:
    0 = north, 90 = east, 180 = south, 270 = west.
    u = eastward, v = northward.
    """
    if speed is None or bearing_deg is None:
        return None, None

    rad = math.radians(bearing_deg)
    u = speed * math.sin(rad)
    v = speed * math.cos(rad)
    return u, v


def main() -> None:
    earth = read_json(EARTH_FILE)
    dyn = read_json(DYNAMIC_FILE)

    metrics = earth.setdefault("metrics", {})
    dyn_summary = dyn.get("summary_metrics", {})
    dyn_inputs = dyn.get("inputs", {})

    speed = safe_float(dyn_summary.get("mean_current_speed_ms"))
    bearing = safe_float(dyn_summary.get("mean_current_direction_deg"))
    label = dyn_summary.get("mean_current_direction_label")

    current_file = dyn_inputs.get("current")
    source_date = extract_date(current_file)

    u, v = direction_components(speed, bearing)

    metrics["current_ms"] = speed
    metrics["current_u_ms"] = u
    metrics["current_v_ms"] = v
    metrics["current_direction_deg"] = bearing
    metrics["current_direction_label"] = label
    metrics["current_source_date"] = source_date
    metrics["current_source_file"] = current_file
    metrics["current_source"] = "ocean_dynamic_physics_today"
    metrics["current_note"] = (
        "Synced from data/physics/ocean_dynamic_physics_today.json "
        "to keep dashboard current metrics consistent with FGI Physics Support."
    )

    # Optional aliases for frontend components that may use different field names.
    metrics["current_speed_ms"] = speed
    metrics["current_bearing_deg"] = bearing
    metrics["current_bearing_label"] = label

    write_json(EARTH_FILE, earth)

    print("=" * 78)
    print("Synced current metrics into earth_signals_today.json")
    print("=" * 78)
    print(f"current_ms              : {speed}")
    print(f"current_direction_deg   : {bearing}")
    print(f"current_direction_label : {label}")
    print(f"current_source_date     : {source_date}")
    print(f"current_source_file     : {current_file}")
    print(f"current_u_ms            : {u}")
    print(f"current_v_ms            : {v}")
    print("=" * 78)


if __name__ == "__main__":
    main()
