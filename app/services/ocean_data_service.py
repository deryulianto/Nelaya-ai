from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

EARTH_SIGNALS_TODAY = DATA_DIR / "earth_signals_today.json"
FGI_DAILY_DIR = DATA_DIR / "fgi_daily"


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _pick_number(obj: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        v = obj.get(k)
        try:
            if v is None:
                continue
            return float(v)
        except Exception:
            continue
    return None


def _is_stale(generated_at: Optional[str]) -> bool:
    if not generated_at:
        return True
    try:
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_h = (now - dt).total_seconds() / 3600.0
        return age_h > 36
    except Exception:
        return True


def _derive_date(date_value: Optional[str], generated_at: Optional[str]) -> Optional[str]:
    if date_value:
        return str(date_value)[:10]

    if generated_at:
        try:
            dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            return dt.astimezone().date().isoformat()
        except Exception:
            return None

    return None

def _deep_find_first_number(obj: Any, candidate_keys: tuple[str, ...]) -> Optional[float]:
    try:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower() in candidate_keys:
                    try:
                        return float(v)
                    except Exception:
                        pass
            for v in obj.values():
                found = _deep_find_first_number(v, candidate_keys)
                if found is not None:
                    return found

        elif isinstance(obj, list):
            for item in obj:
                found = _deep_find_first_number(item, candidate_keys)
                if found is not None:
                    return found
    except Exception:
        return None

    return None


def compute_completeness(today: Dict[str, Any]) -> str:
    keys = ["sst_c", "chl_mg_m3", "wind_ms", "wave_m"]
    n = sum(1 for k in keys if today.get(k) is not None)

    if n >= 4:
        return "high"
    if n >= 2:
        return "medium"
    return "low"


def get_ocean_today(
    region: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    region = region or "Aceh"

    signals = _load_json(EARTH_SIGNALS_TODAY) or {}
    today = signals.get("today", signals) if isinstance(signals, dict) else {}

    generated_at = today.get("generated_at") or signals.get("generated_at")
    date_value = today.get("date") or signals.get("date")

    out = {
        "region": region,
        "date": _derive_date(date_value, generated_at),
        "generated_at": generated_at,
        "sst_c": _pick_number(today, "sst_c", "sst"),
        "chl_mg_m3": _pick_number(today, "chl_mg_m3", "chlorophyll", "chl"),
        "sal_psu": _pick_number(today, "sal_psu", "salinity"),
        "wind_ms": _pick_number(today, "wind_ms", "wind"),
        "wave_m": _pick_number(today, "wave_m", "wave"),
        "ssh_cm": _pick_number(today, "ssh_cm", "ssh"),
    }

    out["stale"] = _is_stale(out.get("generated_at"))
    out["completeness"] = compute_completeness(out)

    return out


def get_fgi_today(region: Optional[str] = None) -> Dict[str, Any]:
    region = region or "Aceh"
    latest: Dict[str, Any] = {}

    preferred = FGI_DAILY_DIR / "latest.json"

    if preferred.exists():
        loaded = _load_json(preferred)
        if isinstance(loaded, dict):
            latest = loaded

    if not latest and FGI_DAILY_DIR.exists():
        files = sorted(FGI_DAILY_DIR.glob("*.json"))
        if files:
            loaded = _load_json(files[-1])
            if isinstance(loaded, dict):
                latest = loaded

    candidate_keys = (
        "fgi_score",
        "score",
        "fgi",
        "prob",
        "probability",
        "value",
        "mean_fgi",
        "avg_fgi",
        "max_fgi",
        "best_fgi",
    )

    score = _deep_find_first_number(latest, candidate_keys)

    band = None
    if isinstance(latest, dict):
        band = latest.get("band")

    if band is None and score is not None:
        if score >= 0.75:
            band = "high"
        elif score >= 0.50:
            band = "medium"
        else:
            band = "low"

    date_value = None
    generated_at = None

    if isinstance(latest, dict):
        date_value = (
            latest.get("date")
            or latest.get("date_utc")
            or latest.get("as_of_utc")
        )
        generated_at = latest.get("generated_at")

    return {
        "region": region,
        "date": _derive_date(date_value, generated_at),
        "generated_at": generated_at,
        "fgi_score": score,
        "band": band,
        "raw_keys": sorted(list(latest.keys())) if latest else [],
    }