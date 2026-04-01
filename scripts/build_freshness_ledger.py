from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Jakarta")
ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw" / "aceh_simeulue"
OUT_PATH = ROOT / "data" / "derived" / "freshness" / "freshness_ledger.json"

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass
class LatestFile:
    date_value: date
    path: Path


VARIABLES = {
    "sst": {
        "dirs": ["sst_nrt"],
        "fresh_rule": "daily",
    },
    "chl": {
        "dirs": ["chl_nrt"],
        "fresh_rule": "daily",
    },
    "wind": {
        "dirs": ["wind_nrt"],
        "fresh_rule": "wind_daily_lagged",
    },
    "wave": {
        "dirs": ["wave_anfc"],
        "fresh_rule": "daily",
    },
    "ssh": {
        "dirs": ["ssh_anfc"],
        "fresh_rule": "daily",
    },
    "salinity": {
        "dirs": ["sal_anfc"],
        "fresh_rule": "weekly_like",
    },
}


def extract_date_from_name(name: str) -> date | None:
    m = DATE_RE.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def find_latest_file(base_dir: Path) -> LatestFile | None:
    if not base_dir.exists():
        return None

    latest: LatestFile | None = None
    for path in base_dir.rglob("*"):
        if not path.is_file():
            continue
        d = extract_date_from_name(path.name)
        if d is None:
            continue
        if latest is None or d > latest.date_value:
            latest = LatestFile(date_value=d, path=path)
    return latest


def classify_status(rule: str, age_days: int | None) -> str:
    if age_days is None:
        return "missing"

    if rule == "daily":
        if age_days == 0:
            return "today"
        if age_days <= 2:
            return "latest-valid"
        return "stale"

    if rule == "wind_daily_lagged":
        if age_days == 0:
            return "today"
        if age_days == 1:
            return "day-1-valid"
        if age_days <= 3:
            return "latest-valid"
        return "stale"

    if rule == "weekly_like":
        if age_days <= 9:
            return "latest-weekly-valid"
        return "stale"

    return "unknown"


def main() -> None:
    now = datetime.now(TZ)
    today = now.date()

    payload: dict = {
        "generated_at": now.isoformat(),
        "timezone": "Asia/Jakarta",
        "root": str(RAW_ROOT),
        "variables": {},
    }

    for var_name, cfg in VARIABLES.items():
        best: LatestFile | None = None

        for dir_name in cfg["dirs"]:
            found = find_latest_file(RAW_ROOT / dir_name)
            if found is None:
                continue
            if best is None or found.date_value > best.date_value:
                best = found

        if best is None:
            payload["variables"][var_name] = {
                "date": None,
                "age_days": None,
                "status": "missing",
                "path": None,
            }
            continue

        age_days = (today - best.date_value).days
        status = classify_status(cfg["fresh_rule"], age_days)

        payload["variables"][var_name] = {
            "date": best.date_value.isoformat(),
            "age_days": age_days,
            "status": status,
            "path": str(best.path),
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
