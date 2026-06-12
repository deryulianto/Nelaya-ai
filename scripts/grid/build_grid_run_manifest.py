#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone


def read_json(path: Path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def quality_label(coverage: dict, safety_counts: dict):
    chl_cov = coverage.get("chl", {}).get("coverage_pct", None)
    sst_cov = coverage.get("sst_c", {}).get("coverage_pct", None)
    wave_cov = coverage.get("wave_height", {}).get("coverage_pct", None)

    unknown_safety = int(safety_counts.get("unknown", 0) or 0)

    flags = []

    if chl_cov is not None and chl_cov < 5:
        flags.append("chl_very_limited")
    elif chl_cov is not None and chl_cov < 30:
        flags.append("chl_limited")

    if sst_cov is not None and sst_cov < 40:
        flags.append("sst_limited")

    if wave_cov is not None and wave_cov < 40:
        flags.append("wave_limited")

    if unknown_safety > 0:
        flags.append("safety_partly_unknown")

    if "chl_very_limited" in flags:
        label = "usable_with_strong_caution"
        public_note = (
            "Hotspot operasional dapat ditampilkan, tetapi dukungan CHL sangat terbatas. "
            "Interpretasi produktivitas harus sangat hati-hati."
        )
    elif flags:
        label = "usable_with_caution"
        public_note = (
            "Hotspot operasional dapat ditampilkan dengan catatan keterbatasan sebagian data."
        )
    else:
        label = "usable"
        public_note = (
            "Cakupan data utama memadai untuk bacaan operasional awal."
        )

    return label, flags, public_note


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    args = parser.parse_args()

    if args.date:
        date_str = args.date
    else:
        files = sorted(Path("data/grid/daily").glob("grid_scoring_*_calibrated_v011_summary.json"))
        if not files:
            raise FileNotFoundError("Tidak ada scoring summary")
        date_str = files[-1].name.replace("grid_scoring_", "").replace("_calibrated_v011_summary.json", "")

    scoring_path = Path(f"data/grid/daily/grid_scoring_{date_str}_calibrated_v011_summary.json")
    hotspot_path = Path(f"data/grid/hotspots/grid_hotspot_{date_str}_v010_summary.json")
    zones_path = Path(f"data/grid/hotspots/grid_hotspot_zones_{date_str}_v012_summary.json")

    scoring = read_json(scoring_path)
    hotspot = read_json(hotspot_path)
    zones = read_json(zones_path)

    coverage = scoring.get("coverage", {}) or {}
    safety_counts = scoring.get("safety_label_counts_v011", {}) or {}

    q_label, flags, public_note = quality_label(coverage, safety_counts)

    manifest = {
        "module": "nelaya_ai_grid_run_manifest",
        "version": "0.1.0",
        "date": date_str,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "quality_label": q_label,
        "quality_flags": flags,
        "public_quality_note": public_note,
        "scoring": {
            "path": str(scoring_path),
            "coverage": coverage,
            "safety_counts": safety_counts,
            "score_mean_v011": scoring.get("score_mean_v011"),
            "overall_confidence_mean_v011": scoring.get("overall_confidence_mean_v011"),
        },
        "hotspot": {
            "path": str(hotspot_path),
            "hotspot_class_counts": hotspot.get("hotspot_class_counts", {}),
        },
        "zones": {
            "path": str(zones_path),
            "version": zones.get("version"),
            "zones_count": zones.get("zones_count"),
            "zone_level_counts": zones.get("zone_level_counts", {}),
            "top_zones": zones.get("top_zones", [])[:5],
        },
        "scientific_note": (
            "Grid hotspot output is operational suitability intelligence, not fish biomass estimation. "
            "Quality flags must be shown together with public readings."
        ),
    }

    out = Path(f"data/grid/grid_run_manifest_{date_str}.json")
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== Grid run manifest created ===")
    print("output:", out)
    print(json.dumps({
        "date": date_str,
        "quality_label": q_label,
        "quality_flags": flags,
        "zones_count": manifest["zones"]["zones_count"],
        "zone_level_counts": manifest["zones"]["zone_level_counts"],
        "public_quality_note": public_note,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
