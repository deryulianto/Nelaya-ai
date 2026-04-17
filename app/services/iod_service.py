from __future__ import annotations

import json
from pathlib import Path
from typing import Any


IOD_OPERATIONAL_CANDIDATES = [
    Path("data/earth/iod_today.json"),
    Path("data/iod_today.json"),
]

IOD_HISTORICAL_CANDIDATES = [
    Path("data/earth/iod_historical_latest.json"),
    Path("data/iod_historical_latest.json"),
]


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


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


def normalize_iod_payload(data: dict[str, Any], default_mode: str) -> dict[str, Any]:
    dmi_raw = data.get("dmi")
    try:
        dmi = float(dmi_raw) if dmi_raw is not None else None
    except (TypeError, ValueError):
        dmi = None

    status = data.get("status")
    if not isinstance(status, str) or not status.strip():
        status = classify_iod(dmi)

    strength = data.get("strength")
    if not isinstance(strength, str) or not strength.strip():
        strength = iod_strength(dmi)

    return {
        "mode": data.get("mode", default_mode),
        "date": data.get("date"),
        "dmi": round(dmi, 3) if dmi is not None else None,
        "status": status,
        "strength": strength,
        "generated_at": data.get("generated_at"),
        "source": data.get("source"),
        "notes": data.get("notes"),
    }


def load_iod_operational() -> dict[str, Any] | None:
    for path in IOD_OPERATIONAL_CANDIDATES:
        data = load_json_if_exists(path)
        if isinstance(data, dict):
            return normalize_iod_payload(data, default_mode="operational")
    return None


def load_iod_historical_latest() -> dict[str, Any] | None:
    for path in IOD_HISTORICAL_CANDIDATES:
        data = load_json_if_exists(path)
        if isinstance(data, dict):
            return normalize_iod_payload(data, default_mode="historical")
    return None


def build_iod_narrative(iod: dict[str, Any] | None) -> str:
    if not iod:
        return "Data IOD belum tersedia."

    status = str(iod.get("status") or "unknown").lower()
    dmi = iod.get("dmi")
    date = iod.get("date")

    if status == "positive":
        return (
            f"IOD berada pada fase positif"
            f"{f' dengan DMI {dmi}' if dmi is not None else ''}"
            f"{f' per {date}' if date else ''}. "
            "Ini memberi konteks regional yang dapat memengaruhi dinamika laut Indonesia bagian barat."
        )
    if status == "negative":
        return (
            f"IOD berada pada fase negatif"
            f"{f' dengan DMI {dmi}' if dmi is not None else ''}"
            f"{f' per {date}' if date else ''}. "
            "Konteks regional ini perlu dibaca bersama sinyal lokal perairan Aceh."
        )
    if status == "neutral":
        return (
            f"IOD berada pada kondisi netral"
            f"{f' dengan DMI {dmi}' if dmi is not None else ''}"
            f"{f' per {date}' if date else ''}. "
            "Artinya pembacaan harian lebih bertumpu pada sinyal lokal."
        )

    return "Status IOD belum dapat ditentukan secara meyakinkan."
