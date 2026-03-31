from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas.ocean_ask import OceanAskRequest, OceanAskResponse
from app.services.ask_context import build_context
from app.services.ask_intent_router import classify_intent
from app.services.ask_confidence import compute_confidence
from app.services.ask_response_builder import build_ocean_ask_response


def _normalize_text(s: Any) -> str:
    return str(s or "").strip().lower()


def _resolve_effective_region(req: OceanAskRequest, ctx: Dict[str, Any]) -> str:
    """
    Prioritas:
    1. wilayah eksplisit di pertanyaan
    2. wilayah dari form / context
    """
    q = _normalize_text(req.question)

    region_aliases = [
        ("banda aceh", "Banda Aceh"),
        ("aceh besar", "Aceh Besar"),
        ("aceh barat", "Aceh Barat"),
        ("aceh barat daya", "Aceh Barat Daya"),
        ("aceh jaya", "Aceh Jaya"),
        ("aceh selatan", "Aceh Selatan"),
        ("aceh singkil", "Aceh Singkil"),
        ("aceh tamiang", "Aceh Tamiang"),
        ("aceh tengah", "Aceh Tengah"),
        ("aceh tenggara", "Aceh Tenggara"),
        ("aceh timur", "Aceh Timur"),
        ("aceh utara", "Aceh Utara"),
        ("pidie", "Pidie"),
        ("pidie jaya", "Pidie Jaya"),
        ("bener meriah", "Bener Meriah"),
        ("bireuen", "Bireuen"),
        ("bieureuen", "Bireuen"),
        ("gayo lues", "Gayo Lues"),
        ("nagan raya", "Nagan Raya"),
        ("subulussalam", "Subulussalam"),
        ("lhokseumawe", "Lhokseumawe"),
        ("langsa", "Langsa"),
        ("sabang", "Sabang"),
        ("simeulue", "Simeulue"),
        ("aceh", "Aceh"),
    ]

    for needle, canonical in region_aliases:
        if f"di {needle}" in q or f"wilayah {needle}" in q or q.endswith(needle) or f" {needle} " in f" {q} ":
            return canonical

    return ctx.get("region") or "Aceh"


def _looks_like_followup(req: OceanAskRequest) -> bool:
    q = _normalize_text(req.question)
    markers = [
        "aturan ini",
        "aturan tersebut",
        "dokumen ini",
        "dokumen tersebut",
        "pasal ini",
        "pasal itu",
        "pasal tersebut",
        "wilayah berlaku",
        "berlaku di mana",
        "cakupan aturan",
        "ruang berlaku",
        "siapa yang terkena",
        "untuk wilayah mana",
        "yang mana",
        "yang lebih aman",
        "kalau untuk",
    ]
    return any(m in q for m in markers)


def _build_memory(req: OceanAskRequest) -> Dict[str, Any]:
    ctx = req.context or {}
    return {
        "last_intent": ctx.get("last_intent"),
        "last_query_type": ctx.get("last_query_type"),
        "last_region": ctx.get("last_region"),
        "last_topics": ctx.get("last_topics") or [],
        "last_primary_source": ctx.get("last_primary_source"),
        "last_primary_pasal": ctx.get("last_primary_pasal"),
        "has_context": bool(ctx),
    }


def _carry_intent_from_context(
    req: OceanAskRequest,
    detected_intent: str,
    memory: Dict[str, Any],
) -> str:
    """
    Override ringan untuk follow-up.
    """
    last_intent = _normalize_text(memory.get("last_intent"))
    last_query_type = _normalize_text(memory.get("last_query_type"))
    has_last_source = bool(memory.get("last_primary_source"))

    if detected_intent == "fallback" and _looks_like_followup(req):
        if last_intent == "regulation_query":
            return "regulation_query"
        if last_query_type == "knowledge" and has_last_source:
            return "regulation_query"

    return detected_intent


