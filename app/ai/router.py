from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.ai.intents import INTENT_KEYWORDS, METRIC_TERMS, REGION_ALIASES


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


# Sinonim tambahan agar Ocean Brain lebih paham bahasa lapangan / bahasa sehari-hari
LOCAL_METRIC_ALIASES: Dict[str, List[str]] = {
    "wave": [
        "gelombang",
        "ombak",
        "tinggi ombak",
        "ketinggian ombak",
        "tinggi gelombang",
        "gelombang laut",
        "ombak laut",
    ],
    "wind": [
        "angin",
        "kecepatan angin",
        "angin permukaan",
    ],
    "sst": [
        "sst",
        "suhu laut",
        "suhu permukaan laut",
        "panas laut",
        "temperatur laut",
    ],
    "chlorophyll": [
        "chlorophyll",
        "chl",
        "klorofil",
        "chlorofil",
        "air hijau",
        "plankton",
    ],
    "salinity": [
        "salinitas",
        "sal",
        "kadar garam",
    ],
    "current": [
        "arus",
        "arus laut",
        "kecepatan arus",
    ],
    "ssh": [
        "ssh",
        "tinggi muka laut",
        "sea surface height",
        "permukaan laut",
    ],
    "fgi": [
        "fgi",
        "fish ground index",
        "potensi ikan",
        "peluang ikan",
    ],
}


def _merged_metric_terms() -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = {}

    # ambil dari intents.py dulu
    for metric, aliases in METRIC_TERMS.items():
        merged[metric] = list(aliases)

    # tambahkan sinonim lokal
    for metric, aliases in LOCAL_METRIC_ALIASES.items():
        merged.setdefault(metric, [])
        for alias in aliases:
            if alias not in merged[metric]:
                merged[metric].append(alias)

    return merged


def detect_intent(question: str) -> str:
    q = _norm(question)
    metric_map = _merged_metric_terms()

    # prioritas: system explanation
    for kw in INTENT_KEYWORDS.get("system_explanation", []):
        if kw in q:
            return "system_explanation"

    # metric explanation bila ada "apa itu/arti" + term metrik
    if any(k in q for k in INTENT_KEYWORDS.get("metric_explanation", [])):
        for metric, aliases in metric_map.items():
            if any(a in q for a in aliases):
                return "metric_explanation"

    # pertanyaan numerik langsung tentang metrik laut
    # contoh: "berapa angin hari ini", "berapa ketinggian ombak di selat malaka"
    if "berapa" in q:
        for metric, aliases in metric_map.items():
            if any(a in q for a in aliases):
                return "ocean_condition_today"

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

    return subs


def detect_region(question: str, explicit_region: Optional[str] = None) -> Optional[str]:
    if explicit_region and explicit_region.strip():
        return explicit_region.strip()

    q = _norm(question)
    for alias, region in REGION_ALIASES.items():
        if alias in q:
            return region

    # fallback region laut penting
    if "selat malaka" in q:
        return "Selat Malaka"
    if "laut andaman" in q:
        return "Laut Andaman"
    if "samudera hindia" in q:
        return "Samudera Hindia"
    if "banda aceh" in q:
        return "Banda Aceh"
    if "sabang" in q:
        return "Sabang"
    if "simeulue" in q or "simeuleu" in q:
        return "Simeulue"

    return None


def detect_metric(question: str) -> Optional[str]:
    q = _norm(question)
    metric_map = _merged_metric_terms()

    # urutan penting: metric yang paling spesifik dulu
    priority = [
        "wave",
        "wind",
        "sst",
        "chlorophyll",
        "salinity",
        "current",
        "ssh",
        "fgi",
    ]

    for metric in priority:
        aliases = metric_map.get(metric, [])
        if any(a in q for a in aliases):
            return metric

    for metric, aliases in metric_map.items():
        if any(a in q for a in aliases):
            return metric

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