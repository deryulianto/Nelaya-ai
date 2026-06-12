#!/usr/bin/env python3
"""
NELAYA-AI Hotspot Zone Aggregator v0.1.2-operational-nucleus

Mengambil inti hotspot operasional:
- hotspot_core / hotspot_strong
- safety favorable
- confidence tinggi
- operational score cukup kuat
- adjacency 4-neighbor agar zona tidak melebar berlebihan

Output:
- data/grid/hotspots/grid_hotspot_zones_YYYY-MM-DD_v012.csv
- data/grid/hotspots/grid_hotspot_zones_YYYY-MM-DD_v012_summary.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import deque

import pandas as pd


def zone_level(core_count, strong_count, mean_score, mean_conf, cell_count):
    core_ratio = core_count / max(cell_count, 1)

    if cell_count >= 10 and core_count >= 5 and core_ratio >= 0.35 and mean_score >= 0.75 and mean_conf >= 0.90:
        return "operational_core_zone"

    if cell_count >= 5 and mean_score >= 0.65 and mean_conf >= 0.85:
        return "operational_strong_zone"

    return "operational_watch_zone"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--min-cells", type=int, default=3)
    parser.add_argument("--min-score", type=float, default=0.65)
    parser.add_argument("--min-confidence", type=float, default=0.85)
    args = parser.parse_args()

    if args.date:
        date_str = args.date
        in_path = Path(f"data/grid/hotspots/grid_hotspot_{date_str}_v010.csv")
    else:
        files = sorted(Path("data/grid/hotspots").glob("grid_hotspot_????-??-??_v010.csv"))
        if not files:
            raise FileNotFoundError("Belum ada grid_hotspot_YYYY-MM-DD_v010.csv")
        in_path = files[-1]
        date_str = in_path.name.replace("grid_hotspot_", "").replace("_v010.csv", "")

    df = pd.read_csv(in_path)

    hot = df[
        df["hotspot_class"].isin(["hotspot_core", "hotspot_strong"])
        & (df["safety_label_v011"] == "favorable")
        & (df["overall_confidence_v011"] >= args.min_confidence)
        & (df["operational_score_v011"] >= args.min_score)
    ].copy().reset_index(drop=True)

    print("=== NELAYA-AI Hotspot Zone Aggregator v0.1.2-operational-nucleus ===")
    print("input:", in_path)
    print("date :", date_str)
    print("selected operational nucleus cells:", len(hot))

    key_to_idx = {
        (int(r.grid_i), int(r.grid_j)): idx
        for idx, r in hot[["grid_i", "grid_j"]].iterrows()
    }

    visited = set()
    zones = []
    zone_no = 1

    # 4-neighbor / rook adjacency, bukan 8-neighbor.
    neighbor_steps = [(1, 0), (-1, 0), (0, 1), (0, -1)]

    for idx, _ in hot.iterrows():
        if idx in visited:
            continue

        q = deque([idx])
        visited.add(idx)
        members = []

        while q:
            cur = q.popleft()
            members.append(cur)

            ci = int(hot.loc[cur, "grid_i"])
            cj = int(hot.loc[cur, "grid_j"])

            for di, dj in neighbor_steps:
                nb = key_to_idx.get((ci + di, cj + dj))
                if nb is not None and nb not in visited:
                    visited.add(nb)
                    q.append(nb)

        part = hot.loc[members].copy()
        n = len(part)

        if n < args.min_cells:
            continue

        core_count = int((part["hotspot_class"] == "hotspot_core").sum())
        strong_count = int((part["hotspot_class"] == "hotspot_strong").sum())

        mean_score = float(part["operational_score_v011"].mean())
        max_score = float(part["operational_score_v011"].max())
        mean_conf = float(part["overall_confidence_v011"].mean())
        mean_gi = float(part["gi_star_zscore"].mean())
        max_gi = float(part["gi_star_zscore"].max())

        depth_mode = part["depth_class"].mode().iloc[0] if not part["depth_class"].mode().empty else "unknown"
        zlevel = zone_level(core_count, strong_count, mean_score, mean_conf, n)

        zone_score = (
            0.40 * mean_score
            + 0.25 * min(max_gi / 10.0, 1.0)
            + 0.20 * (core_count / max(n, 1))
            + 0.15 * mean_conf
        )

        zones.append({
            "zone_id": f"HZ{date_str.replace('-', '')}_N{zone_no:03d}",
            "date": date_str,
            "zone_level": zlevel,
            "cell_count": n,
            "core_count": core_count,
            "strong_count": strong_count,
            "lon_center": round(float(part["lon_center"].mean()), 6),
            "lat_center": round(float(part["lat_center"].mean()), 6),
            "lon_min": round(float(part["lon_min"].min()), 6),
            "lon_max": round(float(part["lon_max"].max()), 6),
            "lat_min": round(float(part["lat_min"].min()), 6),
            "lat_max": round(float(part["lat_max"].max()), 6),
            "depth_mean_m": round(float(part["depth_m"].mean()), 2),
            "depth_min_m": round(float(part["depth_m"].min()), 2),
            "depth_max_m": round(float(part["depth_m"].max()), 2),
            "dominant_depth_class": depth_mode,
            "mean_operational_score": round(mean_score, 4),
            "max_operational_score": round(max_score, 4),
            "mean_overall_confidence": round(mean_conf, 4),
            "mean_gi_star_zscore": round(mean_gi, 4),
            "max_gi_star_zscore": round(max_gi, 4),
            "safety_counts_json": json.dumps(part["safety_label_v011"].value_counts().to_dict(), ensure_ascii=False),
            "zone_score": round(zone_score, 5),
            "member_cell_ids": ",".join(part["cell_id"].astype(str).tolist()),
            "selection_rule": (
                "hotspot_core_or_strong + safety_favorable + confidence>=0.85 + operational_score>=0.65 + rook_4_neighbor"
            ),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "module": "nelaya_ai_hotspot_zone_aggregator",
            "version": "0.1.2-operational-nucleus",
        })

        zone_no += 1

    zones_df = pd.DataFrame(zones)

    order = {
        "operational_core_zone": 1,
        "operational_strong_zone": 2,
        "operational_watch_zone": 3,
    }

    if len(zones_df):
        zones_df["zone_level_order"] = zones_df["zone_level"].map(order).fillna(99).astype(int)
        zones_df = zones_df.sort_values(
            ["zone_level_order", "zone_score", "cell_count"],
            ascending=[True, False, False],
        ).copy()
        zones_df["rank_zone"] = range(1, len(zones_df) + 1)

    out_dir = Path("data/grid/hotspots")
    out_csv = out_dir / f"grid_hotspot_zones_{date_str}_v012.csv"
    out_summary = out_dir / f"grid_hotspot_zones_{date_str}_v012_summary.json"

    zones_df.to_csv(out_csv, index=False)

    top_zones = (
        zones_df.drop(columns=["member_cell_ids"], errors="ignore")
        .head(20)
        .to_dict(orient="records")
        if len(zones_df)
        else []
    )

    summary = {
        "module": "nelaya_ai_hotspot_zone_aggregator",
        "version": "0.1.2-operational-nucleus",
        "date": date_str,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(in_path),
        "output_csv": str(out_csv),
        "selected_cells": int(len(hot)),
        "zones_count": int(len(zones_df)),
        "zone_level_counts": zones_df["zone_level"].value_counts().to_dict() if len(zones_df) else {},
        "top_zones": top_zones,
        "scientific_note": (
            "v0.1.2 identifies compact operational hotspot nuclei using favorable safety, high confidence, "
            "and rook adjacency. These are operational suitability signals, not biomass estimates."
        ),
    }

    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=== Output ===")
    print("CSV    :", out_csv)
    print("Summary:", out_summary)

    print()
    print("=== Zone counts ===")
    print(zones_df["zone_level"].value_counts().to_string() if len(zones_df) else "No zones")

    print()
    print("=== Top zones ===")
    show = [
        "rank_zone", "zone_id", "zone_level", "cell_count",
        "core_count", "strong_count",
        "lon_center", "lat_center",
        "depth_mean_m", "dominant_depth_class",
        "mean_operational_score", "mean_overall_confidence",
        "mean_gi_star_zscore", "max_gi_star_zscore",
        "zone_score",
    ]
    if len(zones_df):
        print(zones_df[show].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
