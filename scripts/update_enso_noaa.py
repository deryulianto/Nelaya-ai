#!/usr/bin/env python3
"""
Update ENSO / Niño 3.4 context for NELAYA-AI.

Source:
NOAA CPC weekly SST indices, base period 1991-2020.

Output:
  data/regional/enso/latest_enso.json
  data/regional/enso/archive/enso_YYYY-MM-DD.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone, date
from pathlib import Path
from urllib.request import Request, urlopen

NOAA_WEEKLY_URL = "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

DATE_RE = re.compile(r"^\s*(\d{2})([A-Z]{3})(\d{4})")
FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class EnsoRecord:
    source_date: date
    nino12_sst: float
    nino12_anom: float
    nino3_sst: float
    nino3_anom: float
    nino34_sst: float
    nino34_anom: float
    nino4_sst: float
    nino4_anom: float


def fetch_text(url: str, timeout: int = 30) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "NELAYA-AI/1.0 (+https://nelaya-ai.com; enso-index-updater)",
            "Accept": "text/plain,text/*,*/*",
        },
    )
    with urlopen(req, timeout=timeout) as res:
        return res.read().decode("utf-8", errors="replace")


def parse_weekly_noaa(text: str) -> list[EnsoRecord]:
    records: list[EnsoRecord] = []

    for line in text.splitlines():
        m = DATE_RE.match(line)
        if not m:
            continue

        day = int(m.group(1))
        mon = MONTHS.get(m.group(2).upper())
        year = int(m.group(3))
        if not mon:
            continue

        values = [float(x) for x in FLOAT_RE.findall(line[m.end():])]

        # Format umum CPC:
        # NINO1+2 SST/SSTA, NINO3 SST/SSTA, NINO3.4 SST/SSTA, NINO4 SST/SSTA
        if len(values) < 8:
            continue

        records.append(
            EnsoRecord(
                source_date=date(year, mon, day),
                nino12_sst=values[0],
                nino12_anom=values[1],
                nino3_sst=values[2],
                nino3_anom=values[3],
                nino34_sst=values[4],
                nino34_anom=values[5],
                nino4_sst=values[6],
                nino4_anom=values[7],
            )
        )

    if not records:
        raise ValueError("No valid NOAA CPC weekly ENSO records found")

    return records


def classify_weekly_nino34(anom: float) -> tuple[str, str, str]:
    """
    Ini bukan klasifikasi ONI resmi.
    Ini hanya sinyal mingguan Niño 3.4 untuk konteks regional.
    Karena itu label dibuat hati-hati: warm/cool tendency, bukan deklarasi El Niño/La Niña resmi.
    """
    if anom >= 0.5:
        return "warm_tendency", "Kecenderungan hangat ENSO", "warm"
    if anom <= -0.5:
        return "cool_tendency", "Kecenderungan dingin ENSO", "cool"
    return "neutral", "ENSO netral", "neutral"


def freshness_label(staleness_days: int) -> str:
    if staleness_days <= 14:
        return "fresh_weekly"
    if staleness_days <= 28:
        return "late_weekly"
    return "stale"


def build_payload(record: EnsoRecord, source_url: str) -> dict:
    now = datetime.now(timezone.utc)
    staleness_days = (now.date() - record.source_date).days
    status, label, thermal_signal = classify_weekly_nino34(record.nino34_anom)
    freshness = freshness_label(staleness_days)

    narrative = (
        f"{label} berdasarkan anomali Niño 3.4 mingguan {record.nino34_anom:.2f} °C "
        f"pada {record.source_date.isoformat()}. ENSO dibaca sebagai konteks iklim regional Pasifik, "
        "bukan prediksi harian lokal Aceh. Untuk NELAYA-AI, pengaruh lokal tetap harus dikunci oleh "
        "SST, CHL, arus, angin, gelombang, salinitas, SSH, FGI, dan observasi nelayan."
    )

    return {
        "module": "regional_climate_enso",
        "version": "1.0.0",
        "status": status,
        "phase": label,
        "label": label,
        "nino34": round(record.nino34_anom, 2),
        "nino34_sst": round(record.nino34_sst, 2),
        "value": round(record.nino34_anom, 2),
        "date": record.source_date.isoformat(),
        "source_date": record.source_date.isoformat(),
        "updated_at": now.isoformat(),
        "source": "NOAA CPC weekly SST indices, base period 1991-2020",
        "source_url": source_url,
        "cadence": "weekly",
        "staleness_days": staleness_days,
        "freshness": freshness,
        "thermal_signal": thermal_signal,
        "thresholds": {
            "warm_weekly_signal_min_nino34_c": 0.5,
            "cool_weekly_signal_max_nino34_c": -0.5,
            "neutral_weekly_range_nino34_c": "-0.5 < Niño 3.4 anomaly < 0.5",
            "note": "Weekly Niño 3.4 is not the same as official ONI event classification.",
        },
        "use_in_fgi_modifier": False,
        "narrative": narrative,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=NOAA_WEEKLY_URL)
    parser.add_argument("--out", default="data/regional/enso/latest_enso.json")
    parser.add_argument("--archive-dir", default="data/regional/enso/archive")
    args = parser.parse_args()

    text = fetch_text(args.url)
    records = parse_weekly_noaa(text)
    latest = max(records, key=lambda r: r.source_date)

    payload = build_payload(latest, args.url)

    out_path = Path(args.out)
    archive_path = Path(args.archive_dir) / f"enso_{payload['source_date']}.json"

    write_json(out_path, payload)
    write_json(archive_path, payload)

    print(
        json.dumps(
            {
                "ok": True,
                "status": payload["status"],
                "phase": payload["phase"],
                "nino34": payload["nino34"],
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
