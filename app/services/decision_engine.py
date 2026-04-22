from __future__ import annotations

from typing import Any, Dict, List, Optional


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def estimate_fgi_like_score(
    chl: Optional[float],
    wave: Optional[float],
    wind: Optional[float],
    sst: Optional[float],
) -> float:
    """
    Skor pendekatan sementara untuk Decision Engine.
    Ini BUKAN FGI final, tetapi sinyal peluang operasional
    sampai kita sambungkan ke FGI real.
    """
    score = 0.45

    if chl is not None:
        if chl >= 1.0:
            score += 0.30
        elif chl >= 0.5:
            score += 0.18
        elif chl >= 0.15:
            score += 0.08
        else:
            score -= 0.05

    if wave is not None:
        if wave >= 2.5:
            score -= 0.35
        elif wave >= 1.5:
            score -= 0.18
        elif wave < 0.6:
            score += 0.05

    if wind is not None:
        if wind >= 12:
            score -= 0.35
        elif wind >= 8:
            score -= 0.18
        elif wind < 4:
            score += 0.05

    if sst is not None:
        if 28.0 <= sst <= 30.5:
            score += 0.08
        elif sst > 30.8:
            score -= 0.06

    return max(0.0, min(1.0, round(score, 3)))


def compute_decision(
    *,
    island_name: str,
    fgi_score: Optional[float],
    wave_m: Optional[float],
    wind_ms: Optional[float],
    bleaching_status: str,
    ecosystem_pressure: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Rule-based Decision Engine v1:
    GO / CAUTION / NO_GO
    """

    reasons: List[str] = []
    warnings: List[str] = []

    decision = "CAUTION"
    label = "Hati-hati"
    color = "amber"

    # hard safety stop
    if wave_m is not None and wave_m > 2.5:
        decision = "NO_GO"
        label = "Tunda"
        color = "red"
        reasons.append("Gelombang berada pada level tinggi untuk operasi harian.")
    if wind_ms is not None and wind_ms > 12:
        decision = "NO_GO"
        label = "Tunda"
        color = "red"
        reasons.append("Angin terlalu kuat untuk operasi yang aman.")
    if bleaching_status == "alert":
        decision = "NO_GO"
        label = "Tunda"
        color = "red"
        reasons.append("Tekanan panas ekosistem berada pada level tinggi.")

    if decision != "NO_GO":
        if (
            fgi_score is not None
            and fgi_score >= 0.6
            and (wave_m is None or wave_m < 1.5)
            and (wind_ms is None or wind_ms < 8)
            and bleaching_status not in {"alert"}
        ):
            decision = "GO"
            label = "Berangkat"
            color = "emerald"
            reasons.append("Peluang operasi relatif baik dan kondisi laut masih mendukung.")
        else:
            decision = "CAUTION"
            label = "Hati-hati"
            color = "amber"
            reasons.append("Peluang tetap ada, namun kondisi belum sepenuhnya optimal.")

    if bleaching_status in {"watch", "warning"}:
        warnings.append("Ekosistem sensitif sedang perlu dipantau lebih hati-hati.")

    if ecosystem_pressure in {"sedang", "tinggi"}:
        warnings.append("Tekanan ekosistem terdeteksi dalam pembacaan harian.")

    summary = (
        f"Keputusan awal untuk {island_name}: {label}. "
        + " ".join(reasons)
    ).strip()

    return {
        "decision": decision,
        "label": label,
        "color": color,
        "summary": summary,
        "reasons": reasons,
        "warnings": warnings,
    }
