from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QueryIntent(str, Enum):
    OBSERVATION = "observation"
    INTERPRETATION = "interpretation"
    INDEX = "index"
    REGULATION = "regulation"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class RoutedQuery:
    intent: QueryIntent
    engine_key: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "intent": self.intent.value,
            "engine_key": self.engine_key,
            "reason": self.reason,
        }


OBS_WORDS = {"gelombang", "ombak", "sst", "suhu", "salinitas", "angin", "chlorophyll", "chl"}
INDEX_WORDS = {"fgi", "osi", "fgi-r", "skor", "indeks", "index"}
REG_WORDS = {"qanun", "regulasi", "rumpon", "zonasi", "aturan", "pasal", "izin"}
INTERP_WORDS = {"aman", "melaut", "mengapa", "kenapa", "waspada", "bagaimana kondisi"}


def classify_intent(question: str) -> RoutedQuery:
    q = question.casefold()

    if any(word in q for word in REG_WORDS):
        return RoutedQuery(QueryIntent.REGULATION, "regulation_engine", "Terdeteksi kata kunci regulasi/tata ruang.")
    if any(word in q for word in INDEX_WORDS):
        return RoutedQuery(QueryIntent.INDEX, "scoring_engine", "Terdeteksi kata kunci indeks/skor.")
    if any(word in q for word in INTERP_WORDS):
        return RoutedQuery(QueryIntent.INTERPRETATION, "domain_reasoning_engine", "Terdeteksi permintaan interpretasi atau kehati-hatian.")
    if any(word in q for word in OBS_WORDS):
        return RoutedQuery(QueryIntent.OBSERVATION, "signals_engine", "Terdeteksi pertanyaan observasional/data sinyal laut.")
    return RoutedQuery(QueryIntent.UNKNOWN, "language_fallback", "Belum cukup sinyal untuk routing presisi; gunakan fallback hati-hati.")
