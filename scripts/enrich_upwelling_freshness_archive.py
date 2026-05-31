#!/usr/bin/env python3
"""
Enrich Upwelling Watch with data freshness metadata and archive daily outputs.

This script does NOT change the UPI algorithm.
It only adds:
- data_status
- staleness_days / staleness_hours
- input_freshness
- archive copies
- audit file
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parents[1]
UP_DIR = ROOT / "data" / "upwelling"
ARCHIVE_DIR = UP_DIR / "archive"
AUDIT_FILE = UP_DIR / "upwelling_data_health_today.json"

WATCH_FILE = UP_DIR / "upwelling_watch_today.json"

FILES_TO_ARCHIVE = {
    "watch": UP_DIR / "upwelling_watch_today.json",
    "candidates_json": UP_DIR / "upwelling_candidates_today.json",
    "candidates_geojson": UP_DIR / "upwelling_candidates_today.geojson",
    "buffers_geojson": UP_DIR / "upwelling_candidate_buffers_today.geojson",
    "clusters_json": UP_DIR / "upwelling_candidate_clusters_today.json",
    "clusters_geojson": UP_DIR / "upwelling_candidate_clusters_today.geojson",
    "temporal_memory": UP_DIR / "upwelling_temporal_memory_today.json",
    "cluster_history": UP_DIR / "upwelling_cluster_history.json",
}


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def extract_date_from_path(path_text: Optional[str]) -> Optional[str]:
    if not path_text:
        return None
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", path_text)
    return m.group(1) if m else None


def date_status(age_days: Optional[int]) -> str:
    if age_days is None:
        return "unknown"
    if age_days <= 2:
        return "fresh"
    if age_days <= 5:
        return "lagging"
    return "stale"


def summarize_inputs(data_files: Dict[str, str], generated_date) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    for key, path_text in data_files.items():
        date_text = extract_date_from_path(path_text)
        age_days = None

        if date_text and generated_date:
            try:
                input_date = datetime.fromisoformat(date_text).date()
                age_days = max(0, (generated_date - input_date).days)
            except Exception:
                age_days = None

        out[key] = {
            "path": path_text,
            "date": date_text,
            "age_days_from_generated_at": age_days,
            "status": date_status(age_days),
        }

    counts: Dict[str, int] = {}
    for item in out.values():
        counts[item["status"]] = counts.get(item["status"], 0) + 1

    return {
        "items": out,
        "summary": counts,
    }


def main() -> None:
    now = datetime.now(timezone.utc).astimezone()

    data = read_json(WATCH_FILE)

    generated_at = parse_dt(data.get("generated_at"))
    if generated_at is None:
        generated_at = datetime.fromtimestamp(WATCH_FILE.stat().st_mtime, tz=now.tzinfo)

    staleness_hours = max(0.0, (now - generated_at).total_seconds() / 3600.0)
    staleness_days = round(staleness_hours / 24.0, 2)

    available = bool(data.get("available", True))

    if not available:
        data_status = "fallback"
    elif staleness_hours <= 36:
        data_status = "fresh"
    elif staleness_hours <= 72:
        data_status = "lagging"
    else:
        data_status = "stale"

    generated_date = generated_at.date()
    date_key = generated_date.isoformat()

    data_files_used = data.get("data_files_used") or {}
    input_freshness = summarize_inputs(data_files_used, generated_date)

    health = {
        "module": "upwelling_data_health",
        "status": data_status,
        "checked_at": now.isoformat(),
        "generated_at": generated_at.isoformat(),
        "staleness_hours": round(staleness_hours, 2),
        "staleness_days": staleness_days,
        "input_freshness": input_freshness,
        "note": (
            "Freshness status is an operational audit layer. "
            "It does not change the UPI algorithm or scientific interpretation."
        ),
    }

    data["data_status"] = data_status
    data["staleness_hours"] = round(staleness_hours, 2)
    data["staleness_days"] = staleness_days
    data["input_freshness"] = input_freshness
    data["data_health"] = health

    write_json(WATCH_FILE, data)
    write_json(AUDIT_FILE, health)

    day_archive = ARCHIVE_DIR / date_key
    day_archive.mkdir(parents=True, exist_ok=True)

    archived = {}
    for label, src in FILES_TO_ARCHIVE.items():
        if not src.exists():
            archived[label] = None
            continue

        suffix = "".join(src.suffixes)
        dst = day_archive / f"{src.stem}_{date_key}{suffix}"
        shutil.copy2(src, dst)
        archived[label] = str(dst.relative_to(ROOT))

    health["archive"] = {
        "date": date_key,
        "directory": str(day_archive.relative_to(ROOT)),
        "files": archived,
    }
    write_json(AUDIT_FILE, health)

    print("=== Upwelling data health ===")
    print("status:", data_status)
    print("generated_at:", generated_at.isoformat())
    print("staleness_hours:", round(staleness_hours, 2))
    print("staleness_days:", staleness_days)
    print("archive:", day_archive.relative_to(ROOT))
    print("input_summary:", input_freshness["summary"])


if __name__ == "__main__":
    main()
