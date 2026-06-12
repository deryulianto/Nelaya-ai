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
        zones_csv = Path(f"data/grid/hotspots/grid_hotspot_zones_{date_str}_v012.csv")
        hotspot_csv = Path(f"data/grid/hotspots/grid_hotspot_{date_str}_v010.csv")
    else:
        files = sorted(Path("data/grid/hotspots").glob("grid_hotspot_zones_*_v012.csv"))
        if not files:
            raise FileNotFoundError("Tidak ada file zones v012")
        zones_csv = files[-1]
        date_str = zones_csv.name.replace("grid_hotspot_zones_", "").replace("_v012.csv", "")
        hotspot_csv = Path(f"data/grid/hotspots/grid_hotspot_{date_str}_v010.csv")

    zones = pd.read_csv(zones_csv)
    cells = pd.read_csv(hotspot_csv)

    features = []

    for _, z in zones.iterrows():
        member_ids = str(z.get("member_cell_ids", "")).split(",")
        member_ids = [x.strip() for x in member_ids if x.strip()]

        part = cells[cells["cell_id"].astype(str).isin(member_ids)].copy()

        for _, r in part.iterrows():
            x0 = float(r["lon_min"])
            x1 = float(r["lon_max"])
            y0 = float(r["lat_min"])
            y1 = float(r["lat_max"])

            props = {
                "zone_id": z["zone_id"],
                "zone_rank": int(z["rank_zone"]),
                "zone_level": z["zone_level"],
                "zone_score": float(z["zone_score"]),
                "cell_id": r["cell_id"],
                "cell_hotspot_class": r["hotspot_class"],
                "operational_score_v011": float(r["operational_score_v011"]),
                "safety_label_v011": r["safety_label_v011"],
                "overall_confidence_v011": float(r["overall_confidence_v011"]),
                "gi_star_zscore": float(r["gi_star_zscore"]),
                "depth_m": float(r["depth_m"]),
                "depth_class": r["depth_class"],
                "lon_center": float(r["lon_center"]),
                "lat_center": float(r["lat_center"]),
                "date": date_str,
                "version": "0.1.2-operational-nucleus-cell-layer",
            }

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
        "name": "NELAYA-AI Operational Hotspot Zone Cells v0.1.2",
        "features": features,
    }

    out = Path(f"data/grid/hotspots/grid_hotspot_zone_cells_{date_str}_v012.geojson")
    out.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")

    print("=== Zone cells GeoJSON created ===")
    print("zones :", len(zones))
    print("cells :", len(features))
    print("output:", out)


if __name__ == "__main__":
    main()
