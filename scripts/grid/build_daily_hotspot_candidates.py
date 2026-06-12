#!/usr/bin/env python3
"""
NELAYA-AI Daily Grid Hotspot Candidate v0.1.0

Membaca calibrated daily grid v0.1.1 lalu menghitung hotspot spasial
berbasis tetangga queen adjacency 3x3 dan Getis-Ord Gi* z-score.

Input:
- data/grid/daily/grid_scoring_YYYY-MM-DD_calibrated_v011.csv

Output:
- data/grid/hotspots/grid_hotspot_YYYY-MM-DD_v010.csv
- data/grid/hotspots/grid_hotspot_YYYY-MM-DD_v010.geojson
- data/grid/hotspots/grid_hotspot_YYYY-MM-DD_v010_summary.json

Catatan:
Ini daily spatial hotspot candidate, belum persistence 7/14/30 hari.
Persistence baru kuat setelah archive beberapa hari tersedia.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd


def classify_hotspot(row):
    z = row.get("gi_star_zscore", np.nan)
    pct = row.get("operational_percentile_rank_v011", np.nan)
    op = row.get("operational_score_v011", np.nan)
    safety = row.get("safety_label_v011", "unknown")
    conf = row.get("overall_confidence_v011", 0)
    local_high = row.get("local_high_count_3x3", 0)

    if pd.isna(z) or pd.isna(pct) or pd.isna(op):
        return "unknown"

    if safety in ["unknown", "limited_data"]:
        if z >= 1.96 and pct <= 0.15:
            return "data_limited_hotspot_signal"
        return "data_limited"

    if safety == "unsafe":
        if z >= 1.96 and pct <= 0.15:
            return "ecological_signal_but_unsafe"
        return "unsafe"

    if z >= 2.58 and pct <= 0.05 and conf >= 0.85 and local_high >= 3:
        return "hotspot_core"

    if z >= 1.96 and pct <= 0.15 and conf >= 0.75 and local_high >= 2:
        return "hotspot_strong"

    if z >= 1.65 and pct <= 0.30 and conf >= 0.60:
        return "hotspot_candidate"

    if pct <= 0.15 and z < 1.65:
        return "high_score_isolated"

    return "non_hotspot"


def build_neighbor_stats(df):
    """
    Queen adjacency 3x3: cell sendiri + 8 tetangga.
    Hanya menghitung tetangga yang termasuk ocean cell aktif di dataframe.
    """

    key_to_idx = {
        (int(r.grid_i), int(r.grid_j)): idx
        for idx, r in df[["grid_i", "grid_j"]].iterrows()
    }

    x = df["operational_score_v011"].fillna(0).to_numpy(dtype=float)
    n_total = len(x)

    global_mean = float(np.mean(x))
    global_s = float(np.sqrt(np.mean(x * x) - global_mean * global_mean))

    if global_s == 0:
        global_s = np.nan

    gi_z = np.full(n_total, np.nan)
    local_sum = np.zeros(n_total)
    local_mean = np.zeros(n_total)
    local_count = np.zeros(n_total, dtype=int)
    local_max = np.zeros(n_total)
    local_high_count = np.zeros(n_total, dtype=int)
    local_core_count = np.zeros(n_total, dtype=int)

    pct = df["operational_percentile_rank_v011"].to_numpy(dtype=float)

    for idx, r in df.iterrows():
        i = int(r["grid_i"])
        j = int(r["grid_j"])

        neigh = []
        for dj in [-1, 0, 1]:
            for di in [-1, 0, 1]:
                k = key_to_idx.get((i + di, j + dj))
                if k is not None:
                    neigh.append(k)

        vals = x[neigh]
        m = len(vals)

        if m == 0:
            continue

        s = float(np.sum(vals))
        local_sum[idx] = s
        local_mean[idx] = float(np.mean(vals))
        local_count[idx] = m
        local_max[idx] = float(np.max(vals))

        local_high_count[idx] = int(np.sum(pct[neigh] <= 0.15))
        local_core_count[idx] = int(np.sum(pct[neigh] <= 0.05))

        # Getis-Ord Gi* z-score untuk binary weights.
        # w_j = 1 untuk tetangga 3x3 termasuk cell sendiri.
        sum_w = float(m)
        sum_w2 = float(m)

        denom_factor = (n_total * sum_w2 - sum_w * sum_w) / max(n_total - 1, 1)

        if global_s and not np.isnan(global_s) and denom_factor > 0:
            gi_z[idx] = (s - global_mean * sum_w) / (global_s * np.sqrt(denom_factor))

    df["local_count_3x3"] = local_count
    df["local_sum_operational_3x3"] = np.round(local_sum, 5)
    df["local_mean_operational_3x3"] = np.round(local_mean, 5)
    df["local_max_operational_3x3"] = np.round(local_max, 5)
    df["local_high_count_3x3"] = local_high_count
    df["local_core_count_3x3"] = local_core_count
    df["gi_star_zscore"] = np.round(gi_z, 4)

    return df, {
        "global_mean_operational": global_mean,
        "global_std_operational": global_s,
        "n_cells": n_total,
        "weighting": "binary queen adjacency 3x3 including self",
    }


def to_geojson(df, out_path):
    keep = df[df["hotspot_class"].isin([
        "hotspot_core",
        "hotspot_strong",
        "hotspot_candidate",
        "data_limited_hotspot_signal",
        "ecological_signal_but_unsafe",
        "high_score_isolated",
    ])].copy()

    keep = keep.sort_values(
        ["hotspot_rank_score", "operational_score_v011", "gi_star_zscore"],
        ascending=False,
    )

    features = []

    for _, r in keep.iterrows():
        x0 = float(r["lon_min"])
        x1 = float(r["lon_max"])
        y0 = float(r["lat_min"])
        y1 = float(r["lat_max"])

        props_cols = [
            "cell_id", "grid_i", "grid_j",
            "lon_center", "lat_center",
            "depth_m", "depth_class",
            "fgi_grid_score", "operational_score_v011",
            "operational_priority_label_v011",
            "safety_label_v011", "safety_risk_v011",
            "overall_confidence_v011",
            "local_mean_operational_3x3",
            "local_high_count_3x3",
            "local_core_count_3x3",
            "gi_star_zscore",
            "hotspot_class",
            "hotspot_rank_score",
            "rank_hotspot_v010",
        ]

        props = {}
        for col in props_cols:
            if col not in r:
                continue
            val = r[col]
            if pd.isna(val):
                val = None
            elif isinstance(val, np.integer):
                val = int(val)
            elif isinstance(val, np.floating):
                val = float(val)
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
        "name": "NELAYA-AI Daily Grid Hotspot Candidate v0.1.0",
        "features": features,
    }

    out_path.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    args = parser.parse_args()

    if args.date:
        date_str = args.date
        in_path = Path(f"data/grid/daily/grid_scoring_{date_str}_calibrated_v011.csv")
    else:
        files = sorted(Path("data/grid/daily").glob("grid_scoring_*_calibrated_v011.csv"))
        if not files:
            raise FileNotFoundError("Tidak ada calibrated file v0.1.1")
        in_path = files[-1]
        date_str = in_path.name.replace("grid_scoring_", "").replace("_calibrated_v011.csv", "")

    if not in_path.exists():
        raise FileNotFoundError(in_path)

    out_dir = Path("data/grid/hotspots")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(in_path)

    required = [
        "grid_i", "grid_j", "operational_score_v011",
        "operational_percentile_rank_v011",
        "safety_label_v011", "overall_confidence_v011",
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Kolom wajib tidak ada: {missing}")

    print("=== NELAYA-AI Daily Grid Hotspot Candidate v0.1.0 ===")
    print("input:", in_path)
    print("date :", date_str)
    print("rows :", len(df))

    df, stats = build_neighbor_stats(df)

    df["hotspot_class"] = df.apply(classify_hotspot, axis=1)

    # Rank score: gabungan skor operasional, z-score, local support, dan confidence.
    z_norm = ((df["gi_star_zscore"].fillna(0) + 3) / 6).clip(0, 1)
    local_support = (df["local_high_count_3x3"].fillna(0) / 9).clip(0, 1)

    df["hotspot_rank_score"] = (
        0.45 * df["operational_score_v011"].fillna(0)
        + 0.30 * z_norm
        + 0.15 * local_support
        + 0.10 * df["overall_confidence_v011"].fillna(0)
    ).round(5)

    priority_order = {
        "hotspot_core": 1,
        "hotspot_strong": 2,
        "hotspot_candidate": 3,
        "data_limited_hotspot_signal": 4,
        "ecological_signal_but_unsafe": 5,
        "high_score_isolated": 6,
        "data_limited": 7,
        "unsafe": 8,
        "non_hotspot": 9,
        "unknown": 10,
    }

    df["hotspot_class_order"] = df["hotspot_class"].map(priority_order).fillna(99).astype(int)

    df = df.sort_values(
        ["hotspot_class_order", "hotspot_rank_score", "operational_score_v011"],
        ascending=[True, False, False],
    ).copy()

    df["rank_hotspot_v010"] = range(1, len(df) + 1)

    df["module_hotspot"] = "nelaya_ai_grid_daily_hotspot_candidate"
    df["hotspot_version"] = "0.1.0-experimental"
    df["hotspot_generated_at_utc"] = datetime.now(timezone.utc).isoformat()

    out_csv = out_dir / f"grid_hotspot_{date_str}_v010.csv"
    out_geojson = out_dir / f"grid_hotspot_{date_str}_v010.geojson"
    out_summary = out_dir / f"grid_hotspot_{date_str}_v010_summary.json"

    df.to_csv(out_csv, index=False)
    to_geojson(df, out_geojson)

    top_cols = [
        "rank_hotspot_v010", "cell_id", "lon_center", "lat_center",
        "depth_m", "depth_class",
        "operational_score_v011",
        "operational_priority_label_v011",
        "safety_label_v011",
        "overall_confidence_v011",
        "local_mean_operational_3x3",
        "local_high_count_3x3",
        "local_core_count_3x3",
        "gi_star_zscore",
        "hotspot_class",
        "hotspot_rank_score",
    ]

    summary = {
        "module": "nelaya_ai_grid_daily_hotspot_candidate",
        "version": "0.1.0-experimental",
        "date": date_str,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(in_path),
        "output_csv": str(out_csv),
        "output_geojson": str(out_geojson),
        "ocean_cells": int(len(df)),
        "getis_ord_note": (
            "Gi* z-score computed using binary queen adjacency 3x3 including the cell itself. "
            "This is a daily spatial clustering signal, not a multi-day persistence result."
        ),
        "stats": stats,
        "hotspot_class_counts": df["hotspot_class"].value_counts(dropna=False).to_dict(),
        "top_hotspots": df[top_cols].head(30).to_dict(orient="records"),
        "scientific_note": (
            "Hotspot candidates indicate spatially clustered high operational suitability. "
            "They are not biomass estimates and require field validation."
        ),
    }

    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=== Output ===")
    print("CSV    :", out_csv)
    print("GeoJSON:", out_geojson)
    print("Summary:", out_summary)

    print()
    print("=== Hotspot class counts ===")
    print(df["hotspot_class"].value_counts(dropna=False).to_string())

    print()
    print("=== Top 20 hotspot candidates ===")
    print(df[top_cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
