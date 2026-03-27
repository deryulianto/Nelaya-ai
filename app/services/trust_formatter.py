from __future__ import annotations

from typing import Any

from .evidence_schema import BasisType, ConfidenceLevel, FreshnessStatus


BASIS_LABELS = {
    BasisType.OBSERVATION.value: "Observasi",
    BasisType.MODEL_SNAPSHOT.value: "Snapshot model",
    BasisType.DERIVED_METRIC.value: "Metode turunan",
    BasisType.RULE_BASED_INTERPRETATION.value: "Interpretasi aturan",
    BasisType.MODEL_BASED_SCORE.value: "Skor model",
    BasisType.LANGUAGE_SUMMARY.value: "Ringkasan bahasa",
}

FRESHNESS_LABELS = {
    FreshnessStatus.FRESH.value: "Fresh",
    FreshnessStatus.RECENT.value: "Recent",
    FreshnessStatus.STALE.value: "Stale",
    FreshnessStatus.UNKNOWN.value: "Unknown",
}

CONFIDENCE_LABELS = {
    ConfidenceLevel.HIGH.value: "Confidence tinggi",
    ConfidenceLevel.MEDIUM.value: "Confidence menengah",
    ConfidenceLevel.LOW.value: "Confidence rendah",
}


def format_trust_footer(payload: dict[str, Any]) -> str:
    parts: list[str] = []

    date_utc = payload.get("date_utc")
    source = payload.get("source")
    freshness = payload.get("freshness_status")
    confidence = payload.get("confidence")
    basis_type = payload.get("basis_type")
    caveat = payload.get("caveat")

    if source:
        if isinstance(source, list):
            source_text = ", ".join(str(x) for x in source)
        else:
            source_text = str(source)
        parts.append(f"Sumber: {source_text}")

    if date_utc:
        parts.append(f"Tanggal data: {date_utc}")

    if freshness:
        parts.append(FRESHNESS_LABELS.get(str(freshness), str(freshness)))

    if confidence:
        parts.append(CONFIDENCE_LABELS.get(str(confidence), str(confidence)))

    if basis_type:
        parts.append(f"Basis: {BASIS_LABELS.get(str(basis_type), str(basis_type))}")

    footer = " • ".join(parts)
    if caveat:
        footer = f"{footer} • Catatan: {caveat}" if footer else f"Catatan: {caveat}"
    return footer
