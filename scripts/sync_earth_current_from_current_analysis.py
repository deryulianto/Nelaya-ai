#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import math
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("/home/coastalai/NELAYA-AI-LAB")

EARTH_FILE = ROOT / "data" / "earth" / "earth_signals_today.json"
CURRENT_FILE = ROOT / "data" / "physics" / "current_analysis_today.json"


def read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def safe_float(x, default=None):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def norm_label(label):
    if not label:
        return None

    s = str(label).strip().lower().replace("-", "_").replace(" ", "_")

    # normalisasi istilah lama
    if s in {"barat_utara", "baratlaut"}:
        return "barat_laut"

    if s in {"barat_selatan", "baratdaya"}:
        return "barat_daya"

    return s


def main():
    earth = read_json(EARTH_FILE)
    current = read_json(CURRENT_FILE)

    metrics = earth.setdefault("metrics", {})

    speed_stats = current.get("speed_stats") or {}
    hotspot = current.get("hotspot") or {}

    snapshot_date = (
        current.get("snapshot_date")
        or current.get("date")
        or current.get("latest_available_date")
    )

    mean_speed = safe_float(
        speed_stats.get("mean")
        or current.get("mean_speed_ms")
        or current.get("current_ms")
    )

    max_speed = safe_float(speed_stats.get("max"))
    p75_speed = safe_float(speed_stats.get("p75"))

    direction_label = norm_label(
        current.get("dominant_direction_label")
        or current.get("current_direction_label")
        or current.get("direction_label")
    )

    direction_deg = safe_float(
        current.get("dominant_direction_deg")
        or current.get("current_direction_deg")
        or current.get("direction_deg")
    )

    source_file = (
        current.get("source_file")
        or current.get("input_file")
        or current.get("file")
        or f"data/raw/aceh_simeulue/cur_nrt/{snapshot_date}.nc"
    )

    metrics["current_ms"] = mean_speed
    metrics["current_max_ms"] = max_speed
    metrics["current_p75_ms"] = p75_speed
    metrics["current_direction_label"] = direction_label
    metrics["current_direction_deg"] = direction_deg
    metrics["current_source_date"] = snapshot_date
    metrics["current_source_file"] = source_file
    metrics["current_source"] = "current_analysis_today"

    # tambahan agar UI bisa tahu ini sudah disinkronkan
    metrics["current_synced_at"] = datetime.now(ZoneInfo("Asia/Jakarta")).isoformat()

    # backup dulu
    backup = EARTH_FILE.with_suffix(".json.bak_current_analysis_sync")
    shutil.copy2(EARTH_FILE, backup)

    EARTH_FILE.write_text(
        json.dumps(earth, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=" * 78)
    print("Synced earth current metrics from current_analysis_today.json")
    print("=" * 78)
    print(f"current_ms              : {mean_speed}")
    print(f"current_max_ms          : {max_speed}")
    print(f"current_p75_ms          : {p75_speed}")
    print(f"current_direction_label : {direction_label}")
    print(f"current_direction_deg   : {direction_deg}")
    print(f"current_source_date     : {snapshot_date}")
    print(f"current_source          : current_analysis_today")
    print(f"backup                  : {backup}")
    print("=" * 78)


if __name__ == "__main__":
    main()
