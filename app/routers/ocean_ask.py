from __future__ import annotations

from fastapi import APIRouter
from typing import Optional, Any, Dict

from app.ai.answer_builder import build_answer
from app.ai.router import route_question
from app.ai.reasoner import run_reasoning
from app.schemas.ocean_ask import OceanAskRequest, OceanAskResponse
from app.services.ocean_data_service import get_fgi_today, get_ocean_today
from app.services.timeseries_service import get_trend_summary
from app.services.regulation_engine import RegulationEngine
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.reference_data_service import count_small_islands, list_small_islands

router = APIRouter(prefix="/api/v1/ocean", tags=["Ocean Brain"])
engine = RegulationEngine()
graph_engine = KnowledgeGraphService()

def _looks_like_reference_query(question: str) -> bool:
    q = (question or "").lower()

    keywords = [
        "pulau",
        "pulau kecil",
        "rumpon",
        "ikan apa",
        "jumlah pulau",
        "berapa pulau",
        "ada berapa pulau",
        "apa saja pulau",
    ]
    return any(k in q for k in keywords)

def _handle_reference_query(question: str, region: str | None = None) -> dict | None:
    q = (question or "").lower()

    if "pulau" in q:
        if "berapa" in q or "jumlah" in q or "ada berapa" in q:
            res = count_small_islands(region=region or "Aceh")
            if not res["found"]:
                return None

            region_label = res["region"] or "Aceh"
            return {
                "ok": True,
                "question": question,
                "intent": "reference_data_query",
                "sub_intents": [],
                "region": region_label,
                "persona": "publik",
                "mode": "ringkas",
                "query_type": "count_small_islands",
                "topics": ["small_islands"],
                "answer": {
                    "headline": f"Jumlah pulau yang terdata di {region_label} adalah {res['count']}.",
                    "summary": (
                        f"Berdasarkan basis data referensi NELAYA-AI, jumlah pulau yang terdata "
                        f"untuk {region_label} saat ini adalah {res['count']}."
                    ),
                    "recommendation": "Gunakan data ini sebagai pembacaan awal dan cocokkan dengan sumber resmi bila diperlukan.",
                    "caution": "Jumlah dapat bergantung pada cakupan dataset dan definisi pulau/pulau kecil yang dipakai.",
                },
                "evidence": {
                    "items": res["items"][:10],
                },
                "scores": {
                    "confidence_score": 0.90
                },
                "explanation": [
                    "Jawaban ini disusun dari basis data referensi terstruktur dalam NELAYA-AI."
                ],
                "data_status": {
                    "source_type": "reference_data",
                    "dataset": "small_islands",
                    "count": res["count"],
                },
                "sources": [],
                "results": [],
            }

        if "apa saja" in q or "sebutkan" in q or "daftar" in q:
            res = list_small_islands(region=region or "Aceh")
            if not res["found"]:
                return None

            region_label = res["region"] or "Aceh"
            sample = ", ".join(res["items"][:12]) if res["items"] else "belum ada nama yang terbaca"

            return {
                "ok": True,
                "question": question,
                "intent": "reference_data_query",
                "sub_intents": [],
                "region": region_label,
                "persona": "publik",
                "mode": "ringkas",
                "query_type": "list_small_islands",
                "topics": ["small_islands"],
                "answer": {
                    "headline": f"Daftar pulau untuk {region_label} berhasil ditemukan.",
                    "summary": (
                        f"Beberapa pulau yang terdata untuk {region_label} antara lain: {sample}."
                    ),
                    "recommendation": "Gunakan daftar ini sebagai pembacaan awal sebelum analisis lanjutan.",
                    "caution": "Daftar yang ditampilkan dibatasi agar ringkas di antarmuka.",
                },
                "evidence": {
                    "items": res["items"][:20],
                },
                "scores": {
                    "confidence_score": 0.90
                },
                "explanation": [
                    "Jawaban ini disusun dari basis data referensi terstruktur dalam NELAYA-AI."
                ],
                "data_status": {
                    "source_type": "reference_data",
                    "dataset": "small_islands",
                    "count": res["count"],
                },
                "sources": [],
                "results": [],
            }

    return None


def _looks_like_graph_query(question: str) -> bool:
    q = (question or "").lower()

    graph_keywords = [
        "panglima laot",
        "panglima laot lhok",
        "adat laut",
        "masyarakat hukum adat laut",
        "apa hubungan",
        "terkait dengan apa",
        "selat malaka",
        "wppnri 571",
        "wppnri 572",
        "laut andaman",
        "samudera hindia",
        "zona perikanan tangkap",
        "kawasan konservasi",
        "ada berapa wppnri",
        "jumlah wppnri",
    ]

    return any(k in q for k in graph_keywords)


