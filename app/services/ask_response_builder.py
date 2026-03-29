from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas.ocean_ask import OceanAnswerBlock, OceanAskRequest, OceanAskResponse


def _build_trust_block(
    *,
    evidence: Dict[str, Any],
    confidence: Dict[str, Any],
) -> Dict[str, Any]:
    trust = evidence.get("trust", {}) or {}

    return {
        "source": trust.get("source"),
        "date_utc": trust.get("date_utc"),
        "generated_at": trust.get("generated_at"),
        "keterbaruan": trust.get("freshness_status"),
        "keyakinan": confidence.get("label"),
        "confidence_score": confidence.get("score"),
        "basis": trust.get("basis_type"),
        "mode": trust.get("mode"),
        "caveat": trust.get("caveat"),
    }


def _collect_sources(evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources = evidence.get("sources", [])
    if isinstance(sources, list):
        return sources
    return []


def _default_followups(intent: str) -> List[str]:
    mapping = {
        "ocean_condition": [
            "Apa yang paling berubah hari ini?",
            "Apakah ombak hari ini aman?",
            "Mengapa klorofil-a rendah?",
        ],
        "safety_check": [
            "Bagaimana tren gelombang minggu ini?",
            "Apa catatan untuk kapal kecil?",
            "Di spot mana ombak lebih tinggi?",
        ],
        "fgi_indicator": [
            "Apa arti FGI?",
            "Apa beda FGI env dan FGI-R?",
            "Mana area relatif lebih menjanjikan?",
        ],
        "regulation_query": [
            "Apa pasal yang paling relevan?",
            "Wilayah berlaku aturan ini di mana?",
            "Apa kaitannya dengan nelayan kecil?",
        ],
        "fallback": [
            "Laut Aceh hari ini bagaimana?",
            "Apakah ombak hari ini aman?",
            "Apa itu rumpon?",
        ],
    }
    return mapping.get(intent, [])


def build_ocean_ask_response(
    *,
    req: OceanAskRequest,
    intent: str,
    sub_intents: Optional[List[str]],
    region: str,
    query_type: str,
    topics: Optional[List[str]],
    answer_block: Dict[str, Any],
    evidence: Dict[str, Any],
    confidence: Dict[str, Any],
    explanation: Optional[List[str]] = None,
    data_status: Optional[Dict[str, Any]] = None,
    right_panel: Optional[Dict[str, Any]] = None,
    followups: Optional[List[str]] = None,
) -> OceanAskResponse:
    answer = OceanAnswerBlock(
        headline=answer_block.get("headline", "Jawaban ditemukan."),
        summary=answer_block.get("summary", "Ringkasan jawaban belum tersedia."),
        recommendation=answer_block.get("recommendation"),
        caution=answer_block.get("caution"),
    )

    return OceanAskResponse(
        ok=True,
        question=req.question,
        intent=intent,
        sub_intents=sub_intents or [],
        region=region,
        persona=req.persona,
        mode=req.mode,
        query_type=query_type,
        topics=topics or [],
        answer=answer,
        evidence=evidence,
        scores={
            "confidence_score": confidence.get("score", 0.5),
        },
        explanation=explanation or [],
        data_status=data_status or {},
        trust=_build_trust_block(evidence=evidence, confidence=confidence),
        right_panel=right_panel or {},
        sources=_collect_sources(evidence),
        followups=followups or _default_followups(intent),
    )
