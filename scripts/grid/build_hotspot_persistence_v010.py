#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pandas as pd


def parse_date_from_name(path: Path) -> str | None:
    name = path.name
    prefix = "grid_hotspot_zone_cells_"
    suffix = "_v012.geojson"
    if not name.startswith(prefix) or not name.endswith(suffix):
        return None
    return name.replace(prefix, "").replace(suffix, "")


def to_float(v, default=None):
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def persistence_label(days_available: int, days_present: int, ratio: float) -> str:
    if days_available < 3:
        return "insufficient_history"

    if days_present >= 5 and ratio >= 0.65:
        return "persistent_hotspot"

    if days_present >= 3 and ratio >= 0.45:
        return "recurrent_hotspot"

    if days_present >= 2:
        return "emerging_hotspot"

    return "single_day_signal"


def build_for_window(target_date: str, window: int):
    target_dt = datetime.fromisoformat(target_date).date()
    start_dt = target_dt - timedelta(days=window - 1)

    files = []
    for p in sorted(Path("data/grid/hotspots").glob("grid_hotspot_zone_cells_*_v012.geojson")):
        d = parse_date_from_name(p)
        if not d:
            continue
        dd = datetime.fromisoformat(d).date()
        if start_dt <= dd <= target_dt:
            files.append((d, p))

    if not files:
        raise FileNotFoundError(f"Tidak ada zone-cell GeoJSON v012 untuk window {window} hari sampai {target_date}")

    days_available = len(sorted(set(d for d, _ in files)))

    by_cell = {}

    for d, path in files:
        gj = json.loads(path.read_text(encoding="utf-8"))
        for feat in gj.get("features", []):
            props = feat.get("properties", {}) or {}
            cell_id = str(props.get("cell_id"))

            if not cell_id or cell_id == "None":
                continue

            item = by_cell.setdefault(cell_id, {
                "cell_id": cell_id,
                "dates_present": set(),
                "first_seen": d,
                "last_seen": d,
                "geometry": feat.get("geometry"),
                "lon_center": props.get("lon_center"),
                "lat_center": props.get("lat_center"),
                "depth_m": props.get("depth_m"),
                "depth_class": props.get("depth_class"),
                "zone_ids": set(),
                "zone_levels": set(),
                "scores": [],
                "confidences": [],
                "gi_scores": [],
                "safety_labels": set(),
            })

            item["dates_present"].add(d)
            item["first_seen"] = min(item["first_seen"], d)
            item["last_seen"] = max(item["last_seen"], d)
            item["geometry"] = feat.get("geometry") or item["geometry"]

            if props.get("zone_id"):
                item["zone_ids"].add(str(props.get("zone_id")))
            if props.get("zone_level"):
                item["zone_levels"].add(str(props.get("zone_level")))
            if props.get("safety_label_v011"):
                item["safety_labels"].add(str(props.get("safety_label_v011")))

            score = to_float(props.get("operational_score_v011"))
            conf = to_float(props.get("overall_confidence_v011"))
            gi = to_float(props.get("gi_star_zscore"))

            if score is not None:
                item["scores"].append(score)
            if conf is not None:
                item["confidences"].append(conf)
            if gi is not None:
                item["gi_scores"].append(gi)

    rows = []
    features = []

    for cell_id, item in by_cell.items():
        days_present = len(item["dates_present"])
        ratio = days_present / max(days_available, 1)
        label = persistence_label(days_available, days_present, ratio)

        mean_score = sum(item["scores"]) / len(item["scores"]) if item["scores"] else None
        mean_conf = sum(item["confidences"]) / len(item["confidences"]) if item["confidences"] else None
        mean_gi = sum(item["gi_scores"]) / len(item["gi_scores"]) if item["gi_scores"] else None
        max_gi = max(item["gi_scores"]) if item["gi_scores"] else None

        row = {
            "cell_id": cell_id,
            "target_date": target_date,
            "window_days": window,
            "days_available": days_available,
            "days_present": days_present,
            "persistence_ratio": round(ratio, 4),
            "persistence_label": label,
            "first_seen": item["first_seen"],
            "last_seen": item["last_seen"],
            "dates_present": ",".join(sorted(item["dates_present"])),
            "lon_center": item["lon_center"],
            "lat_center": item["lat_center"],
            "depth_m": item["depth_m"],
            "depth_class": item["depth_class"],
            "mean_operational_score": round(mean_score, 4) if mean_score is not None else None,
            "mean_overall_confidence": round(mean_conf, 4) if mean_conf is not None else None,
            "mean_gi_star_zscore": round(mean_gi, 4) if mean_gi is not None else None,
            "max_gi_star_zscore": round(max_gi, 4) if max_gi is not None else None,
            "zone_ids": ",".join(sorted(item["zone_ids"])),
            "zone_levels": ",".join(sorted(item["zone_levels"])),
            "safety_labels": ",".join(sorted(item["safety_labels"])),
            "version": "0.1.0-persistence",
        }

        rows.append(row)

        props = dict(row)
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": item["geometry"],
        })

    df = pd.DataFrame(rows)

    if len(df):
        order = {
            "persistent_hotspot": 1,
            "recurrent_hotspot": 2,
            "emerging_hotspot": 3,
            "single_day_signal": 4,
            "insufficient_history": 5,
        }
        df["persistence_order"] = df["persistence_label"].map(order).fillna(99).astype(int)
        df = df.sort_values(
            ["persistence_order", "days_present", "persistence_ratio", "mean_operational_score", "mean_gi_star_zscore"],
            ascending=[True, False, False, False, False],
        ).copy()
        df["rank_persistence"] = range(1, len(df) + 1)

    out_dir = Path("data/grid/persistence")
    out_dir.mkdir(parents=True, exist_ok=True)

    out_csv = out_dir / f"grid_hotspot_persistence_{target_date}_w{window}_v010.csv"
    out_geojson = out_dir / f"grid_hotspot_persistence_{target_date}_w{window}_v010.geojson"
    out_summary = out_dir / f"grid_hotspot_persistence_{target_date}_w{window}_v010_summary.json"

    df.to_csv(out_csv, index=False)

    geojson = {
        "type": "FeatureCollection",
        "name": f"NELAYA-AI Hotspot Persistence W{window} v0.1.0",
        "features": features,
    }
    out_geojson.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")

    label_counts = df["persistence_label"].value_counts().to_dict() if len(df) else {}

    if days_available < 3:
        quality_note = (
            f"Riwayat data baru {days_available} hari dalam window {window} hari. "
            "Persistence belum boleh dibaca sebagai pola menetap; ini masih sinyal awal."
        )
    else:
        quality_note = (
            f"Persistence dihitung dari {days_available} hari data tersedia dalam window {window} hari."
        )

    summary = {
        "module": "nelaya_ai_hotspot_persistence",
        "version": "0.1.0",
        "target_date": target_date,
        "window_days": window,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "date_range": {
            "start": str(start_dt),
            "end": str(target_dt),
        },
        "days_available": days_available,
        "input_files": [str(p) for _, p in files],
        "unique_cells": int(len(df)),
        "persistence_label_counts": label_counts,
        "top_cells": df.head(20).to_dict(orient="records") if len(df) else [],
        "output_csv": str(out_csv),
        "output_geojson": str(out_geojson),
        "quality_note": quality_note,
        "scientific_note": (
            "Persistence measures repeated appearance of operational hotspot nucleus cells across available daily outputs. "
            "It is not biomass persistence and must be interpreted with data quality flags."
        ),
    }

    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--windows", default="7,14,30")
    args = parser.parse_args()

    windows = [int(x.strip()) for x in args.windows.split(",") if x.strip()]
    all_summaries = []

    print("=== NELAYA-AI Hotspot Persistence v0.1.0 ===")
    print("target date:", args.date)
    print("windows    :", windows)
    print()

    for w in windows:
        summary = build_for_window(args.date, w)
        all_summaries.append(summary)

        print(f"=== W{w} ===")
        print(json.dumps({
            "window_days": w,
            "days_available": summary["days_available"],
            "unique_cells": summary["unique_cells"],
            "persistence_label_counts": summary["persistence_label_counts"],
            "quality_note": summary["quality_note"],
        }, ensure_ascii=False, indent=2))
        print()

    index = {
        "module": "nelaya_ai_hotspot_persistence_index",
        "version": "0.1.0",
        "target_date": args.date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "windows": all_summaries,
    }

    out_index = Path(f"data/grid/persistence/grid_hotspot_persistence_{args.date}_index_v010.json")
    out_index.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Index:", out_index)


if __name__ == "__main__":
    main()
