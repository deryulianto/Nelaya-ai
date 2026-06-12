#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone


def read_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    date_str = args.date
    scoring_path = Path(f"data/grid/daily/grid_scoring_{date_str}_summary.json")
    scoring = read_json(scoring_path)

    sources = (
        scoring.get("sources")
        or scoring.get("source_files")
        or scoring.get("input_files")
        or {}
    )

    audit = {}

    for key, path in sources.items():
        if path is None:
            status = "missing"
        else:
            path_text = str(path)
            if date_str in path_text:
                status = "exact_date"
            else:
                status = "fallback_or_mismatch"

        audit[key] = {
            "path": path,
            "target_date": date_str,
            "status": status,
        }

    counts = {}
    for item in audit.values():
        counts[item["status"]] = counts.get(item["status"], 0) + 1

    out = {
        "module": "nelaya_ai_grid_source_audit",
        "version": "0.1.0",
        "date": date_str,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scoring_summary": str(scoring_path),
        "source_status_counts": counts,
        "sources": audit,
        "scientific_note": (
            "This audit checks whether each source file path contains the target pipeline date. "
            "fallback_or_mismatch may be acceptable for forecast/analysis products, but must be visible for reproducibility."
        ),
    }

    out_path = Path(f"data/grid/grid_source_audit_{date_str}.json")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== Grid source audit created ===")
    print("output:", out_path)
    print(json.dumps({
        "date": date_str,
        "source_status_counts": counts,
        "sources": audit,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
