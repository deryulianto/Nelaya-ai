from __future__ import annotations

import json
import re
import html as ihtml
from datetime import datetime, timezone
from pathlib import Path

import requests

URL = "https://www.bom.gov.au/climate/enso/"
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


def fetch_page_text(url: str) -> str:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": "https://www.bom.gov.au/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )

    resp = session.get(url, timeout=30, allow_redirects=True)
    resp.raise_for_status()
    return resp.text


def extract_operational_iod(html_text: str) -> dict:
    # decode HTML entities
    text = ihtml.unescape(html_text)

    # remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # normalize unicode minus / dash / spaces
    text = (
        text.replace("−", "-")
        .replace("–", "-")
        .replace("\xa0", " ")
        .replace("&nbsp;", " ")
    )

    # collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # optional debug sample
    print("\n--- DEBUG TEXT SAMPLE ---")
    idx = text.find("The Indian Ocean Dipole (IOD)")
    print(text[idx:idx+300] if idx != -1 else text[:600])
    print("--- END DEBUG ---\n")

    status_match = re.search(
        r"The Indian Ocean Dipole \(IOD\) is (neutral|positive|negative)\.?",
        text,
        re.IGNORECASE,
    )

    value_match = re.search(
        r"As of\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4}),\s+the IOD index is\s+([-+]?\d+(?:\.\d+)?)\s*°?\s*C",
        text,
        re.IGNORECASE,
    )

    status = status_match.group(1).lower() if status_match else "unknown"

    obs_date = None
    dmi = None

    if value_match:
        obs_date = value_match.group(1)
        dmi = float(value_match.group(2))

    strength = iod_strength(dmi)

    # jangan terlalu yakin kalau angka belum berhasil dibaca
    if dmi is None and not status_match:
        status = "unknown"
        strength = "unknown"

    return {
        "mode": "operational",
        "date": obs_date,
        "dmi": round(dmi, 3) if dmi is not None else None,
        "status": status,
        "strength": strength,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "BoM Southern Hemisphere Monitoring",
        "notes": "Operational status parsed from official BoM climate monitoring page.",
    }


def save_json(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        html = fetch_page_text(URL)
        payload = extract_operational_iod(html)
        save_json(payload)
        print(json.dumps(payload, indent=2))
    except Exception as e:
        fallback = {
            "mode": "operational",
            "date": None,
            "dmi": None,
            "status": "unknown",
            "strength": "unknown",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "BoM Southern Hemisphere Monitoring",
            "notes": f"Operational source temporarily unavailable: {type(e).__name__}: {e}",
        }
        save_json(fallback)
        print(json.dumps(fallback, indent=2))
        raise