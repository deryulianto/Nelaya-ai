from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix="/api/v1/biodiversity",
    tags=["biodiversity"],
)


ROOT = Path(__file__).resolve().parents[2]

CANDIDATE_EARTH_FILES = [
    ROOT / "data" / "earth" / "earth_signals_today.json",
    ROOT / "data" / "earth_signals_today.json",
]


def _now_wib() -> str:
    return datetime.now(ZoneInfo("Asia/Jakarta")).isoformat()


def _load_today_payload() -> Dict[str, Any]:
    import json

    for path in CANDIDATE_EARTH_FILES:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            data["_data_file_used"] = str(path)
            return data

    raise HTTPException(
        status_code=404,
        detail="earth_signals_today.json not found. Run the daily earth signals builder first.",
    )


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None

    if isinstance(value, dict):
        for key in ("value", "mean", "latest", "data"):
            if key in value:
                return _as_float(value.get(key))
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_metric(payload: Dict[str, Any], names: List[str]) -> Optional[float]:
    """
    Flexible metric reader.

    Supports:
    - payload["metrics"]["sst"]["value"]
    - payload["metrics"]["sst"]
    - payload["sst"]
    - payload["ocean"]["sst"]
    """

    containers: List[Dict[str, Any]] = []

    if isinstance(payload.get("metrics"), dict):
        containers.append(payload["metrics"])

    if isinstance(payload.get("ocean"), dict):
        containers.append(payload["ocean"])

    if isinstance(payload.get("data"), dict):
        containers.append(payload["data"])

    containers.append(payload)

    for container in containers:
        for name in names:
            if name in container:
                value = _as_float(container.get(name))
                if value is not None:
                    return value

    return None


def _clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(max_value, value))


def _round_or_none(value: Optional[float], ndigits: int = 3) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), ndigits)


def _thermal_safety_score(sst: Optional[float], sst_anomaly: Optional[float]) -> Dict[str, Any]:
    """
    Higher score means safer thermal condition.

    This is not a direct biodiversity claim.
    It is a thermal stress screening score.
    """

    if sst is None and sst_anomaly is None:
        return {
            "score": 50,
            "level": "unknown",
            "label": "Data suhu belum cukup",
            "reason": "SST dan anomali SST tidak tersedia.",
        }

    score = 80.0
    reasons: List[str] = []

    if sst is not None:
        if sst >= 32.0:
            score = 25.0
            reasons.append("SST sangat hangat.")
        elif sst >= 31.0:
            score = 40.0
            reasons.append("SST hangat tinggi.")
        elif sst >= 30.0:
            score = 60.0
            reasons.append("SST hangat dan perlu dipantau.")
        elif sst >= 28.0:
            score = 82.0
            reasons.append("SST berada pada kisaran relatif aman.")
        else:
            score = 70.0
            reasons.append("SST relatif lebih rendah.")

    if sst_anomaly is not None:
        if sst_anomaly >= 1.5:
            score -= 25.0
            reasons.append("Anomali SST sangat positif.")
        elif sst_anomaly >= 0.8:
            score -= 15.0
            reasons.append("Anomali SST positif cukup kuat.")
        elif sst_anomaly >= 0.3:
            score -= 6.0
            reasons.append("Anomali SST positif ringan.")
        elif sst_anomaly <= -0.8:
            score += 5.0
            reasons.append("Anomali SST negatif, tekanan panas relatif berkurang.")

    score = _clamp(score)

    if score >= 75:
        level = "low_stress"
        label = "Tekanan termal rendah"
    elif score >= 55:
        level = "watch"
        label = "Perlu dipantau"
    elif score >= 35:
        level = "moderate_stress"
        label = "Tekanan termal sedang"
    else:
        level = "high_stress"
        label = "Tekanan termal tinggi"

    return {
        "score": round(score, 1),
        "level": level,
        "label": label,
        "reason": " ".join(reasons) if reasons else "Kondisi termal dibaca dari data tersedia.",
    }


