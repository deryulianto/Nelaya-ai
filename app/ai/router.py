from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.ai.intents import INTENT_KEYWORDS, METRIC_TERMS, REGION_ALIASES


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _looks_like_comparison(q: str) -> bool:
    comparison_terms = [
        "lebih",
        "dibanding",
        "daripada",
        "vs",
        "minggu lalu",
        "minggu ini",
        "kemarin",
        "hari ini",
        "naik",
        "turun",
        "lebih panas",
        "lebih dingin",
        "lebih tinggi",
        "lebih rendah",
    ]
    return any(term in q for term in comparison_terms)


def detect_metric(question: str) -> Optional[str]:
    q = _norm(question)

    # aturan tambahan berbasis bahasa alami
    if "panas" in q or "dingin" in q or "suhu" in q:
        return "sst"
    if "gelombang" in q or "ombak" in q:
        return "wave"
    if "angin" in q:
        return "wind"
    if "arus" in q or "current" in q:
        return "current"
    if "potensi ikan" in q or "fgi" in q:
        return "fgi"
    if "chlorophyll" in q or "chlorofil" in q or "klorofil" in q or "chl" in q:
        return "chlorophyll"

    for metric, aliases in METRIC_TERMS.items():
        if any(a in q for a in aliases):
            return metric
    return None


def detect_intent(question: str) -> str:
    q = _norm(question)

    # 1. system explanation
    for kw in INTENT_KEYWORDS.get("system_explanation", []):
        if kw in q:
            return "system_explanation"

    # 2. metric explanation
    if any(k in q for k in INTENT_KEYWORDS.get("metric_explanation", [])):
        metric = detect_metric(q)
        if metric:
            return "metric_explanation"

    # 3. comparative / trend analysis prioritas tinggi
    metric = detect_metric(q)
    if _looks_like_comparison(q) and metric in {"sst", "wave", "wind", "chlorophyll", "current", "fgi"}:
        return "trend_analysis"

    # 4. fallback keyword scoring
    best_intent = "ocean_condition_today"
    best_score = 0

    for intent, kws in INTENT_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in q)
        if score > best_score:
            best_intent = intent
            best_score = score

    return best_intent


def detect_sub_intents(question: str, primary_intent: str) -> List[str]:
    q = _norm(question)
    subs: List[str] = []

    if primary_intent != "ocean_condition_today":
        if any(kw in q for kw in INTENT_KEYWORDS.get("ocean_condition_today", [])):
            subs.append("ocean_condition_today")

    if primary_intent != "safety_check":
        if any(kw in q for kw in INTENT_KEYWORDS.get("safety_check", [])):
            subs.append("safety_check")

    if primary_intent != "fishing_recommendation":
        if any(kw in q for kw in INTENT_KEYWORDS.get("fishing_recommendation", [])):
            subs.append("fishing_recommendation")

    if primary_intent != "trend_analysis" and _looks_like_comparison(q):
        subs.append("trend_analysis")

    return subs


def detect_region(question: str, explicit_region: Optional[str] = None) -> Optional[str]:
    q = _norm(question)

    # 1. jika ada region disebut eksplisit di pertanyaan, itu menang
    for alias, region in REGION_ALIASES.items():
        if alias in q:
            return region

    # 2. baru fallback ke region dari form/UI
    if explicit_region and explicit_region.strip():
        return explicit_region.strip()

    return None


def route_question(
    question: str,
    region: Optional[str] = None,
    persona: str = "publik",
) -> Dict[str, Any]:
    intent = detect_intent(question)
    sub_intents = detect_sub_intents(question, intent)
    resolved_region = detect_region(question, region)
    metric = detect_metric(question)

    return {
        "intent": intent,
        "sub_intents": sub_intents,
        "region": resolved_region,
        "persona": (persona or "publik").strip().lower(),
        "metric": metric,
    }