from __future__ import annotations

from typing import Any


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_local_chl(chl: float | None) -> str:
    if chl is None:
        return "unknown"
    if chl >= 0.5:
        return "high"
    if chl >= 0.15:
        return "medium"
    return "low"


def classify_local_sst(sst: float | None) -> str:
    if sst is None:
        return "unknown"
    if sst >= 30.5:
        return "very_warm"
    if sst >= 29.0:
        return "warm"
    if sst >= 27.5:
        return "normal"
    return "cool"


def classify_local_wind(wind: float | None) -> str:
    if wind is None:
        return "unknown"
    if wind >= 10:
        return "very_strong"
    if wind >= 6:
        return "strong"
    if wind >= 3:
        return "moderate"
    return "weak"


def classify_local_wave(wave: float | None) -> str:
    if wave is None:
        return "unknown"
    if wave >= 2.5:
        return "very_high"
    if wave >= 1.5:
        return "high"
    if wave >= 0.5:
        return "moderate"
    return "low"


def compute_iod_modifier(
    dmi: float | None,
    iod_status: str | None,
    sst: float | None,
    chl: float | None,
    wind: float | None,
    wave: float | None,
) -> dict[str, Any]:
    """
    IOD hanya menjadi modifier kecil dan explainable.
    Pengaruhnya dibatasi agar tidak mendominasi FGI inti.
    """
    modifier = 1.0
    reasons: list[str] = []

    status = (iod_status or "").strip().lower()
    if not status:
        if dmi is None:
            status = "unknown"
        elif dmi >= 0.4:
            status = "positive"
        elif dmi <= -0.4:
            status = "negative"
        else:
            status = "neutral"

    chl_cls = classify_local_chl(chl)
    sst_cls = classify_local_sst(sst)
    wind_cls = classify_local_wind(wind)
    wave_cls = classify_local_wave(wave)

    if status == "positive":
        modifier += 0.02
        reasons.append("IOD positif memberi dukungan latar regional kecil")
    elif status == "negative":
        modifier -= 0.02
        reasons.append("IOD negatif menahan skor secara ringan")
    elif status == "neutral":
        reasons.append("IOD netral, pengaruh regional minimal")
    else:
        reasons.append("Status IOD belum tersedia, modifier dijaga netral")

    if status == "positive" and chl_cls in {"medium", "high"}:
        modifier += 0.03
        reasons.append("CHL lokal mendukung produktivitas permukaan")
    elif status == "negative" and chl_cls == "low":
        modifier -= 0.03
        reasons.append("CHL lokal rendah memperlemah peluang")

    if wind_cls == "strong":
        modifier -= 0.02
        reasons.append("Angin kuat menurunkan kualitas operasional")
    elif wind_cls == "very_strong":
        modifier -= 0.03
        reasons.append("Angin sangat kuat menurunkan kualitas operasional")

    if wave_cls == "high":
        modifier -= 0.03
        reasons.append("Gelombang tinggi membatasi kenyamanan operasi")
    elif wave_cls == "very_high":
        modifier -= 0.05
        reasons.append("Gelombang sangat tinggi membatasi operasi secara nyata")

    if sst_cls == "very_warm":
        modifier -= 0.02
        reasons.append("SST sangat hangat menahan peluang secara ringan")

    modifier = clamp(modifier, 0.92, 1.08)

    return {
        "dmi": round(dmi, 3) if dmi is not None else None,
        "status": status,
        "modifier": round(modifier, 3),
        "reasons": reasons,
        "local_flags": {
            "sst": sst_cls,
            "chl": chl_cls,
            "wind": wind_cls,
            "wave": wave_cls,
        },
    }


def compute_fgi_final(core_score: float | None, iod_modifier: float | None) -> float | None:
    if core_score is None or iod_modifier is None:
        return None
    return round(clamp(float(core_score) * float(iod_modifier), 0.0, 1.0), 3)


def compute_fgi_confidence(
    has_sst: bool,
    has_chl: bool,
    has_wind: bool,
    has_wave: bool,
    has_sal: bool,
    has_ssh: bool,
    iod_status: str | None,
    iod_modifier: float | None,
) -> float:
    score = 0.45

    for ok in [has_sst, has_chl, has_wind, has_wave, has_sal, has_ssh]:
        if ok:
            score += 0.07

    if (iod_status or "").lower() in {"positive", "negative", "neutral"}:
        score += 0.03

    if iod_modifier is not None and (iod_modifier > 1.06 or iod_modifier < 0.94):
        score -= 0.02

    return round(clamp(score, 0.0, 1.0), 3)