def route_subintent(
    req: OceanAskRequest,
    intent: str,
    ctx: Dict[str, Any],
    memory: Dict[str, Any],
) -> Dict[str, Any]:
    q = _normalize_text(req.question)

    if intent == "regulation_query":
        compliance_markers = [
            "bolehkah",
            "apakah boleh",
            "dilarang",
            "tidak boleh",
            "bom",
            "racun",
            "potas",
            "setrum",
            "alat tangkap yang dilarang",
            "jenis alat tangkap yang dilarang",
            "illegal fishing",
        ]
        scope_markers = [
            "wilayah berlaku",
            "berlaku di mana",
            "siapa yang terkena",
            "untuk wilayah mana",
            "cakupannya",
            "ruang berlaku",
            "cakupan aturan",
        ]

        if any(m in q for m in compliance_markers):
            return {"sub_intent": "regulation_compliance", "confidence": 0.90}
        if any(m in q for m in scope_markers):
            return {"sub_intent": "regulation_scope", "confidence": 0.88}
        return {"sub_intent": "regulation_explainer", "confidence": 0.80}

    if intent == "fgi_indicator":
        if ("apa arti" in q) or ("apa itu" in q):
            return {"sub_intent": "definition", "confidence": 0.90}
        if (
            ("informasi fgi" in q)
            or ("gambaran fgi" in q)
            or ("ringkasan fgi" in q)
            or ("secara umum" in q and "fgi" in q)
            or ("kondisi fgi" in q)
        ):
            return {"sub_intent": "general_summary", "confidence": 0.88}
        return {"sub_intent": "reasoning", "confidence": 0.80}

    if intent == "relative_opportunity":
        compare_markers = [
            "perairan mana",
            "mana yang ikannya lebih banyak",
            "mana ikan lebih banyak",
            "wilayah mana yang ikannya lebih banyak",
            "area mana yang lebih menjanjikan",
            "perairan mana yang lebih menjanjikan",
            "lokasi mana yang relatif lebih baik",
            "mana yang relatif lebih banyak",
            "relatif lebih banyak di mana",
        ]
        if any(m in q for m in compare_markers):
            return {"sub_intent": "spatial_compare", "confidence": 0.86}
        return {"sub_intent": "single_region", "confidence": 0.82}

    if intent == "trend_analysis":
        if "minggu ini" in q and "minggu lalu" in q:
            return {"sub_intent": "weekly_compare", "confidence": 0.90}
        if "hari ini" in q and "kemarin" in q:
            return {"sub_intent": "daily_compare", "confidence": 0.90}
        return {"sub_intent": "summary", "confidence": 0.78}

    return {"sub_intent": "default", "confidence": 0.70}


