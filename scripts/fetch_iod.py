from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

URL = "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"
OUT = Path("data/earth/iod_today.json")


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
    # buang missing value placeholders dan nilai tidak masuk akal
    if value in (-9999, -9999.0, -99.99, -999.0):
        return False
    if value < -10 or value > 10:
        return False
    return True


def fetch_iod() -> dict:
    response = requests.get(URL, timeout=30)
    response.raise_for_status()

    lines = response.text.splitlines()
    data = []

    for line in lines:
        parts = line.split()

        # baris data tahunan normal: [year, jan, feb, ..., dec]
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

            date = datetime(year, month, 15)
            data.append({"date": date, "dmi": value})

    if not data:
        raise RuntimeError("No valid IOD/DMI values found in source file.")

    df = pd.DataFrame(data).sort_values("date").reset_index(drop=True)
    latest = df.iloc[-1]

    dmi = float(latest["dmi"])

    result = {
        "date": latest["date"].strftime("%Y-%m-%d"),
        "dmi": round(dmi, 3),
        "status": classify_iod(dmi),
        "strength": iod_strength(dmi),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "NOAA PSL dmi.had.long.data",
    }
    return result


def save_iod(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    iod = fetch_iod()
    save_iod(iod)
    print(json.dumps(iod, indent=2))