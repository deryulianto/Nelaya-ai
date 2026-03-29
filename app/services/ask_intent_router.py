from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.services.ask_intents import (
    INTENT_FALLBACK,
    INTENT_KEYWORDS,
    INTENT_PRIORITY,
    METRIC_KEYWORDS,
)


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _contains_any(text: str, keywords: List[str]) -> bool:
    return any(k in text for k in keywords)


def detect_metric(question: str) -> Optional[str]:
    q = _normalize(question)
    for metric, keywords in METRIC_KEYWORDS.items():
        if _contains_any(q, keywords):
            return metric
    return None


def detect_topics(question: str) -> List[str]:
    q = _normalize(question)
    topics: List[str] = []

    if "aceh" in q:
        topics.append("aceh")
    if "nelayan" in q:
        topics.append("nelayan")
    if "rumpon" in q:
        topics.append("rumpon")
    if "qanun" in q:
        topics.append("qanun")
    if "panglima laot" in q:
        topics.append("panglima_laot")
    if "pulau" in q:
        topics.append("pulau")
    if "surf" in q or "ombak" in q:
        topics.append("surf")

    return topics


def classify_intent(question: str) -> Dict[str, Any]:
    q = _normalize(question)

    matched_intents: List[str] = []

    for intent in INTENT_PRIORITY:
        keywords = INTENT_KEYWORDS.get(intent, [])
        if keywords and _contains_any(q, keywords):
            matched_intents.append(intent)

    if matched_intents:
        primary_intent = matched_intents[0]
        sub_intents = matched_intents[1:]
    else:
        primary_intent = INTENT_FALLBACK
        sub_intents = []

    metric = detect_metric(q)
    topics = detect_topics(q)

    # query_type sederhana dulu
    if primary_intent in {"regulation_query", "knowledge_adat"}:
        query_type = "knowledge"
    elif primary_intent in {"reference_data_query"}:
        query_type = "reference"
    else:
        query_type = "ocean"

    return {
        "intent": primary_intent,
        "sub_intents": sub_intents,
        "metric": metric,
        "topics": topics,
        "query_type": query_type,
        "normalized_question": q,
    }