def _pick_trend_metric(intent: str, detected_metric: Optional[str]) -> str:
    if detected_metric:
        return detected_metric

    if intent == "safety_check":
        return "wave"
    if intent == "fishing_recommendation":
        return "chlorophyll"
    if intent == "metric_explanation":
        return "sst"
    if intent == "trend_analysis":
        return detected_metric or "sst"
    return "sst"


def _looks_like_regulation_query(question: str) -> bool:
    q = (question or "").lower()

    regulation_keywords = [
        "qanun",
        "peraturan",
        "regulasi",
        "pasal",
        "ayat",
        "izin",
        "dilarang",
        "diperbolehkan",
        "boleh",
        "tidak boleh",
        "rumpon",
        "alat tangkap",
        "penangkapan ikan",
        "jalur penangkapan",
        "zona penangkapan",
        "wppnri",
        "konservasi",
        "rzwp",
        "rzwp3k",
        "permen",
        "pp ",
        "undang-undang",
        "uu ",
        "sipr",
    ]

    return any(k in q for k in regulation_keywords)


@router.post("/ask")
def ask_ocean(req: OceanAskRequest):
    # 0) Pertanyaan knowledge graph
    if _looks_like_graph_query(req.question):
        graph_answer = graph_engine.answer(req.question)
        if graph_answer:
            sources = graph_answer.get("sources", [])
            primary_source = sources[0]["title"] if sources else None
            primary_pasal = sources[0]["pasal"] if sources else None

            return {
                "ok": True,
                "question": req.question,
                "intent": "knowledge_graph_query",
                "sub_intents": [],
                "region": req.region or "Aceh",
                "persona": req.persona,
                "mode": req.mode,
                "query_type": graph_answer.get("query_type", "knowledge_graph_query"),
                "topics": graph_answer.get("topics", []),
                "answer": {
                    "headline": graph_answer.get("headline", "Relasi pengetahuan ditemukan."),
                    "summary": graph_answer.get("summary", "Knowledge graph menemukan relasi yang relevan."),
                    "recommendation": "Gunakan relasi ini sebagai pembacaan awal dan padukan dengan regulasi serta data laut bila diperlukan.",
                    "caution": "Knowledge graph adalah layer pengetahuan terstruktur dan tetap perlu dibaca bersama sumber regulasi atau data utama.",
                },
                "evidence": {
                    "node": graph_answer.get("node"),
                    "relations": graph_answer.get("relations", []),
                },
                "scores": {
                    "confidence_score": 0.92
                },
                "explanation": graph_answer.get("relations", [])[:3],
                "data_status": {
                    "source_type": "knowledge_graph",
                    "nodes": graph_answer.get("stats", {}).get("nodes", 0),
                    "edges": graph_answer.get("stats", {}).get("edges", 0),
                    "query_type": graph_answer.get("query_type", "knowledge_graph_query"),
                    "topics": graph_answer.get("topics", []),
                    "primary_source": primary_source,
                    "primary_pasal": primary_pasal,
                },
                "sources": sources,
                "results": [],
            }

    # 0.5) Pertanyaan reference data
    if _looks_like_reference_query(req.question):
        ref_answer = _handle_reference_query(req.question, req.region or "Aceh")
        if ref_answer:
            return ref_answer

    # 1) Pertanyaan regulasi
    if _looks_like_regulation_query(req.question):
        reg_answer = engine.answer(req.question)
        sources = reg_answer.get("sources", [])
        primary_source = sources[0]["title"] if sources else None
        primary_pasal = sources[0]["pasal"] if sources else None

        return {
            "ok": True,
            "question": req.question,
            "intent": "regulation_query",
            "sub_intents": [],
            "region": req.region or "Aceh",
            "persona": req.persona,
            "mode": req.mode,
            "query_type": reg_answer.get("query_type"),
            "topics": reg_answer.get("topics", []),
            "answer": {
                "headline": "Jawaban regulasi ditemukan.",
                "summary": reg_answer.get("answer", "Belum ada jawaban regulasi yang cukup relevan."),
                "recommendation": "Periksa pasal sumber untuk memastikan konteks hukum yang tepat.",
                "caution": "Jawaban ini adalah pembacaan awal regulasi dan tidak menggantikan penafsiran hukum resmi.",
            },
            "evidence": {},
            "scores": {
                "confidence_score": 0.9 if sources else 0.45
            },
            "explanation": [
                "Jawaban ini disusun dari basis regulasi yang telah diindeks dalam NELAYA-AI."
            ],
            "data_status": {
                "documents": engine.stats().get("documents", 0),
                "articles": engine.stats().get("articles", 0),
                "source_type": "regulations",
                "query_type": reg_answer.get("query_type"),
                "topics": reg_answer.get("topics", []),
                "primary_source": primary_source,
                "primary_pasal": primary_pasal,
            },
            "sources": sources,
            "results": reg_answer.get("results", []),
        }

    # 2) Selain regulasi → Ocean Brain data laut
    parsed = route_question(
        question=req.question,
        region=req.region,
        persona=req.persona,
    )

    region = parsed.get("region") or req.region or "Aceh"
    metric = parsed.get("metric")
    intent = parsed["intent"]

    trend_metric = _pick_trend_metric(intent, metric)

    today = get_ocean_today(region=region, context=req.context)
    fgi = get_fgi_today(region=region)
    trend = get_trend_summary(region=region, metric=trend_metric)

    reasoning = run_reasoning(
        intent=intent,
        today=today,
        fgi=fgi,
        trend=trend,
        persona=req.persona,
        mode=req.mode,
        metric=metric,
        question=req.question,
        region=region,
    )

    built = build_answer(
        question=req.question,
        intent=intent,
        persona=req.persona,
        mode=req.mode,
        region=region,
        today=today,
        fgi=fgi,
        trend=trend,
        reasoning=reasoning,
    )

    return OceanAskResponse(
        ok=True,
        question=req.question,
        intent=intent,
        sub_intents=parsed.get("sub_intents", []),
        region=region,
        persona=req.persona,
        mode=req.mode,
        answer=built["answer"],
        evidence=built["evidence"],
        scores=built["scores"],
        explanation=built["explanation"],
        data_status={
            "date": today.get("date"),
            "generated_at": today.get("generated_at"),
            "stale": today.get("stale", True),
            "completeness": today.get("completeness", "low"),
            "trend_metric": trend_metric,
            "source_type": "ocean_data",
        },
    )


