#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "earth": "data/earth/earth_signals_today.json",
    "dynamic": "data/physics/ocean_dynamic_physics_today.json",
    "temporal": "data/physics/fgi_temporal_memory_today.json",
    "bathy": "data/physics/bathymetry_features_summary.json",
}


def read_json(path):
    p = ROOT / path
    if not p.exists():
        print(f"\n=== {path} NOT FOUND ===")
        return None
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def show_value(name, value):
    print(f"\n=== {name} ===")
    print(json.dumps(value, ensure_ascii=False, indent=2)[:5000])


def main():
    earth = read_json(FILES["earth"])
    dynamic = read_json(FILES["dynamic"])
    temporal = read_json(FILES["temporal"])
    bathy = read_json(FILES["bathy"])

    if earth:
        show_value("earth.metrics.sst", earth.get("metrics", {}).get("sst"))
        show_value("earth.metrics.chl", earth.get("metrics", {}).get("chl"))
        show_value("earth.metrics.fgi", earth.get("metrics", {}).get("fgi"))
        show_value("earth.metrics.fgi_current_aware", earth.get("metrics", {}).get("fgi_current_aware"))
        show_value("earth.metrics.ssh", earth.get("metrics", {}).get("ssh"))

    if dynamic:
        show_value("dynamic top keys", list(dynamic.keys()))
        show_value("dynamic summary", dynamic.get("summary"))
        show_value("dynamic metrics", dynamic.get("metrics"))

    if temporal:
        show_value("temporal top keys", list(temporal.keys()))
        show_value("temporal summary", temporal.get("summary"))

    if bathy:
        show_value("bathy top keys", list(bathy.keys()))
        show_value("bathy summary", bathy.get("summary"))
        show_value("bathy stats", bathy.get("stats"))


if __name__ == "__main__":
    main()