def _productivity_support_score(chl: Optional[float]) -> Dict[str, Any]:
    """
    CHL-a is treated as productivity signal, not direct biodiversity.
    Too low may mean weak productivity signal.
    Too high may indicate bloom, turbidity, or coastal input and needs caution.
    """

    if chl is None:
        return {
            "score": 50,
            "level": "unknown",
            "label": "Data produktivitas belum cukup",
            "reason": "CHL-a tidak tersedia.",
        }

    if chl < 0.05:
        score = 35.0
        level = "low"
        label = "Produktivitas rendah"
        reason = "CHL-a sangat rendah, sinyal produktivitas primer lemah."
    elif chl < 0.15:
        score = 55.0
        level = "low_medium"
        label = "Produktivitas rendah-sedang"
        reason = "CHL-a masih rendah namun mulai menunjukkan sinyal produktivitas."
    elif chl <= 0.80:
        score = 82.0
        level = "healthy_signal"
        label = "Produktivitas mendukung"
        reason = "CHL-a berada pada kisaran produktivitas yang mendukung."
    elif chl <= 2.00:
        score = 70.0
        level = "elevated"
        label = "Produktivitas tinggi"
        reason = "CHL-a tinggi; dapat mendukung rantai makanan, tetapi tetap perlu konteks lokal."
    else:
        score = 45.0
        level = "too_high_caution"
        label = "CHL-a sangat tinggi, perlu kehati-hatian"
        reason = "CHL-a sangat tinggi; dapat terkait bloom, sedimentasi, atau input pesisir."

    return {
        "score": round(score, 1),
        "level": level,
        "label": label,
        "reason": reason,
    }


def _physical_stability_score(
    wave_hs: Optional[float],
    wind_ms: Optional[float],
    salinity: Optional[float],
) -> Dict[str, Any]:
    """
    Higher score means calmer or more stable physical condition.
    This is useful for habitat exposure and field observation planning.
    """

    scores: List[float] = []
    reasons: List[str] = []

    if wave_hs is not None:
        if wave_hs >= 3.0:
            scores.append(25.0)
            reasons.append("Gelombang tinggi.")
        elif wave_hs >= 2.0:
            scores.append(45.0)
            reasons.append("Gelombang cukup kuat.")
        elif wave_hs >= 1.25:
            scores.append(65.0)
            reasons.append("Gelombang sedang.")
        else:
            scores.append(85.0)
            reasons.append("Gelombang relatif tenang.")

    if wind_ms is not None:
        if wind_ms >= 12.0:
            scores.append(30.0)
            reasons.append("Angin kuat.")
        elif wind_ms >= 8.0:
            scores.append(50.0)
            reasons.append("Angin sedang-kuat.")
        elif wind_ms >= 5.0:
            scores.append(70.0)
            reasons.append("Angin sedang.")
        else:
            scores.append(85.0)
            reasons.append("Angin relatif lemah.")

    if salinity is not None:
        if salinity < 30.0:
            scores.append(45.0)
            reasons.append("Salinitas rendah; kemungkinan ada pengaruh air tawar atau input pesisir.")
        elif salinity > 35.5:
            scores.append(55.0)
            reasons.append("Salinitas relatif tinggi; perlu konteks lokal.")
        else:
            scores.append(80.0)
            reasons.append("Salinitas berada pada kisaran laut normal.")

    if not scores:
        return {
            "score": 50,
            "level": "unknown",
            "label": "Stabilitas fisik belum cukup data",
            "reason": "Gelombang, angin, dan salinitas tidak tersedia.",
        }

    score = sum(scores) / len(scores)

    if score >= 75:
        level = "stable"
        label = "Fisik laut relatif stabil"
    elif score >= 55:
        level = "moderate"
        label = "Fisik laut sedang"
    elif score >= 35:
        level = "pressured"
        label = "Ada tekanan fisik"
    else:
        level = "high_pressure"
        label = "Tekanan fisik tinggi"

    return {
        "score": round(score, 1),
        "level": level,
        "label": label,
        "reason": " ".join(reasons),
    }


