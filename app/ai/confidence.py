from __future__ import annotations

from typing import Any, Dict


def compute_confidence_score(today: Dict[str, Any], fgi: Dict[str, Any], explanation_count: int) -> float:
    score = 0.35

    completeness = today.get("completeness")
    if completeness == "high":
        score += 0.20
    elif completeness == "medium":
        score += 0.10

    if not today.get("stale", True):
        score += 0.15

    if today.get("date"):
        score += 0.08
    else:
        score -= 0.08

    if fgi.get("fgi_score") is not None:
        score += 0.10
    else:
        score -= 0.08

    score += min(explanation_count * 0.02, 0.08)

    return max(0.0, min(1.0, round(score, 3)))
