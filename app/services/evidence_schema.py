from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    RECENT = "recent"
    STALE = "stale"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BasisType(str, Enum):
    OBSERVATION = "observation"
    MODEL_SNAPSHOT = "model_snapshot"
    DERIVED_METRIC = "derived_metric"
    RULE_BASED_INTERPRETATION = "rule_based_interpretation"
    MODEL_BASED_SCORE = "model_based_score"
    LANGUAGE_SUMMARY = "language_summary"


@dataclass(slots=True)
class EvidenceRecord:
    """
    Minimal evidence object for all Hybrid-AI outputs.

    Keep this schema stable and reuse it across Earth/Surf/FGI/OSI endpoints.
    """

    id: str
    kind: str
    metric: str
    value: Any
    unit: str | None = None
    region: str | None = None
    date_utc: str | None = None
    generated_at: str | None = None
    source: str | list[str] | None = None
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    basis_type: BasisType = BasisType.DERIVED_METRIC
    drivers: list[str] = field(default_factory=list)
    caveat: str | None = None
    summary: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["freshness_status"] = self.freshness_status.value
        data["confidence"] = self.confidence.value
        data["basis_type"] = self.basis_type.value
        if not self.generated_at:
            data["generated_at"] = now_utc_iso()
        return data


@dataclass(slots=True)
class ExplainabilityRecord:
    index_name: str
    score: float | int | None
    category: str
    top_drivers: list[str] = field(default_factory=list)
    trend_vs_previous: str | None = None
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    caveat: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_name": self.index_name,
            "score": self.score,
            "category": self.category,
            "top_drivers": self.top_drivers,
            "trend_vs_previous": self.trend_vs_previous,
            "confidence": self.confidence.value,
            "caveat": self.caveat,
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_driver_list(drivers: Iterable[str] | None) -> list[str]:
    if not drivers:
        return []
    return [str(x).strip() for x in drivers if str(x).strip()]


def build_evidence(
    *,
    id: str,
    kind: str,
    metric: str,
    value: Any,
    unit: str | None = None,
    region: str | None = None,
    date_utc: str | None = None,
    generated_at: str | None = None,
    source: str | list[str] | None = None,
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN,
    confidence: ConfidenceLevel = ConfidenceLevel.LOW,
    basis_type: BasisType = BasisType.DERIVED_METRIC,
    drivers: Iterable[str] | None = None,
    caveat: str | None = None,
    summary: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return EvidenceRecord(
        id=id,
        kind=kind,
        metric=metric,
        value=value,
        unit=unit,
        region=region,
        date_utc=date_utc,
        generated_at=generated_at,
        source=source,
        freshness_status=freshness_status,
        confidence=confidence,
        basis_type=basis_type,
        drivers=ensure_driver_list(drivers),
        caveat=caveat,
        summary=summary,
        extra=extra,
    ).to_dict()
