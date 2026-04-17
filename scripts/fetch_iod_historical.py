from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

URL = "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"
OUT = Path("data/earth/iod_historical_latest.json")


def classify_iod(dmi: float | None) -> str:
    if dmi is None:
        return "unknown"
    if dmi >= 0.4:
        return "positive"
    if dmi <= -0.4:
        return "negative"
    return "neutral"


def iod_strength(dmi: float | None) -> str:
    if dmi is None:
        return "unknown"
    a = abs(dmi)
    if a >= 1.0:
        return "strong"
    if a >= 0.6:
        return "moderate"
    if a >= 0.4:
        return "weak"
    return "neutral"


def is_valid_dmi(value: float) -> bool:
    if value in (-9999, -9999.0, -999.0, -99.99):
        return False
    if value < -10 or value > 10:
        return False
    return True


def fetch_iod_historical_latest() -> dict:
    resp = requests.get(URL, timeout=30)
    resp.raise_for_status()

    rows: list[dict] = []
    for line in resp.text.splitlines():
        parts = line.split()
        if len(parts) < 13:
            continue

        try:
            year = int(parts[0])
        except ValueError:
            continue

        for month in range(1, 13):
            try:
                value = float(parts[month])
            except (ValueError, TypeError, IndexError):
                continue

            if not is_valid_dmi(value):
                continue

            rows.append(
                {
                    "date": datetime(year, month, 15),
                    "dmi": value,
                }
            )

    if not rows:
        raise RuntimeError("No valid DMI values found in NOAA PSL source.")

    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    latest = df.iloc[-1]
    dmi = float(latest["dmi"])

    payload = {
        "mode": "historical",
        "date": latest["date"].strftime("%Y-%m-%d"),
        "dmi": round(dmi, 3),
        "status": classify_iod(dmi),
        "strength": iod_strength(dmi),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "NOAA PSL dmi.had.long.data",
        "notes": "Historical reference from NOAA PSL; not intended as current operational daily status.",
    }
    return payload


def save_json(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    payload = fetch_iod_historical_latest()
    save_json(payload)
    print(json.dumps(payload, indent=2))
