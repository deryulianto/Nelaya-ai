from __future__ import annotations

from .config import NARRATIVE_CAUTION_MAP, NARRATIVE_POSITIVE_MAP


def osi_label(value: float) -> str:
    if value <= 20:
        return "Very Weak"
    if value <= 40:
        return "Weak"
    if value <= 60:
        return "Moderate"
    if value <= 80:
        return "Strong"
    return "Very Strong"


def summary_for_label(label: str) -> str:
    mapping = {
        "Very Weak": "Kondisi laut cenderung lemah atau data belum cukup kuat untuk membaca dinamika yang aktif.",
        "Weak": "Kondisi laut relatif tenang namun sinyal produktivitas dan dinamika masih terbatas.",
        "Moderate": "Kondisi laut moderat dengan struktur dan dinamika yang cukup seimbang.",
        "Strong": "Laut menunjukkan dinamika aktif dan struktur kolom air yang cukup sehat.",
        "Very Strong": "Laut sangat dinamis dan aktif; pembacaan keselamatan dan tekanan ekosistem tetap diperlukan.",
    }
    return mapping[label]


def build_narrative(label: str, components: dict[str, float]) -> dict[str, object]:
    ordered = sorted(components.items(), key=lambda kv: kv[1], reverse=True)
    top2 = ordered[:2]
    bottom2 = ordered[-2:]

    positives = [NARRATIVE_POSITIVE_MAP.get(name, name) for name, _ in top2]
    cautions = [NARRATIVE_CAUTION_MAP.get(name, name) for name, _ in bottom2]

    return {
        "summary": summary_for_label(label),
        "positives": positives,
        "cautions": cautions,
    }