@router.post("/quick-check")
def quick_check(req: OceanAskRequest):
    parsed = route_question(req.question, req.region, req.persona)
    region = parsed.get("region") or req.region or "Aceh"
    trend_metric = "wave"

    today = get_ocean_today(region=region, context=req.context)
    fgi = get_fgi_today(region=region)
    trend = get_trend_summary(region=region, metric=trend_metric)

    reasoning = run_reasoning(
        intent="safety_check",
        today=today,
        fgi=fgi,
        trend=trend,
        persona=req.persona,
        mode="ringkas",
        metric=parsed.get("metric"),
        question=req.question,
        region=region,
    )

    safety_score = reasoning["scores"]["safety_score"]
    confidence_score = reasoning["scores"]["confidence_score"]

    badge = (
        "AMAN" if safety_score >= 0.80 else
        "WASPADA RINGAN" if safety_score >= 0.60 else
        "WASPADA" if safety_score >= 0.40 else
        "BERISIKO"
    )

    headline = (
        "Relatif aman" if safety_score >= 0.80 else
        "Cukup aman" if safety_score >= 0.60 else
        "Perlu waspada" if safety_score >= 0.40 else
        "Cenderung berisiko"
    )

    reason = reasoning["explanation"][0] if reasoning["explanation"] else "Data keselamatan terbatas."

    return {
        "ok": True,
        "headline": headline,
        "badge": badge,
        "reason": reason,
        "confidence": confidence_score,
        "region": region,
        "trend_metric": trend_metric,
    }


@router.get("/stats")
def ocean_stats():
    return {
        "regulations": engine.stats(),
    }


@router.get("/glossary")
def glossary(term: str):
    q = (term or "").strip().lower()

    if q == "fgi":
        return {
            "ok": True,
            "term": "FGI",
            "title": "Fish Ground Index",
            "summary": "Indikator peluang relatif area penangkapan ikan berbasis kombinasi kondisi oseanografi.",
        }

    if q in {"chl", "chlorophyll", "chlorofil"}:
        return {
            "ok": True,
            "term": "Chlorophyll",
            "title": "Chlorophyll",
            "summary": "Indikator produktivitas perairan yang membantu membaca dasar rantai makanan laut.",
        }

    if q in {"sst", "suhu laut"}:
        return {
            "ok": True,
            "term": "SST",
            "title": "Sea Surface Temperature",
            "summary": "Suhu permukaan laut yang membantu membaca dinamika massa air dan kenyamanan habitat.",
        }

    return {
        "ok": True,
        "term": term,
        "title": term,
        "summary": "Istilah belum tersedia di glossary v1.",
    }