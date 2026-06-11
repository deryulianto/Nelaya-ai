from __future__ import annotations

import json
from pathlib import Path
from typing import Any


OPERATIONAL_PATHS = [
    Path("data/regional/iod/latest_iod.json"),
    Path("data/earth/iod_today.json"),
    Path("data/iod_today.json"),
]

HISTORICAL_PATHS = [
    Path("data/regional/iod/latest_iod.json"),
    Path("data/earth/iod_historical_latest.json"),
    Path("data/iod_historical_latest.json"),
]


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

    a = abs(float(dmi))
    if a >= 1.0:
        return "strong"
    if a >= 0.7:
        return "moderate"
    if a >= 0.4:
        return "weak"
    return "neutral"


def _read_json_first(paths: list[Path]) -> tuple[dict[str, Any] | None, str | None]:
    for path in paths:
        if not path.exists():
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if isinstance(data, dict):
            return data, str(path)

    return None, None


def normalize_iod_payload(data: dict[str, Any], default_mode: str, source_path: str | None = None) -> dict[str, Any]:
    dmi_raw = data.get("dmi")

    try:
        dmi = float(dmi_raw) if dmi_raw is not None else None
    except Exception:
        dmi = None

    status = str(data.get("status") or "").strip().lower()
    if not status or status in {"none", "null", "unknown"}:
        status = classify_iod(dmi)

    strength = str(data.get("strength") or "").strip().lower()
    if not strength or strength in {"none", "null", "unknown"}:
        strength = iod_strength(dmi)

    # Preserve metadata dari updater JMA baru agar UI bisa membaca freshness/lag.
    payload: dict[str, Any] = {
        "module": data.get("module") or "regional_climate_iod",
        "version": data.get("version") or "1.0.0",
        "mode": data.get("mode") or default_mode,
        "status": status,
        "dmi": round(dmi, 3) if dmi is not None else None,
        "strength": strength,
        "date": data.get("date") or data.get("period") or data.get("source_date"),
        "source_date": data.get("source_date") or data.get("date"),
        "updated_at": data.get("updated_at"),
        "source": data.get("source"),
        "source_url": data.get("source_url"),
        "source_path": source_path,
        "cadence": data.get("cadence") or "monthly",
        "staleness_days": data.get("staleness_days"),
        "freshness": data.get("freshness"),
        "thresholds": data.get("thresholds"),
        "use_in_fgi_modifier": data.get("use_in_fgi_modifier", True),
        "narrative": data.get("narrative"),
    }

    return {k: v for k, v in payload.items() if v is not None}


def load_iod_operational() -> dict[str, Any] | None:
    data, source_path = _read_json_first(OPERATIONAL_PATHS)
    if not data:
        return None
    return normalize_iod_payload(data, default_mode="operational", source_path=source_path)


def load_iod_historical_latest() -> dict[str, Any] | None:
    data, source_path = _read_json_first(HISTORICAL_PATHS)
    if not data:
        return None
    return normalize_iod_payload(data, default_mode="historical", source_path=source_path)


def build_iod_narrative(iod: dict[str, Any] | None) -> str:
    if not iod:
        return (
            "IOD belum tersedia. NELAYA-AI tetap membaca kondisi laut Aceh "
            "berdasarkan sinyal lokal seperti SST, CHL, arus, angin, gelombang, "
            "salinitas, SSH, dan FGI."
        )

    if iod.get("narrative"):
        return str(iod["narrative"])

    status = str(iod.get("status") or "unknown").lower()
    dmi = iod.get("dmi")
    period = iod.get("date") or iod.get("source_date") or "periode terbaru"

    if status == "positive":
        phase = "IOD positif"
    elif status == "negative":
        phase = "IOD negatif"
    elif status == "neutral":
        phase = "IOD netral"
    else:
        phase = "IOD belum jelas"

    dmi_text = f" dengan DMI {dmi} °C" if dmi is not None else ""
    return (
        f"{phase} pada {period}{dmi_text}. "
        "IOD dibaca sebagai konteks iklim regional Samudra Hindia, bukan prediksi harian lokal Aceh."
    )
