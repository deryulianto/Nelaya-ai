from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.ai.confidence import compute_confidence_score


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, round(v, 3)))


def _calc_safety_score(today: Dict[str, Any]) -> float:
    score = 1.0

    wave = today.get("wave_m")
    wind = today.get("wind_ms")

    if wave is not None:
        if wave > 2.5:
            score -= 0.55
        elif wave > 2.0:
            score -= 0.35
        elif wave > 1.25:
            score -= 0.18
        else:
            score -= 0.02
    else:
        score -= 0.20

    if wind is not None:
        if wind > 12:
            score -= 0.35
        elif wind > 8:
            score -= 0.20
        elif wind > 5:
            score -= 0.08
        else:
            score -= 0.02
    else:
        score -= 0.15

    return _clamp(score)


def _calc_opportunity_score(today: Dict[str, Any], fgi: Dict[str, Any]) -> float:
    score = 0.45

    fgi_score = fgi.get("fgi_score")
    chl = today.get("chl_mg_m3")
    sst = today.get("sst_c")

    if fgi_score is not None:
        score = 0.55 * float(fgi_score) + 0.25

    if chl is not None:
        if chl >= 0.5:
            score += 0.12
        elif chl >= 0.3:
            score += 0.06
        else:
            score -= 0.05

    if sst is not None:
        if 27 <= sst <= 30:
            score += 0.08
        else:
            score -= 0.04

    return _clamp(score)


def _metric_label(metric: Optional[str]) -> str:
    m = (metric or "").strip().lower()
    mapping = {
        "sst": "suhu laut",
        "chlorophyll": "chlorophyll",
        "chl": "chlorophyll",
        "wave": "gelombang",
        "wind": "angin",
        "fgi": "FGI",
        "mpi": "MPI",
        "ssh": "tinggi muka laut",
    }
    return mapping.get(m, m or "indikator")


def _build_trend_message(trend: Dict[str, Any]) -> Optional[str]:
    trend_name = trend.get("trend")
    metric = trend.get("metric")

    if not trend_name or trend_name == "unknown":
        return None

    label = _metric_label(metric)
    return f"Tren {label} saat ini cenderung {trend_name}."


def _looks_like_numeric_question(question: Optional[str], metric: Optional[str]) -> bool:
    q = (question or "").lower()
    if "berapa" not in q:
        return False

    metric_keys = [
        "gelombang",
        "angin",
        "sst",
        "suhu",
        "chlorophyll",
        "chl",
        "salinitas",
        "sal",
        "fgi",
        "ssh",
    ]
    return any(k in q for k in metric_keys) or bool(metric)


