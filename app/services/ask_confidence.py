from __future__ import annotations

from typing import Any, Dict, Tuple


def _to_label(score: float) -> str:
    if score >= 0.85:
        return "tinggi"
    if score >= 0.60:
        return "sedang"
    return "rendah"


def compute_confidence(
    *,
    intent: str,
    evidence: Dict[str, Any],
    answer_kind: str = "default",
) -> Dict[str, Any]:
    """
    Output:
    {
      "score": 0.72,
      "label": "sedang",
      "reasons": [...]
    }
    """
    reasons = []
    score = 0.50

    trust = evidence.get("trust", {}) or {}
    upstream_conf = (trust.get("confidence") or "").lower()
    has_data = bool(evidence.get("data"))
    has_documents = bool(evidence.get("documents"))
    has_items = bool(evidence.get("items"))
    has_explain = bool(evidence.get("explain"))
    intent_match = evidence.get("intent_match", True)
    is_fallback = evidence.get("is_fallback", False)
    missing_core = evidence.get("missing_core_fields", False)

    if intent_match:
        score += 0.10
        reasons.append("intent cocok")
    else:
        score -= 0.20
        reasons.append("intent belum cukup cocok")

    if has_data or has_documents or has_items:
        score += 0.15
        reasons.append("evidence utama tersedia")
    else:
        score -= 0.20
        reasons.append("evidence utama belum tersedia")

    if has_explain:
        score += 0.10
        reasons.append("penjelasan tersedia")

    if upstream_conf == "high":
        score += 0.10
        reasons.append("confidence upstream tinggi")
    elif upstream_conf == "medium":
        score += 0.05
        reasons.append("confidence upstream sedang")
    elif upstream_conf == "low":
        score -= 0.05
        reasons.append("confidence upstream rendah")

    if missing_core:
        score -= 0.15
        reasons.append("field inti belum lengkap")

    if is_fallback:
        score = min(score, 0.55)
        reasons.append("jawaban fallback")

    if answer_kind == "generic":
        score = min(score, 0.65)
        reasons.append("jawaban masih generik")

    score = max(0.20, min(score, 0.95))

    return {
        "score": round(score, 2),
        "label": _to_label(score),
        "reasons": reasons,
    }
