from __future__ import annotations

from pathlib import Path
import json
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1/earth", tags=["Earth"])

ROOT = Path(__file__).resolve().parents[2]

CANDIDATES = [
    ROOT / "data" / "earth_signals_today.json",
    ROOT / "data" / "earth" / "earth_signals_today.json",
    ROOT / "data" / "signals_today.json",
]


def _pick_file() -> Path:
    for p in CANDIDATES:
        if p.exists():
            return p
    return CANDIDATES[0]


def _first_str(*vals: Any) -> Optional[str]:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if v != v:
            return None
        return v
    except Exception:
        return None


def _parse_ymd(s: Optional[str]) -> Optional[date]:
    if not s or len(s) < 10:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _metric_count(payload: Dict[str, Any]) -> int:
    metric_candidates = [
        payload.get("sst_c"),
        payload.get("chl_mg_m3"),
        payload.get("sal_psu"),
        payload.get("wind_ms"),
        payload.get("wave_m"),
        payload.get("ssh_cm"),
        ((payload.get("metrics") or {}).get("sst") or {}).get("value"),
        ((payload.get("metrics") or {}).get("chl") or {}).get("value"),
        ((payload.get("metrics") or {}).get("sal") or {}).get("value"),
        ((payload.get("metrics") or {}).get("wind") or {}).get("value"),
        ((payload.get("metrics") or {}).get("wave") or {}).get("value"),
        ((payload.get("metrics") or {}).get("ssh") or {}).get("value"),
    ]
    return sum(1 for v in metric_candidates if _num(v) is not None)