def select_evidence_bundle(
    req: OceanAskRequest,
    intent: str,
    sub_intent: str,
    ctx: Dict[str, Any],
    memory: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Tahap awal:
    evidence bundle masih ringan.
    Nanti dihubungkan ke engine domain yang lebih spesifik.
    """
    return {
        "intent": intent,
        "sub_intent": sub_intent,
        "region": ctx.get("region"),
        "memory": memory,
        "data": {},
        "documents": [],
        "sources": [],
        "trust": {},
        "right_panel_seed": {},
    }


def compose_answer_from_bundle(
    req: OceanAskRequest,
    intent: str,
    sub_intent: str,
    bundle: Dict[str, Any],
    ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Composer ringan v2 awal.
    Ini hanya fallback aman sebelum semua domain composer dipisah.
    """
    region = ctx.get("region") or "Aceh"

    if intent == "off_domain_feedback":
        return {
            "answer_block": {
                "headline": "Terima kasih, saya memang masih terus belajar.",
                "summary": (
                    "Kalau ada jawaban saya yang belum pas, itu masukan yang baik. "
                    "Coba beri saya pertanyaan yang lebih spesifik tentang kondisi laut, FGI, gelombang, "
                    "regulasi, atau data referensi, dan saya akan mencoba menjawab lebih baik."
                ),
                "recommendation": "Arahkan saya ke pertanyaan yang lebih spesifik agar pembacaan saya lebih tepat.",
                "caution": "Saya masih dalam tahap penguatan dan terus diperbaiki dari waktu ke waktu.",
            },
            "explanation": [
                "Respons ini ditujukan untuk umpan balik ringan, bukan pertanyaan domain laut."
            ],
            "right_panel": {
                "title": "Respons percakapan",
                "cards": [
                    {"label": "Jenis query", "value": "Feedback", "unit": ""},
                    {"label": "Mode", "value": "Percakapan", "unit": ""},
                ],
            },
            "data_status": {"source_type": "conversation_feedback"},
            "followups": [
                "Bagaimana kondisi laut hari ini?",
                "Apa itu FGI?",
                "Apakah ombak hari ini aman?",
                "Apa itu rumpon?",
            ],
        }

    if intent == "fallback":
        return {
            "answer_block": {
                "headline": "Pertanyaan belum bisa dipetakan dengan cukup kuat.",
                "summary": (
                    f"Saya belum cukup yakin memilih jalur terbaik untuk menjawab pertanyaan ini di wilayah {region}."
                ),
                "recommendation": "Coba buat pertanyaan lebih spesifik tentang laut, FGI, gelombang, regulasi, atau data referensi.",
                "caution": "Pada tahap ini, tidak semua pertanyaan kompleks sudah didukung penuh.",
            },
            "explanation": [
                "Pertanyaan belum cukup spesifik atau belum cocok ke domain yang tersedia."
            ],
            "right_panel": {
                "title": "Status jawaban",
                "cards": [
                    {"label": "Jenis query", "value": "Fallback", "unit": ""},
                ],
            },
            "data_status": {"source_type": "fallback"},
            "followups": [
                "Laut Aceh hari ini bagaimana?",
                "Apakah ombak hari ini aman?",
                "Mengapa FGI rendah?",
                "Apa itu rumpon?",
            ],
        }

    return {
        "answer_block": {
            "headline": f"Pertanyaan {intent} berhasil diarahkan.",
            "summary": (
                f"Orchestrator v2 sudah mengenali intent `{intent}`"
                + (f" dengan sub-intent `{sub_intent}`." if sub_intent else ".")
                + " Tahap berikutnya adalah menyambungkan ke composer domain yang lebih kaya."
            ),
            "recommendation": "Hubungkan intent ini ke evidence selector dan composer domain agar jawaban makin matang.",
            "caution": "Ini masih kerangka orchestrator v2 tahap awal.",
        },
        "explanation": [
            f"Intent terpilih: {intent}",
            f"Sub-intent: {sub_intent}",
            f"Wilayah kerja: {ctx.get('region')}",
        ],
        "right_panel": {
            "title": "Routing Orchestrator v2",
            "cards": [
                {"label": "Intent", "value": intent, "unit": ""},
                {"label": "Sub-intent", "value": sub_intent, "unit": ""},
                {"label": "Wilayah", "value": ctx.get('region'), "unit": ""},
            ],
        },
        "data_status": {"source_type": "orchestrator_v2"},
        "followups": [
            "Bagaimana kondisi laut hari ini?",
            "Apa arti FGI?",
            "Apa itu rumpon?",
        ],
    }


def orchestrate_tanya_v2(req: OceanAskRequest) -> OceanAskResponse:
    # 1. intent awal
    routing = classify_intent(req.question)

    # 2. bangun context dasar
    ctx = build_context(req, routing)

    # 3. memory pendek
    memory = _build_memory(req)

    # 4. override region bila ada eksplisit di pertanyaan
    ctx["region"] = _resolve_effective_region(req, ctx)

    # 5. override intent bila follow-up perlu dibawa
    intent = _carry_intent_from_context(req, routing["intent"], memory)

    # 6. sub-intent
    sub = route_subintent(req, intent, ctx, memory)
    sub_intent = sub["sub_intent"]
    sub_intent_confidence = sub["confidence"]

    # 7. evidence bundle
    bundle = select_evidence_bundle(req, intent, sub_intent, ctx, memory)

    # 8. composer awal
    composed = compose_answer_from_bundle(req, intent, sub_intent, bundle, ctx)

    evidence = bundle.get("evidence", {}) if isinstance(bundle.get("evidence"), dict) else {}
    if not evidence:
        evidence = {
            "intent_match": intent != "fallback",
            "data": bundle.get("data", {}),
            "documents": bundle.get("documents", []),
            "sources": bundle.get("sources", []),
            "trust": bundle.get("trust", {}) or {},
            "missing_core_fields": False,
        }

    # 9. confidence
    confidence = compute_confidence(
        intent=intent,
        evidence=evidence,
        answer_kind="default" if intent != "fallback" else "generic",
    )

    # tambahkan skor internal orchestrator
    scores = {
        "intent_confidence": round(float(routing.get("intent_confidence", 0.70)), 2)
        if isinstance(routing, dict)
        else 0.70,
        "sub_intent_confidence": round(float(sub_intent_confidence), 2),
        "confidence_score": confidence.get("score", 0.50),
    }

    # 10. build response final
    resp = build_ocean_ask_response(
        req=req,
        intent=intent,
        sub_intents=[sub_intent] if sub_intent and sub_intent != "default" else [],
        region=ctx["region"],
        query_type=ctx.get("query_type", "ocean"),
        topics=ctx.get("topics", []),
        answer_block=composed["answer_block"],
        evidence=evidence,
        confidence=confidence,
        explanation=composed.get("explanation", []),
        data_status=composed.get("data_status", {}),
        right_panel=composed.get("right_panel", {}),
        followups=composed.get("followups", []),
    )

    resp.scores = scores
    return resp
