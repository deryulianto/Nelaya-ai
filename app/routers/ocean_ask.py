from __future__ import annotations

from typing import Optional, Any, Dict, List

from fastapi import APIRouter

from app.ai.answer_builder import build_answer
from app.ai.router import route_question
from app.ai.reasoner import run_reasoning
from app.schemas.ocean_ask import OceanAskRequest, OceanAskResponse
from app.services.ocean_data_service import get_fgi_today, get_ocean_today
from app.services.timeseries_service import get_trend_summary
from app.services.regulation_engine import RegulationEngine
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.reference_data_service import (
    count_dataset,
    count_small_islands,
    list_dataset,
    list_small_islands,
    find_nearest_ports,
)

router = APIRouter(prefix="/api/v1/ocean", tags=["Ocean Brain"])

engine = RegulationEngine()
graph_engine = KnowledgeGraphService()


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
        "wppnri",
        "laut andaman",
        "samudera hindia",
        "zona perikanan tangkap",
        "kawasan konservasi",
        "ada berapa wppnri",
        "jumlah wppnri",
    ]

    return any(k in q for k in graph_keywords)


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


def _detect_reference_dataset(question: str) -> str | None:
    q = (question or "").lower()

    if "pulau" in q:
        return "small_islands"
    if "pelabuhan" in q or "port" in q:
        return "ports"
    if "surf" in q or "surfing" in q or "ombak bagus" in q or "spot surfing" in q:
        return "surf_spots"

    return None


def _handle_reference_v2(question: str, region: str | None):
    q = (question or "").lower()
    dataset = _detect_reference_dataset(question)
    if not dataset:
        return None

    label_map = {
        "small_islands": "pulau",
        "ports": "pelabuhan",
        "surf_spots": "lokasi surfing",
    }
    label = label_map[dataset]
    region_label = region or "Aceh"

    # nearest port
    if dataset == "ports" and "terdekat" in q:
        coord_map = {
            "simeulue": (2.6167, 96.0833),
            "banda aceh": (5.55, 95.32),
            "selat malaka": (4.5, 98.0),
            "aceh": (4.5, 96.5),
        }

        key = (region or "aceh").strip().lower()
        lat, lon = coord_map.get(key, (4.5, 96.5))

        res = find_nearest_ports(lat, lon)

        return {
            "ok": True,
            "intent": "reference_data_query",
            "query_type": "nearest_ports",
            "answer": {
                "headline": "Pelabuhan terdekat berhasil ditemukan.",
                "summary": f"Pelabuhan terdekat antara lain: {', '.join([r['name'] for r in res])}.",
                "recommendation": "Gunakan pelabuhan terdekat untuk efisiensi operasional.",
                "caution": "Pastikan kondisi lapangan dan akses aktual sebelum berangkat.",
            },
            "evidence": {
                "items": res,
            },
            "data_status": {
                "dataset": "ports",
                "count": len(res),
            },
        }

    # count queries
    if "berapa" in q or "jumlah" in q or "ada berapa" in q:
        if dataset == "small_islands":
            res = count_small_islands(region)
        else:
            res = count_dataset(dataset, region)

        return {
            "ok": True,
            "intent": "reference_data_query",
            "query_type": f"count_{dataset}",
            "answer": {
                "headline": f"Jumlah {label} di {region_label} sekitar {res['count']}.",
                "summary": f"Berdasarkan data referensi NELAYA-AI, terdapat {res['count']} {label} yang terdata.",
                "recommendation": "Gunakan data ini sebagai gambaran awal untuk analisis wilayah.",
                "caution": "Jumlah dapat berubah tergantung kelengkapan dataset.",
            },
            "evidence": {
                "items": res["items"][:10],
            },
            "data_status": {
                "dataset": dataset,
                "count": res["count"],
            },
        }

    # list queries
    if "apa saja" in q or "daftar" in q or "sebutkan" in q:
        if dataset == "small_islands":
            res = list_small_islands(region, limit=30)
        else:
            res = list_dataset(dataset, region, limit=30)

        items = [str(x) for x in res.get("items", [])]
        sample = ", ".join(items[:12]) if items else "belum ada item yang terbaca"

        return {
            "ok": True,
            "intent": "reference_data_query",
            "query_type": f"list_{dataset}",
            "answer": {
                "headline": f"Daftar {label} di {region_label} berhasil ditemukan.",
                "summary": f"Beberapa {label} yang terdata di {region_label} antara lain: {sample}.",
                "recommendation": "Gunakan daftar ini sebagai pembacaan awal sebelum analisis lanjutan.",
                "caution": "Daftar yang ditampilkan dibatasi agar ringkas di antarmuka.",
            },
            "evidence": {
                "items": items[:20],
            },
            "data_status": {
                "dataset": dataset,
                "count": res.get("count", len(items)),
            },
        }

    return None


def _detect_brain_needs(question: str) -> dict:
    q = (question or "").lower()

    return {
        "needs_ocean": any(k in q for k in [
            "aman melaut",
            "aman",
            "gelombang",
            "ombak",
            "angin",
            "sst",
            "suhu laut",
            "chlorophyll",
            "chl",
            "arus",
            "hari ini",
            "minggu ini",
            "trend",
            "tren",
        ]),
        "needs_reference": any(k in q for k in [
            "pelabuhan",
            "port",
            "pulau",
            "pulau kecil",
            "surf",
            "surfing",
            "spot surfing",
            "lokasi surfing",
        ]),
        "needs_graph": any(k in q for k in [
            "panglima laot",
            "panglima laot lhok",
            "adat laut",
            "wppnri",
            "selat malaka",
            "laut andaman",
            "samudera hindia",
            "apa hubungan",
            "terkait dengan",
        ]),
        "needs_regulation": any(k in q for k in [
            "qanun",
            "peraturan",
            "regulasi",
            "pasal",
            "ayat",
            "izin",
            "dilarang",
            "boleh",
            "tidak boleh",
            "alat tangkap",
            "rumpon",
            "jalur penangkapan",
            "zona penangkapan",
            "konservasi",
            "sipr",
        ]),
    }