def _collect_input_days(payload: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    inputs = payload.get("inputs") or {}
    if isinstance(inputs, dict):
        for v in inputs.values():
            if isinstance(v, dict):
                day = v.get("day")
                if isinstance(day, str) and len(day) >= 10:
                    out.append(day[:10])
    return sorted(set(out))


def _freshness_status(date_utc: Optional[str], newest_input_day: Optional[str] = None) -> str:
    ref = _parse_ymd(newest_input_day or date_utc)
    if not ref:
        return "unknown"
    today_utc = datetime.now(timezone.utc).date()
    age = (today_utc - ref).days
    if age <= 0:
        return "fresh"
    if age == 1:
        return "recent"
    return "stale"


def _confidence(payload: Dict[str, Any], mixed_days: bool) -> str:
    count = _metric_count(payload)
    if count >= 5 and not mixed_days:
        return "high"
    if count >= 3:
        return "medium"
    return "low"


def _metric_value(payload: Dict[str, Any], key: str, nested_key: str) -> Optional[float]:
    direct = _num(payload.get(key))
    if direct is not None:
        return direct
    metrics = payload.get("metrics") or {}
    if isinstance(metrics, dict):
        return _num(((metrics.get(nested_key) or {}).get("value")))
    return None


def _build_explain(payload: Dict[str, Any]) -> Dict[str, Any]:
    sst = _metric_value(payload, "sst_c", "sst")
    chl = _metric_value(payload, "chl_mg_m3", "chl")
    wind = _metric_value(payload, "wind_ms", "wind")
    wave = _metric_value(payload, "wave_m", "wave")
    ssh = _metric_value(payload, "ssh_cm", "ssh")

    drivers: List[str] = []
    if sst is not None:
        if sst >= 30.5:
            drivers.append("SST sangat hangat, yang dapat mengubah kenyamanan kondisi permukaan laut di beberapa area.")
        elif sst >= 29.0:
            drivers.append("SST hangat dan masih wajar untuk perairan tropis, tetapi tetap perlu dibaca bersama parameter lain.")
        else:
            drivers.append("SST berada pada kisaran yang relatif moderat untuk perairan tropis.")
    if chl is not None:
        if chl >= 0.5:
            drivers.append("Klorofil-a tinggi, memberi sinyal produktivitas permukaan yang relatif baik.")
        elif chl >= 0.15:
            drivers.append("Klorofil-a sedang, cukup mendukung tetapi belum menonjol.")
        else:
            drivers.append("Klorofil-a rendah, sehingga dukungan produktivitas permukaan cenderung terbatas.")
    if wave is not None:
        if wave >= 2.5:
            drivers.append("Gelombang tinggi, sehingga kehati-hatian operasi laut meningkat.")
        elif wave >= 1.5:
            drivers.append("Gelombang sedang-tinggi, yang dapat memengaruhi kenyamanan operasi di perairan terbuka.")
        else:
            drivers.append("Gelombang relatif rendah-sedang, sehingga dinamika permukaan tidak terlalu menekan kondisi umum.")
    if wind is not None:
        if wind >= 10.0:
            drivers.append("Angin sangat kencang dan menjadi faktor tekanan utama pada kondisi permukaan.")
        elif wind >= 6.0:
            drivers.append("Angin cukup kencang dan perlu diperhitungkan dalam pembacaan kondisi harian.")
        else:
            drivers.append("Angin lemah-sedang, sehingga tekanan atmosferik permukaan tidak terlalu dominan.")

    input_summary = {
        "sst_c": sst,
        "chl_mg_m3": chl,
        "wind_ms": wind,
        "wave_hs_m": wave,
        "ssh_cm": ssh,
    }
    return {
        "drivers": drivers[:4],
        "input_summary": input_summary,
        "score_summary": payload.get("summary") or "Ringkasan Earth dibangun dari sintesis sinyal oseanografi harian yang tersedia.",
        "model_note": "Earth today adalah snapshot sintesis kondisi laut harian dan bukan pengukuran langsung seluruh kesehatan ekosistem.",
    }


def _build_trust(payload: Dict[str, Any], source_file: Path) -> Dict[str, Any]:
    generated_at = _first_str(payload.get("generated_at"), ((payload.get("meta") or {}).get("generated_at")))
    if not generated_at:
        generated_at = datetime.now(timezone.utc).isoformat()

    date_utc = _first_str(payload.get("date_utc"), payload.get("asOf"), payload.get("timestamp"))
    if date_utc and len(date_utc) >= 10:
        date_utc = date_utc[:10]

    input_days = _collect_input_days(payload)
    newest_input_day = input_days[-1] if input_days else None
    mixed_days = len(input_days) > 1

    source = payload.get("source")
    if isinstance(source, dict):
        source_label = " • ".join(str(v).strip() for v in [source.get("label"), source.get("product"), source.get("provider")] if isinstance(v, str) and v.strip())
    elif isinstance(source, str) and source.strip():
        source_label = source.strip()
    else:
        source_label = f"Earth snapshot • {source_file.name}"

    return {
        "source": source_label,
        "date_utc": newest_input_day or date_utc,
        "generated_at": generated_at,
        "freshness_status": _freshness_status(date_utc, newest_input_day),
        "confidence": _confidence(payload, mixed_days),
        "basis_type": "derived_daily_ocean_snapshot",
        "mode": "daily-synthesis",
        "caveat": "Earth today adalah snapshot sintesis sinyal oseanografi harian; waktu antar-parameter dapat berbeda dan tidak identik dengan pengukuran langsung seluruh kesehatan ekosistem.",
    }


@router.get("/ping")
def ping():
    return {
        "ok": True,
        "service": "earth",
        "trust": {
            "source": "Earth router",
            "date_utc": datetime.now(timezone.utc).date().isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "freshness_status": "fresh",
            "confidence": "high",
            "basis_type": "service_health",
            "mode": "ping",
            "caveat": "Ping hanya memeriksa layanan, bukan kualitas data.",
        },
    }


@router.get("/today")
def today(trace: str | None = Query(default=None)):
    fp = _pick_file()
    if not fp.exists():
        raise HTTPException(status_code=404, detail=f"Missing earth signals file: {fp}")

    payload = json.loads(fp.read_text(encoding="utf-8"))
    payload.setdefault("meta", {})
    payload["meta"].setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    if trace:
        payload["meta"]["trace"] = trace

    payload["trust"] = _build_trust(payload, fp)
    payload["explain"] = _build_explain(payload)
    payload.setdefault(
        "summary",
        "Earth today merangkum kondisi laut harian dari parameter utama yang tersedia.",
    )
    return payload