def _data_confidence_score(values: Dict[str, Optional[float]]) -> Dict[str, Any]:
    total = len(values)
    available = sum(1 for value in values.values() if value is not None)

    if total == 0:
        completeness = 0.0
    else:
        completeness = available / total

    score = completeness * 100.0

    if score >= 80:
        level = "high"
        label = "Keyakinan data tinggi"
    elif score >= 55:
        level = "medium"
        label = "Keyakinan data sedang"
    elif score >= 30:
        level = "low"
        label = "Keyakinan data rendah"
    else:
        level = "very_low"
        label = "Data sangat terbatas"

    missing = [key for key, value in values.items() if value is None]

    return {
        "score": round(score, 1),
        "level": level,
        "label": label,
        "available_metrics": available,
        "total_metrics": total,
        "missing_metrics": missing,
    }


def _overall_status(score: float) -> Dict[str, str]:
    if score >= 75:
        return {
            "level": "supportive",
            "label": "Kondisi relatif mendukung",
        }
    if score >= 60:
        return {
            "level": "fair_watch",
            "label": "Cukup mendukung, tetap dipantau",
        }
    if score >= 45:
        return {
            "level": "caution",
            "label": "Waspada ekologis",
        }
    return {
        "level": "pressure",
        "label": "Tekanan ekologis meningkat",
    }


def _build_interpretation(
    score: float,
    thermal: Dict[str, Any],
    productivity: Dict[str, Any],
    physical: Dict[str, Any],
    confidence: Dict[str, Any],
) -> str:
    status = _overall_status(score)

    return (
        f"Biodiversity membaca kondisi hari ini sebagai '{status['label']}'. "
        f"Sinyal termal: {thermal['label']}. "
        f"Sinyal produktivitas: {productivity['label']}. "
        f"Kondisi fisik: {physical['label']}. "
        f"{confidence['label']}. "
        "Interpretasi ini bukan klaim langsung tentang perubahan biodiversitas, "
        "melainkan sinyal awal tekanan atau dukungan ekologis yang perlu divalidasi dengan observasi lapangan."
    )


def _field_recommendations(
    thermal: Dict[str, Any],
    productivity: Dict[str, Any],
    physical: Dict[str, Any],
) -> List[str]:
    recs: List[str] = []

    if thermal["level"] in ("moderate_stress", "high_stress"):
        recs.append(
            "Prioritaskan foto dan catatan lapangan pada habitat sensitif seperti karang dangkal, lamun, dan perairan jernih dekat pulau kecil."
        )

    if productivity["level"] in ("too_high_caution", "elevated"):
        recs.append(
            "Catat warna air, kejernihan, bau, busa, atau indikasi bloom/sedimentasi di wilayah pesisir."
        )

    if physical["level"] in ("pressured", "high_pressure"):
        recs.append(
            "Hindari menyimpulkan kondisi biota dari observasi visual saat laut terlalu bergelombang; kualitas pengamatan dapat menurun."
        )

    if not recs:
        recs.append(
            "Lakukan observasi rutin sederhana: foto permukaan laut, catatan jenis ikan dominan, kondisi karang/lamun jika terlihat, dan koordinat lokasi."
        )

    recs.append(
        "Gunakan hasil ini sebagai panduan lokasi dan waktu observasi, bukan sebagai bukti final perubahan biodiversitas."
    )

    return recs


