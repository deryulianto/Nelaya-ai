#!/usr/bin/env python3
"""
NELAYA-AI Daily Grid Calibration Patch v0.1.1

Tujuan:
- Memperbaiki label high yang terlalu luas dengan percentile rank.
- Memisahkan FGI confidence dan safety confidence.
- Mencegah data safety kosong dianggap favorable.
- Membuat operational_score_v011 yang lebih konservatif.
- Menghasilkan top GeoJSON dan summary calibrated.

Input:
- data/grid/daily/grid_scoring_YYYY-MM-DD.csv

Output:
- data/grid/daily/grid_scoring_YYYY-MM-DD_calibrated_v011.csv
- data/grid/daily/grid_scoring_YYYY-MM-DD_calibrated_v011_top.geojson
- data/grid/daily/grid_scoring_YYYY-MM-DD_calibrated_v011_summary.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd


FGI_FEATURES = ["sst_c", "chl", "current_speed", "depth_m", "ssh"]
SAFETY_FEATURES = ["wave_height", "wind_speed", "current_speed"]


def percentile_label(p):
    if pd.isna(p):
        return "unknown"
    if p <= 0.05:
        return "very_high_priority"
    if p <= 0.15:
        return "high_priority"
    if p <= 0.30:
        return "moderate_high"
    if p <= 0.60:
        return "moderate"
    if p <= 0.85:
        return "low_moderate"
    return "low"


def classify_safety_v011(row):
    wave = row.get("wave_height", np.nan)
    wind = row.get("wind_speed", np.nan)
    cur = row.get("current_speed", np.nan)

    available = {
        "wave": not pd.isna(wave),
        "wind": not pd.isna(wind),
        "current": not pd.isna(cur),
    }

    n_avail = sum(available.values())
    missing = [k for k, ok in available.items() if not ok]

    risks = []

    if available["wave"]:
        if wave >= 2.5:
            risks.append("wave_high")
        elif wave >= 1.5:
            risks.append("wave_moderate")

    if available["wind"]:
        if wind >= 12.0:
            risks.append("wind_high")
        elif wind >= 8.0:
            risks.append("wind_moderate")

    if available["current"]:
        if cur >= 1.5:
            risks.append("current_strong")
        elif cur >= 0.9:
            risks.append("current_moderate")

    if any(r in risks for r in ["wave_high", "wind_high", "current_strong"]):
        label = "unsafe"
        factor = 0.20
    elif any(r in risks for r in ["wave_moderate", "wind_moderate", "current_moderate"]):
        label = "watch"
        factor = 0.70
    else:
        if n_avail == 3:
            label = "favorable"
            factor = 1.00
        elif n_avail >= 1:
            label = "limited_data"
            factor = 0.55
        else:
            label = "unknown"
            factor = 0.35

    safety_confidence = n_avail / 3.0

    if not risks:
        risks = ["none"]

    if missing:
        risks.extend([f"missing_{m}" for m in missing])

    return pd.Series({
        "safety_label_v011": label,
        "safety_factor_v011": round(factor, 3),
        "safety_confidence_v011": round(safety_confidence, 3),
        "safety_risk_v011": ",".join(risks),
        "safety_inputs_available": n_avail,
    })


def to_top_geojson(df, out_path, top_n=500):
    top = df.sort_values("operational_score_v011", ascending=False).head(top_n).copy()

    features = []
    for _, r in top.iterrows():
        x0 = float(r["lon_min"])
        x1 = float(r["lon_max"])
        y0 = float(r["lat_min"])
        y1 = float(r["lat_max"])

        props = {}
        keep_cols = [
            "cell_id", "grid_i", "grid_j",
            "lon_center", "lat_center",
            "depth_m", "depth_class",
            "sst_c", "chl", "current_speed", "salinity", "ssh",
            "wind_speed", "wave_height",
            "fgi_grid_score",
            "fgi_percentile_rank",
            "fgi_priority_label_v011",
            "safety_label_v011",
            "safety_risk_v011",
            "fgi_confidence_v011",
            "safety_confidence_v011",
            "overall_confidence_v011",
            "operational_score_v011",
            "operational_priority_label_v011",
            "rank_operational_v011",
        ]

        for col in keep_cols:
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
        "name": f"NELAYA-AI calibrated daily grid v0.1.1 top {top_n}",
        "features": features,
    }

    out_path.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--top-n", type=int, default=500)
    args = parser.parse_args()

    if args.date:
        in_path = Path(f"data/grid/daily/grid_scoring_{args.date}.csv")
        date_str = args.date
    else:
        files = sorted(Path("data/grid/daily").glob("grid_scoring_*.csv"))
        files = [p for p in files if "calibrated" not in p.name and p.name.endswith(".csv")]
        if not files:
            raise FileNotFoundError("Tidak ada file grid_scoring_YYYY-MM-DD.csv")
        in_path = files[-1]
        date_str = in_path.stem.replace("grid_scoring_", "")

    df = pd.read_csv(in_path)

    print("=== NELAYA-AI Calibration Patch v0.1.1 ===")
    print("input:", in_path)
    print("date :", date_str)
    print("rows :", len(df))

    # Confidence ekologis FGI: jumlah fitur utama yang tersedia.
    for col in FGI_FEATURES:
        if col not in df.columns:
            df[col] = np.nan

    df["fgi_inputs_available"] = df[FGI_FEATURES].notna().sum(axis=1)
    df["fgi_confidence_v011"] = (df["fgi_inputs_available"] / len(FGI_FEATURES)).round(3)

    # Patch safety.
    safety_patch = df.apply(classify_safety_v011, axis=1)
    df = pd.concat([df, safety_patch], axis=1)

    # Overall confidence: FGI lebih dominan, tapi safety tetap mempengaruhi.
    df["overall_confidence_v011"] = (
        0.65 * df["fgi_confidence_v011"] +
        0.35 * df["safety_confidence_v011"]
    ).round(3)

    # Penalti data safety: kalau safety input minim, jangan diberi skor operasional terlalu tinggi.
    safety_data_factor = (0.50 + 0.50 * df["safety_confidence_v011"]).clip(0.35, 1.0)

    df["operational_score_v011"] = (
        df["fgi_grid_score"].fillna(0)
        * df["fgi_confidence_v011"].fillna(0)
        * df["safety_factor_v011"].fillna(0.35)
        * safety_data_factor.fillna(0.35)
    ).round(4)

    # Percentile label untuk FGI raw dan operational calibrated.
    # Rank kecil = prioritas tinggi.
    df["fgi_percentile_rank"] = df["fgi_grid_score"].rank(
        ascending=False, method="first", pct=True
    ).round(5)
    df["fgi_priority_label_v011"] = df["fgi_percentile_rank"].apply(percentile_label)

    df["operational_percentile_rank_v011"] = df["operational_score_v011"].rank(
        ascending=False, method="first", pct=True
    ).round(5)
    df["operational_priority_label_v011"] = df["operational_percentile_rank_v011"].apply(percentile_label)

    df["rank_operational_v011"] = df["operational_score_v011"].rank(
        ascending=False, method="first"
    ).astype(int)

    df["calibration_version"] = "0.1.1-conservative"
    df["calibrated_at_utc"] = datetime.now(timezone.utc).isoformat()

    out_dir = Path("data/grid/daily")
    out_csv = out_dir / f"grid_scoring_{date_str}_calibrated_v011.csv"
    out_geojson = out_dir / f"grid_scoring_{date_str}_calibrated_v011_top.geojson"
    out_summary = out_dir / f"grid_scoring_{date_str}_calibrated_v011_summary.json"

    df.to_csv(out_csv, index=False)
    to_top_geojson(df, out_geojson, top_n=args.top_n)

    summary = {
        "module": "nelaya_ai_grid_daily_calibration",
        "version": "0.1.1-conservative",
        "date": date_str,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(in_path),
        "output_csv": str(out_csv),
        "ocean_cells": int(len(df)),
        "coverage": {
            c: {
                "non_null": int(df[c].notna().sum()) if c in df.columns else 0,
                "coverage_pct": round(float(df[c].notna().mean() * 100), 2) if c in df.columns else 0.0,
            }
            for c in ["sst_c", "chl", "current_speed", "salinity", "ssh", "wind_speed", "wave_height"]
        },
        "old_label_counts": df["fgi_grid_label"].value_counts(dropna=False).to_dict() if "fgi_grid_label" in df.columns else {},
        "fgi_priority_label_counts_v011": df["fgi_priority_label_v011"].value_counts(dropna=False).to_dict(),
        "safety_label_counts_v011": df["safety_label_v011"].value_counts(dropna=False).to_dict(),
        "operational_priority_label_counts_v011": df["operational_priority_label_v011"].value_counts(dropna=False).to_dict(),
        "score_mean_v011": float(np.nanmean(df["operational_score_v011"])),
        "overall_confidence_mean_v011": float(np.nanmean(df["overall_confidence_v011"])),
        "top_cells_v011": df.sort_values("operational_score_v011", ascending=False)[[
            "rank_operational_v011",
            "cell_id",
            "lon_center",
            "lat_center",
            "depth_m",
            "depth_class",
            "fgi_grid_score",
            "fgi_confidence_v011",
            "safety_label_v011",
            "safety_confidence_v011",
            "safety_risk_v011",
            "overall_confidence_v011",
            "operational_score_v011",
            "operational_priority_label_v011",
        ]].head(20).to_dict(orient="records"),
        "scientific_note": (
            "v0.1.1 applies conservative calibration. Missing safety data is not treated as favorable. "
            "Priority labels are percentile-based, not direct biomass estimates. "
            "Layer remains experimental and requires standardized field validation."
        )
    }

    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=== Output ===")
    print("CSV    :", out_csv)
    print("GeoJSON:", out_geojson)
    print("Summary:", out_summary)

    print()
    print("=== Safety v0.1.1 counts ===")
    print(df["safety_label_v011"].value_counts(dropna=False).to_string())

    print()
    print("=== Operational priority v0.1.1 counts ===")
    print(df["operational_priority_label_v011"].value_counts(dropna=False).to_string())

    print()
    print("=== Top 20 calibrated operational cells ===")
    cols = [
        "rank_operational_v011", "cell_id", "lon_center", "lat_center",
        "depth_m", "depth_class",
        "sst_c", "chl", "current_speed", "wind_speed", "wave_height",
        "fgi_grid_score", "fgi_confidence_v011",
        "safety_label_v011", "safety_confidence_v011",
        "overall_confidence_v011", "operational_score_v011",
        "operational_priority_label_v011",
        "safety_risk_v011",
    ]
    print(df.sort_values("operational_score_v011", ascending=False)[cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
