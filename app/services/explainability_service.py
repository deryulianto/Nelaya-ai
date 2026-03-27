from __future__ import annotations

from typing import Any

from .evidence_schema import ConfidenceLevel, ExplainabilityRecord


def describe_change(current: float | int | None, previous: float | int | None, *, epsilon: float = 0.05) -> str:
    if current is None or previous is None:
        return "belum dapat dibandingkan"
    delta = float(current) - float(previous)
    if abs(delta) <= epsilon:
        return "relatif stabil"
    if delta > 0:
        return "meningkat"
    return "menurun"


def build_index_explainability(
    *,
    index_name: str,
    score: float | int | None,
    category: str,
    drivers: list[str] | None = None,
    previous_score: float | int | None = None,
    confidence: ConfidenceLevel = ConfidenceLevel.LOW,
    caveat: str | None = None,
) -> dict[str, Any]:
    record = ExplainabilityRecord(
        index_name=index_name,
        score=score,
        category=category,
        top_drivers=drivers or [],
        trend_vs_previous=describe_change(score, previous_score),
        confidence=confidence,
        caveat=caveat,
    )
    return record.to_dict()
