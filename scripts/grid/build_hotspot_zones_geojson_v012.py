#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    args = parser.parse_args()

    if args.date:
        date_str = args.date
        in_csv = Path(f"data/grid/hotspots/grid_hotspot_zones_{date_str}_v012.csv")
    else:
        files = sorted(Path("data/grid/hotspots").glob("grid_hotspot_zones_*_v012.csv"))
        if not files:
            raise FileNotFoundError("Tidak ada file grid_hotspot_zones_*_v012.csv")
        in_csv = files[-1]
        date_str = in_csv.name.replace("grid_hotspot_zones_", "").replace("_v012.csv", "")

    df = pd.read_csv(in_csv)

    features = []

    for _, r in df.iterrows():
        x0 = float(r["lon_min"])
        x1 = float(r["lon_max"])
        y0 = float(r["lat_min"])
        y1 = float(r["lat_max"])

        props_cols = [
            "rank_zone",
            "zone_id",
            "date",
            "zone_level",
            "cell_count",
            "core_count",
            "strong_count",
            "lon_center",
            "lat_center",
            "depth_mean_m",
            "depth_min_m",
            "depth_max_m",
            "dominant_depth_class",
            "mean_operational_score",
            "max_operational_score",
            "mean_overall_confidence",
            "mean_gi_star_zscore",
            "max_gi_star_zscore",
            "zone_score",
            "safety_counts_json",
            "selection_rule",
            "version",
        ]

        props = {}
        for col in props_cols:
            if col not in r:
                continue
            val = r[col]
            if pd.isna(val):
                val = None
            elif hasattr(val, "item"):
                val = val.item()
            props[col] = val

        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [x0, y0],
                    [x1, y0],
                    [x1, y1],
                    [x0, y1],
                    [x0, y0],
                ]]
            }
        })

    geojson = {
        "type": "FeatureCollection",
        "name": "NELAYA-AI Operational Hotspot Nucleus Zones v0.1.2",
        "features": features,
    }

    out_path = Path(f"data/grid/hotspots/grid_hotspot_zones_{date_str}_v012.geojson")
    out_path.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")

    print("=== Zone GeoJSON created ===")
    print("input :", in_csv)
    print("output:", out_path)
    print("zones :", len(features))


if __name__ == "__main__":
    main()
