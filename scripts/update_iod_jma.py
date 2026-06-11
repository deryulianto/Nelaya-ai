#!/usr/bin/env python3
"""
Update Indian Ocean Dipole (IOD/DMI) context for NELAYA-AI.

Source:
JMA Tokyo Climate Center DMI monthly SST anomaly, base period 1991-2020.

Output:
  data/regional/iod/latest_iod.json
  data/regional/iod/archive/iod_YYYY-MM.json
"""

from __future__ import annotations

import argparse
import calendar
import json
from dataclasses import dataclass
from datetime import datetime, timezone, date
from pathlib import Path
from urllib.request import Request, urlopen

JMA_DMI_URL = (
    "https://ds.data.jma.go.jp/tcc/tcc/products/elnino/index/"
    "sstindex/base_period_9120/DMI/anomaly"
)

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
MISSING_SENTINEL = 90.0


@dataclass(frozen=True)
class DmiRecord:
    year: int
    month: int
    value: float

    @property
    def period(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def source_date(self) -> str:
        last_day = calendar.monthrange(self.year, self.month)[1]
        return f"{self.year:04d}-{self.month:02d}-{last_day:02d}"


def fetch_text(url: str, timeout: int = 30) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "NELAYA-AI/1.0 (+https://nelaya-ai.com; climate-index-updater)",
            "Accept": "text/plain,text/*,*/*",
        },
    )
    with urlopen(req, timeout=timeout) as res:
        return res.read().decode("utf-8", errors="replace")


def parse_jma_dmi_table(text: str) -> list[DmiRecord]:
    tokens = text.replace("\n", " ").split()
    if len(tokens) < 13:
        raise ValueError("JMA DMI table is too short or unreadable")

    month_headers = [t.upper() for t in tokens[:12]]
    if month_headers != MONTHS:
        raise ValueError(f"Unexpected JMA DMI month header: {month_headers}")

    records: list[DmiRecord] = []
    idx = 12

    while idx < len(tokens):
        year_token = tokens[idx]
        idx += 1

        try:
            year = int(year_token)
        except ValueError as exc:
            raise ValueError(f"Expected year token, got {year_token!r}") from exc

        values = tokens[idx : idx + 12]
        if len(values) < 12:
            break
        idx += 12

        for month, raw in enumerate(values, start=1):
            try:
                value = float(raw)
            except ValueError:
                continue

            if abs(value) >= MISSING_SENTINEL:
                continue

            records.append(DmiRecord(year=year, month=month, value=value))

    if not records:
        raise ValueError("No valid DMI records found in JMA table")

    return records


def classify_iod(dmi: float) -> str:
    if dmi >= 0.4:
        return "positive"
    if dmi <= -0.4:
        return "negative"
    return "neutral"


def freshness_label(staleness_days: int) -> str:
    # IOD/DMI adalah konteks iklim bulanan, bukan field oseanografi harian.
    if staleness_days <= 45:
        return "fresh_monthly"
    if staleness_days <= 75:
        return "late_monthly"
    return "stale"


def narrative(status: str, dmi: float, period: str, freshness: str) -> str:
    status_id = {
        "positive": "IOD positif",
        "negative": "IOD negatif",
        "neutral": "IOD netral",
    }.get(status, "IOD belum jelas")

    freshness_id = {
        "fresh_monthly": "Data masih layak dibaca sebagai konteks bulanan.",
        "late_monthly": "Data mulai terlambat; gunakan sebagai konteks regional dengan kehati-hatian.",
        "stale": "Data sudah terlalu lama; jangan gunakan sebagai pengubah aktif FGI sampai diperbarui.",
    }.get(freshness, "Kesegaran data belum diketahui.")

    return (
        f"{status_id} pada periode {period} dengan DMI {dmi:.2f} °C. "
        "IOD dibaca sebagai konteks iklim regional Samudra Hindia, bukan prediksi harian lokal Aceh. "
        f"{freshness_id}"
    )


def build_payload(record: DmiRecord, source_url: str) -> dict:
    now = datetime.now(timezone.utc)
    source_dt = date.fromisoformat(record.source_date)
    staleness_days = (now.date() - source_dt).days
    status = classify_iod(record.value)
    freshness = freshness_label(staleness_days)

    return {
        "module": "regional_climate_iod",
        "version": "1.0.0",
        "status": status,
        "dmi": round(record.value, 2),
        "date": record.period,
        "source_date": record.source_date,
        "updated_at": now.isoformat(),
        "source": "JMA Tokyo Climate Center DMI monthly SST anomaly, base period 1991-2020",
        "source_url": source_url,
        "cadence": "monthly",
        "staleness_days": staleness_days,
        "freshness": freshness,
        "thresholds": {
            "positive_iod_min_dmi_c": 0.4,
            "negative_iod_max_dmi_c": -0.4,
            "neutral_range_dmi_c": "-0.4 < DMI < 0.4",
        },
        "use_in_fgi_modifier": freshness != "stale",
        "narrative": narrative(status, record.value, record.period, freshness),
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=JMA_DMI_URL)
    parser.add_argument("--out", default="data/regional/iod/latest_iod.json")
    parser.add_argument("--archive-dir", default="data/regional/iod/archive")
    args = parser.parse_args()

    text = fetch_text(args.url)
    records = parse_jma_dmi_table(text)
    latest = max(records, key=lambda r: (r.year, r.month))
    payload = build_payload(latest, args.url)

    out_path = Path(args.out)
    archive_path = Path(args.archive_dir) / f"iod_{payload['date']}.json"

    write_json(out_path, payload)
    write_json(archive_path, payload)

    print(
        json.dumps(
            {
                "ok": True,
                "status": payload["status"],
                "dmi": payload["dmi"],
                "period": payload["date"],
                "source_date": payload["source_date"],
                "freshness": payload["freshness"],
                "staleness_days": payload["staleness_days"],
                "out": str(out_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
