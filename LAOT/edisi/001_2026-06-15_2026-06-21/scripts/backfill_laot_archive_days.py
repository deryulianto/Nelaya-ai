#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path.home() / "NELAYA-AI-LAB"
EDISI = ROOT / "LAOT/edisi/001_2026-06-15_2026-06-21"

DAYS = ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18"]

def read_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_read_error": str(e), "_path": str(path)}

def pick_market_signal(market, *names):
    # Marketplace lama menyimpan data di signals/snapshot, bukan top-level.
    for container in ["signals", "snapshot"]:
        obj = market.get(container)
        if isinstance(obj, dict):
            for name in names:
                if name in obj and obj[name] is not None:
                    return obj[name]
    for name in names:
        if name in market and market[name] is not None:
            return market[name]
    return None

for day in DAYS:
    outdir = EDISI / "data" / day
    outdir.mkdir(parents=True, exist_ok=True)

    market_path = ROOT / f"data/marketplace_insights/{day}.json"
    grid_path = ROOT / f"data/grid/daily/grid_scoring_{day}_calibrated_v011_summary.json"
    zone_path = ROOT / f"data/grid/hotspots/grid_hotspot_zones_{day}_v012_summary.json"
    hotspot_path = ROOT / f"data/grid/hotspots/grid_hotspot_{day}_v010_summary.json"

    market = read_json(market_path)
    grid = read_json(grid_path)
    zone = read_json(zone_path)
    hotspot = read_json(hotspot_path)

    top_zone = None
    top_zones = zone.get("top_zones")
    if isinstance(top_zones, list) and top_zones:
        top_zone = top_zones[0]

    top_hotspot = None
    top_hotspots = hotspot.get("top_hotspots")
    if isinstance(top_hotspots, list) and top_hotspots:
        top_hotspot = top_hotspots[0]

    # Jika tidak ada aggregated zone, pakai top hotspot sebagai catatan indikatif,
    # tetapi jangan menyebutnya zona operasional.
    if top_zone:
        zone_payload = top_zone
        zones_count = zone.get("zones_count")
        zone_mode = "aggregated_zone"
    elif top_hotspot:
        zone_payload = {
            "zone_id": top_hotspot.get("cell_id"),
            "zone_level": top_hotspot.get("hotspot_class"),
            "cell_count": 1,
            "core_count": top_hotspot.get("local_core_count_3x3"),
            "strong_count": None,
            "lon_center": top_hotspot.get("lon_center"),
            "lat_center": top_hotspot.get("lat_center"),
            "depth_mean_m": top_hotspot.get("depth_m"),
            "dominant_depth_class": top_hotspot.get("depth_class"),
            "mean_operational_score": top_hotspot.get("operational_score_v011"),
            "mean_overall_confidence": top_hotspot.get("overall_confidence_v011"),
            "mean_gi_star_zscore": top_hotspot.get("gi_star_zscore"),
            "zone_score": top_hotspot.get("hotspot_rank_score"),
            "rank_zone": top_hotspot.get("rank_hotspot_v010"),
            "safety_counts_json": json.dumps({"note": top_hotspot.get("safety_label_v011")}, ensure_ascii=False),
        }
        zones_count = zone.get("zones_count", 0)
        zone_mode = "top_hotspot_cell_only"
    else:
        zone_payload = None
        zones_count = zone.get("zones_count")
        zone_mode = "no_zone_or_hotspot"

    row = {
        "capture_date": day,
        "insight_date": day,
        "source_mode": "archive_backfill",
        "source_note": "Backfill dari arsip grid/hotspot; bukan capture API harian LAOT.",
        "source_files": {
            "marketplace": str(market_path) if market_path.exists() else None,
            "grid_summary": str(grid_path) if grid_path.exists() else None,
            "zone_summary": str(zone_path) if zone_path.exists() else None,
            "hotspot_summary": str(hotspot_path) if hotspot_path.exists() else None,
        },

        "ocean_signals": {
            "sst": pick_market_signal(market, "sst", "sst_c", "sea_surface_temperature"),
            "chl": pick_market_signal(market, "chl", "chlorophyll", "chlorophyll_a"),
            "wave": pick_market_signal(market, "wave", "wave_height", "hs", "significant_wave_height"),
            "wind": pick_market_signal(market, "wind", "wind_speed"),
            "sst_class": None,
            "chl_class": None,
            "wave_class": None,
            "wind_class": None,
        },

        "fgi": {
            "core": None,
            "final": grid.get("score_mean_v011"),
            "final_0_100": round((grid.get("score_mean_v011") or 0) * 100),
            "confidence": grid.get("overall_confidence_mean_v011"),
            "iod_modifier": None,
            "local_flags": None,
            "reasons": ["Backfill memakai score_mean_v011 grid summary, bukan FGI publik harian."]
        },

        "grid": {
            "dashboard_level": "archive_backfill",
            "dashboard_headline": None,
            "quality_label": "archive_backfill_grid_summary",
            "quality_note": "Backfill dari arsip grid/hotspot; coverage dibaca dari summary.",
            "hotspot_status": "hotspot_detected" if top_zone or top_hotspot else "no_aggregated_zone",
            "zones_count": zones_count,
            "zone_level_counts": zone.get("zone_level_counts"),
            "top_zone": zone_payload,
            "zone_mode": zone_mode,
            "score_mean_v011": grid.get("score_mean_v011"),
            "overall_confidence_mean_v011": grid.get("overall_confidence_mean_v011"),
            "coverage": grid.get("coverage"),
        },

        "ocean_health": {
            "status_label": "Tidak tersedia dalam backfill arsip",
            "headline": None,
            "public_facts": [],
            "what_this_means": "Ocean Health tidak dibackfill dari arsip grid/hotspot.",
            "do_not_interpret_as": []
        }
    }

    (outdir / "laot_daily_row.json").write_text(
        json.dumps(row, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    top = row["grid"]["top_zone"] or {}
    note = f"""# LAOT Daily Note — {day}

## Status
- Mode: archive_backfill
- Catatan: backfill dari arsip grid/hotspot, bukan capture API harian LAOT.

## Grid Summary
- score_mean_v011: {row["grid"]["score_mean_v011"]}
- overall_confidence_mean_v011: {row["grid"]["overall_confidence_mean_v011"]}
- zones_count: {row["grid"]["zones_count"]}
- zone_mode: {row["grid"]["zone_mode"]}

## Top Zone / Hotspot
- ID: {top.get("zone_id", "-")}
- Level: {top.get("zone_level", "-")}
- Center: {top.get("lon_center", "-")} BT / {top.get("lat_center", "-")} LU
- Depth mean: {top.get("depth_mean_m", "-")}
- Depth class: {top.get("dominant_depth_class", "-")}
- Mean operational score: {top.get("mean_operational_score", "-")}
- Mean confidence: {top.get("mean_overall_confidence", "-")}

## Guardrail
Data ini dapat dipakai sebagai konteks mingguan LAOT, tetapi harus diberi label backfill arsip. Jangan dibaca sebagai capture harian penuh.
"""
    (outdir / "laot_daily_note.md").write_text(note, encoding="utf-8")

    print(f"OK backfill {day} -> {outdir/'laot_daily_row.json'}")