def build_biodiversity_watch(payload: Dict[str, Any]) -> Dict[str, Any]:
    sst = _pick_metric(payload, ["sst", "sst_c", "sea_surface_temperature", "temperature"])
    sst_anomaly = _pick_metric(payload, ["sst_anomaly", "sst_anom", "temperature_anomaly"])
    chl = _pick_metric(payload, ["chl", "chl_a", "chlorophyll", "chlorophyll_a"])
    wave_hs = _pick_metric(payload, ["wave_hs", "hs", "wave_height", "significant_wave_height", "wave_m"])
    wind_ms = _pick_metric(payload, ["wind_ms", "wind_speed", "wind", "wind_mps"])
    salinity = _pick_metric(payload, ["salinity", "sss", "sea_surface_salinity"])
    ssh = _pick_metric(payload, ["ssh", "sea_surface_height"])

    values = {
        "sst": sst,
        "sst_anomaly": sst_anomaly,
        "chl": chl,
        "wave_hs": wave_hs,
        "wind_ms": wind_ms,
        "salinity": salinity,
        "ssh": ssh,
    }

    thermal = _thermal_safety_score(sst, sst_anomaly)
    productivity = _productivity_support_score(chl)
    physical = _physical_stability_score(wave_hs, wind_ms, salinity)
    confidence = _data_confidence_score(values)

    biodiversity_watch_score = (
        0.35 * float(thermal["score"])
        + 0.30 * float(productivity["score"])
        + 0.20 * float(physical["score"])
        + 0.15 * float(confidence["score"])
    )

    biodiversity_watch_score = round(_clamp(biodiversity_watch_score), 1)
    status = _overall_status(biodiversity_watch_score)

    date_value = (
        payload.get("date")
        or payload.get("snapshot_date")
        or payload.get("latest_available_date")
        or payload.get("generated_at")
    )

    return {
        "module": "biodiversity_watch",
        "version": "0.1",
        "region": "Aceh",
        "date": date_value,
        "generated_at": _now_wib(),
        "data_file_used": payload.get("_data_file_used"),
        "score": biodiversity_watch_score,
        "status": status,
        "metrics": {
            "sst_c": _round_or_none(sst, 3),
            "sst_anomaly_c": _round_or_none(sst_anomaly, 3),
            "chl_mg_m3": _round_or_none(chl, 4),
            "wave_hs_m": _round_or_none(wave_hs, 3),
            "wind_ms": _round_or_none(wind_ms, 3),
            "salinity_psu": _round_or_none(salinity, 3),
            "ssh": _round_or_none(ssh, 3),
        },
        "components": {
            "thermal_safety": thermal,
            "productivity_support": productivity,
            "physical_stability": physical,
            "data_confidence": confidence,
        },
        "interpretation": _build_interpretation(
            biodiversity_watch_score,
            thermal,
            productivity,
            physical,
            confidence,
        ),
        "field_recommendations": _field_recommendations(
            thermal,
            productivity,
            physical,
        ),
        "claim_policy": {
            "safe_claim": "NELAYA-AI membaca sinyal tekanan dan dukungan ekologis berdasarkan dinamika laut.",
            "not_allowed_without_field_data": [
                "Mengklaim biodiversitas meningkat atau menurun secara langsung.",
                "Mengklaim karang sudah memutih tanpa foto, survei, atau data bleaching resmi.",
                "Mengklaim ikan pasti berkumpul pada lokasi tertentu tanpa validasi tangkapan atau observasi.",
            ],
            "confidence_rule": "Data fisik laut memiliki keyakinan lebih tinggi daripada klaim biologis langsung.",
        },
        "pilot_sites_note": (
            "Versi v0.1 masih membaca kondisi regional Aceh. "
            "Analisis per titik seperti Simeulue, Sabang, dan Pulau Banyak akan dibuat setelah ekstraksi grid per lokasi aktif."
        ),
    }


@router.get("/watch/today")
def get_biodiversity_watch_today() -> Dict[str, Any]:
    payload = _load_today_payload()
    return build_biodiversity_watch(payload)


@router.get("/health")
def biodiversity_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "module": "biodiversity_watch",
        "version": "0.1",
        "generated_at": _now_wib(),
    }
