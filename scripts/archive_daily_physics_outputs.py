#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NELAYA-AI Archive Daily Physics Outputs

Purpose:
- Archive daily outputs from the Physics-informed FGI pipeline.
- Build a history folder for FGI v0.7 temporal memory.

Default archive path:
  data/physics/history/YYYY/MM/DD/

Archived files:
  - fgi_physics_support_today.json
  - fgi_physics_support_today.nc
  - fgi_physics_support_preview.geojson
  - ocean_dynamic_physics_today.json
  - ocean_dynamic_physics_today.nc
  - ocean_dynamic_front_preview.geojson
  - dynamic_inputs_report.json
  - bathymetry_features_summary.json
  - bathymetry_shelfbreak_preview.geojson

Also writes:
  - manifest.json
  - updates data/physics/history/index.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


ROOT = Path(".")
PHYSICS_DIR = ROOT / "data" / "physics"
HISTORY_DIR = PHYSICS_DIR / "history"

DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


FILES_TO_ARCHIVE = [
    "fgi_physics_support_today.json",
    "fgi_physics_support_today.nc",
    "fgi_physics_support_preview.geojson",
    "ocean_dynamic_physics_today.json",
    "ocean_dynamic_physics_today.nc",
    "ocean_dynamic_front_preview.geojson",
    "dynamic_inputs_report.json",
    "bathymetry_features_summary.json",
    "bathymetry_shelfbreak_preview.geojson",
]


def to_builtin(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_builtin(v) for v in obj]
    if isinstance(obj, tuple):
        return [to_builtin(v) for v in obj]
    if isinstance(obj, (int, str, bool)) or obj is None:
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return str(obj)


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def extract_dates_from_paths(obj: Any) -> List[str]:
    text = json.dumps(obj, ensure_ascii=False)
    return sorted(set(DATE_RE.findall(text)))


def today_jakarta() -> str:
    return datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d")


def get_archive_date(cli_date: Optional[str], fgi_summary: Dict[str, Any]) -> str:
    if cli_date:
        return cli_date

    # Prefer run date, not source data date, because this is a daily product archive.
    # Source dates are still stored in manifest.
    return today_jakarta()


def best_cell_from_summary(summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    top = (
        summary.get("top_cells", {})
        .get("fgi_physics_support_confidence_adjusted", [])
    )
    if isinstance(top, list) and top:
        return top[0]
    return None


def update_index(index_file: Path, entry: Dict[str, Any]) -> None:
    index_file.parent.mkdir(parents=True, exist_ok=True)

    if index_file.exists():
        try:
            index = json.loads(index_file.read_text(encoding="utf-8"))
        except Exception:
            index = {"entries": []}
    else:
        index = {"entries": []}

    entries = index.get("entries", [])
    entries = [e for e in entries if e.get("archive_date") != entry.get("archive_date")]
    entries.append(entry)
    entries = sorted(entries, key=lambda e: e.get("archive_date", ""))

    index = {
        "module": "nelaya_ai_physics_history_index",
        "updated_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "count": len(entries),
        "entries": entries,
    }

    index_file.write_text(json.dumps(to_builtin(index), indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Archive date YYYY-MM-DD. Default: today Asia/Jakarta.")
    parser.add_argument("--root", default=".", help="NELAYA-AI-LAB root.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing archive files.")
    parser.add_argument("--no-nc", action="store_true", help="Skip NetCDF files.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    physics_dir = root / "data" / "physics"
    history_dir = physics_dir / "history"

    fgi_summary_path = physics_dir / "fgi_physics_support_today.json"
    dynamic_summary_path = physics_dir / "ocean_dynamic_physics_today.json"
    input_report_path = physics_dir / "dynamic_inputs_report.json"

    if not fgi_summary_path.exists():
        raise SystemExit(f"Missing required file: {fgi_summary_path}")

    fgi_summary = read_json(fgi_summary_path)
    dynamic_summary = read_json(dynamic_summary_path)
    input_report = read_json(input_report_path)

    archive_date = get_archive_date(args.date, fgi_summary)
    year, month, day = archive_date.split("-")

    archive_dir = history_dir / year / month / day
    archive_dir.mkdir(parents=True, exist_ok=True)

    copied: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for name in FILES_TO_ARCHIVE:
        if args.no_nc and name.endswith(".nc"):
            skipped.append({"file": name, "reason": "no_nc"})
            continue

        src = physics_dir / name
        dst = archive_dir / name

        if not src.exists():
            skipped.append({"file": name, "reason": "missing"})
            continue

        if dst.exists() and not args.overwrite:
            skipped.append({"file": name, "reason": "exists"})
            continue

        shutil.copy2(src, dst)
        copied.append(
            {
                "file": name,
                "src": str(src),
                "dst": str(dst),
                "bytes": dst.stat().st_size,
            }
        )

    source_dates = sorted(
        set(
            extract_dates_from_paths(fgi_summary)
            + extract_dates_from_paths(dynamic_summary)
            + extract_dates_from_paths(input_report)
        )
    )

    best_cell = best_cell_from_summary(fgi_summary)

    manifest = {
        "module": "nelaya_ai_daily_physics_archive",
        "version": "0.1",
        "archive_date": archive_date,
        "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "archive_dir": str(archive_dir),
        "source_dates_detected": source_dates,
        "species_group": fgi_summary.get("species_group"),
        "fgi_version": fgi_summary.get("version"),
        "status": fgi_summary.get("status"),
        "summary_metrics": fgi_summary.get("summary_metrics", {}),
        "best_cell": best_cell,
        "copied": copied,
        "skipped": skipped,
    }

    manifest_file = archive_dir / "manifest.json"
    manifest_file.write_text(json.dumps(to_builtin(manifest), indent=2, ensure_ascii=False), encoding="utf-8")

    index_entry = {
        "archive_date": archive_date,
        "archive_dir": str(archive_dir),
        "manifest": str(manifest_file),
        "species_group": fgi_summary.get("species_group"),
        "fgi_version": fgi_summary.get("version"),
        "status": fgi_summary.get("status"),
        "geojson_point_count": (
            fgi_summary.get("outputs", {})
            .get("geojson", {})
            .get("point_count")
        ),
        "max_confidence_adjusted_score": (
            fgi_summary.get("summary_metrics", {})
            .get("max_confidence_adjusted_score")
        ),
        "best_cell": best_cell,
    }

    update_index(history_dir / "index.json", index_entry)

    print("=" * 78)
    print("NELAYA-AI Daily Physics Archive")
    print("=" * 78)
    print(f"Archive date : {archive_date}")
    print(f"Archive dir  : {archive_dir}")
    print(f"Manifest     : {manifest_file}")
    print(f"Copied       : {len(copied)}")
    print(f"Skipped      : {len(skipped)}")
    print("")
    print("Best cell:")
    print(json.dumps(to_builtin(best_cell), indent=2, ensure_ascii=False))
    print("")
    print("Source dates detected:")
    print(json.dumps(source_dates, indent=2, ensure_ascii=False))
    print("=" * 78)


if __name__ == "__main__":
    main()