def _build_explanations(
    intent: str,
    today: Dict[str, Any],
    fgi: Dict[str, Any],
    trend: Dict[str, Any],
    metric: Optional[str] = None,
) -> List[str]:
    msgs: List[str] = []

    wave = today.get("wave_m")
    wind = today.get("wind_ms")
    sst = today.get("sst_c")
    chl = today.get("chl_mg_m3")
    fgi_score = fgi.get("fgi_score")

    if intent == "metric_explanation":
        if metric == "fgi":
            msgs.append("FGI adalah indikator peluang relatif, bukan jaminan hasil tangkap.")
        elif metric in {"chlorophyll", "chl"}:
            msgs.append("Chlorophyll membantu membaca produktivitas perairan.")
        elif metric == "sst":
            msgs.append("SST menunjukkan suhu permukaan laut.")
        elif metric == "mpi":
            msgs.append("MPI perlu dibaca sesuai definisi operasional modul yang dipakai.")
        else:
            msgs.append("Istilah ini merupakan bagian dari sistem pembacaan indikator laut.")
        return msgs

    if intent == "safety_check":
        if wave is not None:
            if wave <= 1.25:
                msgs.append("Gelombang berada pada level rendah hingga sedang.")
            elif wave <= 2.0:
                msgs.append("Gelombang mulai perlu diwaspadai untuk operasi skala kecil.")
            else:
                msgs.append("Gelombang cukup tinggi dan meningkatkan risiko operasi laut.")

        if wind is not None:
            if wind <= 5:
                msgs.append("Angin permukaan masih relatif ringan.")
            elif wind <= 8:
                msgs.append("Angin permukaan sedang dan perlu dipantau.")
            else:
                msgs.append("Angin cukup kuat dan dapat memengaruhi keselamatan pelayaran kecil.")

        trend_msg = _build_trend_message(trend)
        if trend_msg:
            msgs.append(trend_msg)

        return msgs[:5]

    if intent == "fishing_recommendation":
        if fgi_score is not None:
            if fgi_score >= 0.75:
                msgs.append("FGI berada pada level tinggi.")
            elif fgi_score >= 0.50:
                msgs.append("FGI berada pada level sedang.")
            else:
                msgs.append("FGI berada pada level rendah.")

        if chl is not None:
            if chl >= 0.5:
                msgs.append("Chlorophyll menunjukkan produktivitas permukaan yang cukup baik.")
            elif chl >= 0.3:
                msgs.append("Chlorophyll berada pada level sedang.")
            else:
                msgs.append("Chlorophyll masih relatif rendah.")

        if sst is not None:
            if 27 <= sst <= 30:
                msgs.append("Suhu laut masih cukup mendukung bagi pembacaan peluang permukaan.")
            else:
                msgs.append("Suhu laut belum berada pada kisaran paling mendukung menurut rule sederhana v1.")

        trend_msg = _build_trend_message(trend)
        if trend_msg:
            msgs.append(trend_msg)

        return msgs[:5]

    if intent == "trend_analysis":
        trend_msg = _build_trend_message(trend)
        if trend_msg:
            msgs.append(trend_msg)

        today_v = trend.get("today")
        avg_7d = trend.get("avg_7d")
        anomaly = trend.get("anomaly")
        label = _metric_label(trend.get("metric"))

        if today_v is not None and avg_7d is not None:
            msgs.append(f"Nilai terbaru {label} dapat dibandingkan dengan rerata 7 harinya.")

        if anomaly is not None:
            msgs.append(f"Anomali {label} terhadap baseline juga sudah dihitung.")

        return msgs[:5]

    if intent == "system_explanation":
        if wave is not None:
            msgs.append("Sistem membaca gelombang sebagai komponen keselamatan.")
        if wind is not None:
            msgs.append("Sistem membaca angin sebagai komponen keselamatan.")
        if fgi_score is not None:
            msgs.append("Sistem membaca FGI sebagai komponen peluang relatif.")
        trend_msg = _build_trend_message(trend)
        if trend_msg:
            msgs.append(trend_msg)
        return msgs[:5]

    if wave is not None:
        if wave <= 1.25:
            msgs.append("Gelombang berada pada level rendah hingga sedang.")
        elif wave <= 2.0:
            msgs.append("Gelombang mulai perlu diwaspadai untuk operasi skala kecil.")
        else:
            msgs.append("Gelombang cukup tinggi dan meningkatkan risiko operasi laut.")

    if wind is not None:
        if wind <= 5:
            msgs.append("Angin permukaan masih relatif ringan.")
        elif wind <= 8:
            msgs.append("Angin permukaan sedang dan perlu dipantau.")
        else:
            msgs.append("Angin cukup kuat dan dapat memengaruhi keselamatan pelayaran kecil.")

    if fgi_score is not None:
        if fgi_score >= 0.75:
            msgs.append("FGI berada pada level tinggi.")
        elif fgi_score >= 0.50:
            msgs.append("FGI berada pada level sedang.")
        else:
            msgs.append("FGI berada pada level rendah.")

    trend_msg = _build_trend_message(trend)
    if trend_msg:
        msgs.append(trend_msg)

    return msgs[:5]


def run_reasoning(
    intent: str,
    today: Dict[str, Any],
    fgi: Dict[str, Any],
    trend: Dict[str, Any],
    persona: str = "publik",
    mode: str = "ringkas",
    metric: Optional[str] = None,
    question: Optional[str] = None,
    region: Optional[str] = None,
) -> Dict[str, Any]:
    if intent == "metric_explanation":
        explanations = _build_explanations(intent, today, fgi, trend, metric=metric)
        confidence_score = compute_confidence_score(today, fgi, len(explanations))
        return {
            "intent": intent,
            "metric": metric,
            "question_type": "definition",
            "region": region,
            "scores": {
                "confidence_score": confidence_score,
            },
            "explanation": explanations,
        }

    safety_score = _calc_safety_score(today)
    opportunity_score = _calc_opportunity_score(today, fgi)
    explanations = _build_explanations(intent, today, fgi, trend, metric=metric)
    confidence_score = compute_confidence_score(today, fgi, len(explanations))

    question_type = "numeric_lookup" if _looks_like_numeric_question(question, metric) else "general"

    return {
        "intent": intent,
        "metric": metric,
        "question_type": question_type,
        "region": region,
        "scores": {
            "safety_score": safety_score,
            "opportunity_score": opportunity_score,
            "confidence_score": confidence_score,
        },
        "explanation": explanations,
    }