def _reference_summary_from_payload(ref_payload: dict) -> str:
    answer = (ref_payload or {}).get("answer", {}) or {}
    headline = answer.get("headline")
    summary = answer.get("summary")
    if headline and summary:
        return f"{headline} {summary}"
    if summary:
        return summary
    if headline:
        return headline
    return "Data referensi ditemukan."


def _graph_summary_from_payload(graph_payload: dict) -> str:
    answer = (graph_payload or {}).get("answer", {}) or {}
    headline = answer.get("headline")
    summary = answer.get("summary")
    if headline and summary:
        return f"{headline} {summary}"
    if summary:
        return summary
    if headline:
        return headline
    return "Relasi pengetahuan ditemukan."


def _reg_summary_from_payload(reg_payload: dict) -> str:
    answer = (reg_payload or {}).get("answer", {}) or {}
    headline = answer.get("headline")
    summary = answer.get("summary")
    if headline and summary:
        return f"{headline} {summary}"
    if summary:
        return summary
    if headline:
        return headline
    return "Jawaban regulasi ditemukan."


def _handle_fusion_query(req: OceanAskRequest):
    needs = _detect_brain_needs(req.question)
    active = [k for k, v in needs.items() if v]

    if len(active) < 2:
        return None

    parts: List[str] = []
    evidence: Dict[str, Any] = {}
    explanations: List[str] = []
    sources: List[Dict[str, Any]] = []

    region = req.region or "Aceh"

    # 1. Ocean brain
    if needs["needs_ocean"]:
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

        ocean_summary = built.get("answer", {}).get("summary") or built.get("answer", {}).get("headline")
        if ocean_summary:
            parts.append(f"Aspek kondisi laut: {ocean_summary}")

        evidence["ocean"] = built.get("evidence", {})
        explanations.extend((built.get("explanation") or [])[:2])

    # 2. Reference brain
    if needs["needs_reference"]:
        ref = _handle_reference_v2(req.question, req.region)
        if ref:
            parts.append(f"Aspek data referensi: {_reference_summary_from_payload(ref)}")
            evidence["reference"] = ref.get("evidence", {})
            explanations.extend((ref.get("explanation") or [])[:1])

    # 3. Knowledge graph brain
    if needs["needs_graph"]:
        graph_answer = graph_engine.answer(req.question)
        if graph_answer:
            graph_payload = {
                "answer": {
                    "headline": graph_answer.get("headline"),
                    "summary": graph_answer.get("summary"),
                }
            }
            parts.append(f"Aspek relasi wilayah: {_graph_summary_from_payload(graph_payload)}")
            evidence["graph"] = {
                "node": graph_answer.get("node"),
                "relations": graph_answer.get("relations", [])[:3],
            }
            explanations.extend((graph_answer.get("relations") or [])[:2])

            for s in graph_answer.get("sources", [])[:2]:
                sources.append(s)

    # 4. Regulation brain
    if needs["needs_regulation"]:
        reg_answer = engine.answer(req.question)
        reg_payload = {
            "answer": {
                "headline": "Jawaban regulasi ditemukan.",
                "summary": reg_answer.get("answer"),
            }
        }
        parts.append(f"Aspek regulasi: {_reg_summary_from_payload(reg_payload)}")
        evidence["regulation"] = {
            "sources": reg_answer.get("sources", [])[:3],
        }
        explanations.append("Jawaban regulasi dipadukan dari basis aturan yang telah diindeks dalam NELAYA-AI.")

        for s in reg_answer.get("sources", [])[:2]:
            sources.append(s)

    if not parts:
        return None

    dedup_sources: List[Dict[str, Any]] = []
    seen = set()
    for s in sources:
        key = (s.get("title"), s.get("pasal"))
        if key in seen:
            continue
        seen.add(key)
        dedup_sources.append(s)

    return {
        "ok": True,
        "question": req.question,
        "intent": "fusion_query",
        "sub_intents": active,
        "region": region,
        "persona": req.persona,
        "mode": req.mode,
        "query_type": "fusion_multi_brain",
        "topics": active,
        "answer": {
            "headline": "Jawaban gabungan berhasil disusun.",
            "summary": "\n\n".join(parts),
            "recommendation": "Gunakan jawaban ini sebagai pembacaan gabungan antara kondisi laut, data referensi, relasi wilayah, dan regulasi bila tersedia.",
            "caution": "Untuk keputusan operasional, tetap padukan dengan pengamatan lapangan dan sumber resmi terkait.",
        },
        "evidence": evidence,
        "scores": {
            "confidence_score": 0.90,
        },
        "explanation": explanations[:5],
        "data_status": {
            "source_type": "fusion",
            "brains": active,
        },
        "sources": dedup_sources[:5],
        "results": [],
    }


@router.post("/ask")
def ask_ocean(req: OceanAskRequest):
    # 0) fusion query dulu
    fusion = _handle_fusion_query(req)
    if fusion:
        return fusion

    # 1) reference data
    ref = _handle_reference_v2(req.question, req.region)
    if ref:
        return ref

    # 2) knowledge graph
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
                    "confidence_score": 0.92,
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

    # 3) regulation
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
                "confidence_score": 0.9 if sources else 0.45,
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

    # 4) ocean brain biasa
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