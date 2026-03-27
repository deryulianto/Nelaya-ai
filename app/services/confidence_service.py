from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from .evidence_schema import ConfidenceLevel, FreshnessStatus


@dataclass(slots=True)
class TrustAssessment:
    freshness_status: FreshnessStatus
    confidence: ConfidenceLevel
    caveat: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "freshness_status": self.freshness_status.value,
            "confidence": self.confidence.value,
            "caveat": self.caveat,
        }


def _coerce_date(value: str | date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except Exception:
        return None


def freshness_from_date(date_utc: str | date | datetime | None, *, today_utc: date | None = None) -> FreshnessStatus:
    data_day = _coerce_date(date_utc)
    if data_day is None:
        return FreshnessStatus.UNKNOWN

    today_utc = today_utc or datetime.now(timezone.utc).date()
    age_days = (today_utc - data_day).days

    if age_days <= 1:
        return FreshnessStatus.FRESH
    if age_days <= 3:
        return FreshnessStatus.RECENT
    if age_days > 3:
        return FreshnessStatus.STALE
    return FreshnessStatus.UNKNOWN


def confidence_from_signals(
    *,
    date_utc: str | date | datetime | None,
    completeness_ratio: float | None = None,
    inference_depth: int = 0,
) -> ConfidenceLevel:
    """
    A deliberately simple first-pass confidence calculator.

    Rules:
    - start from freshness
    - reward high completeness
    - penalize deeper inference chains
    """
    freshness = freshness_from_date(date_utc)
    completeness_ratio = 1.0 if completeness_ratio is None else max(0.0, min(1.0, completeness_ratio))

    score = 0
    if freshness == FreshnessStatus.FRESH:
        score += 2
    elif freshness == FreshnessStatus.RECENT:
        score += 1
    elif freshness == FreshnessStatus.STALE:
        score -= 1

    if completeness_ratio >= 0.9:
        score += 2
    elif completeness_ratio >= 0.7:
        score += 1
    elif completeness_ratio < 0.5:
        score -= 1

    if inference_depth >= 2:
        score -= 1
    if inference_depth >= 4:
        score -= 1

    if score >= 3:
        return ConfidenceLevel.HIGH
    if score >= 1:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def assess_trust(
    *,
    date_utc: str | date | datetime | None,
    completeness_ratio: float | None = None,
    inference_depth: int = 0,
) -> TrustAssessment:
    freshness = freshness_from_date(date_utc)
    confidence = confidence_from_signals(
        date_utc=date_utc,
        completeness_ratio=completeness_ratio,
        inference_depth=inference_depth,
    )

    caveat = None
    if freshness == FreshnessStatus.STALE:
        caveat = "Data lebih lama dari 3 hari; interpretasi perlu kehati-hatian lebih."
    elif freshness == FreshnessStatus.UNKNOWN:
        caveat = "Tanggal data tidak jelas; tingkat keyakinan dibatasi."
    elif confidence == ConfidenceLevel.LOW:
        caveat = "Evidence belum cukup kuat; gunakan sebagai indikasi awal, bukan kepastian final."

    return TrustAssessment(
        freshness_status=freshness,
        confidence=confidence,
        caveat=caveat,
    )
