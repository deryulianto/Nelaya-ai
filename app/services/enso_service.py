from __future__ import annotations

import json
from pathlib import Path
from typing import Any


OPERATIONAL_PATHS = [
    Path("data/regional/enso/latest_enso.json"),
    Path("data/earth/enso_today.json"),
    Path("data/enso_today.json"),
]


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


def normalize_enso_payload(data: dict[str, Any], source_path: str | None = None) -> dict[str, Any]:
    nino34_raw = data.get("nino34") or data.get("nino_34") or data.get("value") or data.get("sst_anomaly")

    try:
        nino34 = float(nino34_raw) if nino34_raw is not None else None
    except Exception:
        nino34 = None

    status = str(data.get("status") or "").strip().lower()
    if not status:
        if nino34 is None:
            status = "unknown"
        elif nino34 >= 0.5:
            status = "el_nino_tendency"
        elif nino34 <= -0.5:
            status = "la_nina_tendency"
        else:
            status = "neutral"

    # Normalisasi label agar tidak terdengar sebagai deklarasi El Niño/La Niña resmi.
    if status == "el_nino_tendency":
        status = "warm_tendency"
    elif status == "la_nina_tendency":
        status = "cool_tendency"

    raw_phase = str(data.get("phase") or data.get("label") or "").strip()

    if status == "warm_tendency":
        phase = "Kecenderungan hangat ENSO"
    elif status == "cool_tendency":
        phase = "Kecenderungan dingin ENSO"
    elif status == "neutral":
        phase = "ENSO netral"
    else:
        phase = raw_phase or "ENSO belum jelas"

    payload: dict[str, Any] = {
        "module": data.get("module") or "regional_climate_enso",
        "version": data.get("version") or "1.0.0",
        "mode": data.get("mode") or "operational",
        "status": status,
        "phase": phase,
        "label": phase,
        "nino34": round(nino34, 3) if nino34 is not None else None,
        "nino34_sst": data.get("nino34_sst"),
        "value": round(nino34, 3) if nino34 is not None else None,
        "date": data.get("date") or data.get("source_date"),
        "source_date": data.get("source_date") or data.get("date"),
        "updated_at": data.get("updated_at"),
        "source": data.get("source"),
        "source_url": data.get("source_url"),
        "source_path": source_path,
        "cadence": data.get("cadence") or "weekly",
        "staleness_days": data.get("staleness_days"),
        "freshness": data.get("freshness"),
        "thermal_signal": data.get("thermal_signal"),
        "thresholds": data.get("thresholds"),
        "use_in_fgi_modifier": data.get("use_in_fgi_modifier", False),
        "narrative": data.get("narrative"),
    }

    return {k: v for k, v in payload.items() if v is not None}


def load_enso_operational() -> dict[str, Any] | None:
    data, source_path = _read_json_first(OPERATIONAL_PATHS)
    if not data:
        return None
    return normalize_enso_payload(data, source_path=source_path)


def build_enso_narrative(enso: dict[str, Any] | None) -> str:
    if not enso:
        return (
            "ENSO belum tersedia. NELAYA-AI tetap membaca kondisi laut Aceh "
            "berdasarkan sinyal lokal seperti SST, CHL, arus, angin, gelombang, "
            "salinitas, SSH, dan FGI."
        )

    if enso.get("narrative"):
        return str(enso["narrative"])

    phase = enso.get("phase") or enso.get("label") or "ENSO belum jelas"
    nino34 = enso.get("nino34")
    date = enso.get("source_date") or enso.get("date") or "periode terbaru"

    value_text = f" dengan anomali Niño 3.4 {nino34} °C" if nino34 is not None else ""
    return (
        f"{phase} pada {date}{value_text}. "
        "ENSO dibaca sebagai konteks iklim regional Pasifik, bukan prediksi harian lokal Aceh."
    )
