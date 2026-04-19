from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional

ROOT = Path(__file__).resolve().parents[2]

TODAY_PATH = ROOT / "data" / "earth" / "earth_signals_today.json"
YESTERDAY_PATH = ROOT / "data" / "earth" / "earth_signals_yesterday.json"

THRESHOLDS = {
    "sst_c": 0.3,
    "chl_mg_m3": 0.03,
    "wave_m": 0.2,
    "wind_ms": 0.5,
    "ssh_cm": 2.0,
    "index": 0.05,
}


def _load_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _delta_state(today: Optional[float], yesterday: Optional[float], threshold: float) -> str:
    if today is None or yesterday is None:
        return "tidak diketahui"

    diff = today - yesterday
    if abs(diff) < threshold:
        return "stabil"
    if diff > 0:
        return "naik"
    return "turun"


def _delta_payload(today: Optional[float], yesterday: Optional[float], threshold: float) -> Dict[str, Any]:
    state = _delta_state(today, yesterday, threshold)
    diff = None
    if today is not None and yesterday is not None:
        diff = float(today - yesterday)

    return {
        "today": today,
        "yesterday": yesterday,
        "diff": diff,
        "state": state,
    }


def _metric_value(obj: Dict[str, Any], key: str) -> Optional[float]:
    return _to_float((obj.get("metrics", {}).get(key) or {}).get("value"))


def compute_delta() -> Dict[str, Any]:
    today = _load_json(TODAY_PATH)
    yest = _load_json(YESTERDAY_PATH)

    if not today or not yest:
        return {
            "available": False,
            "reason": "today_or_yesterday_missing",
            "changes": {},
        }

    result = {
        "available": True,
        "today_date": today.get("date_utc"),
        "yesterday_date": yest.get("date_utc"),
        "changes": {},
    }

    # raw metrics
    for key in ["sst_c", "chl_mg_m3", "wave_m", "wind_ms", "ssh_cm"]:
        result["changes"][key] = _delta_payload(
            _to_float(today.get(key)),
            _to_float(yest.get(key)),
            THRESHOLDS.get(key, 0.1),
        )

    # indices
    for idx in ["fgi", "osi", "msi"]:
        result["changes"][idx] = _delta_payload(
            _metric_value(today, idx),
            _metric_value(yest, idx),
            THRESHOLDS["index"],
        )

    return result


def build_delta_sentence(delta: Dict[str, Any]) -> Optional[str]:
    if not delta.get("available"):
        return None

    changes = delta.get("changes", {})

    sst = (changes.get("sst_c") or {}).get("state")
    chl = (changes.get("chl_mg_m3") or {}).get("state")
    fgi = (changes.get("fgi") or {}).get("state")
    osi = (changes.get("osi") or {}).get("state")
    msi = (changes.get("msi") or {}).get("state")

    parts: list[str] = []

    if sst == "naik":
        parts.append("Suhu laut cenderung meningkat dibanding kemarin")
    elif sst == "turun":
        parts.append("Suhu laut mulai menurun dibanding kemarin")

    if chl == "naik":
        parts.append("produktivitas biologis menunjukkan peningkatan")
    elif chl == "turun":
        parts.append("produktivitas biologis cenderung melemah")

    if fgi == "naik":
        parts.append("peluang perikanan sedikit membaik")
    elif fgi == "turun":
        parts.append("peluang perikanan cenderung menurun")

    if osi == "naik":
        parts.append("stabilitas laut menguat")
    elif osi == "turun":
        parts.append("stabilitas laut sedikit melemah")

    if msi == "naik":
        parts.append("dan sinyal keberlanjutan harian membaik")
    elif msi == "turun":
        parts.append("dan sinyal keberlanjutan harian melemah")

    if not parts:
        return "Kondisi laut relatif stabil dibandingkan hari sebelumnya."

    sentence = ", ".join(parts)
    if not sentence.endswith("."):
        sentence += "."
    return sentence