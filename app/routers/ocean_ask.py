from __future__ import annotations

from typing import Optional, Any, Dict, List

from fastapi import APIRouter, Body

from app.ai.answer_builder import build_answer
from app.ai.router import route_question
from app.ai.reasoner import run_reasoning
from app.schemas.ocean_ask import OceanAskRequest, OceanAskResponse
from app.services.ocean_data_service import get_fgi_today, get_ocean_today
from app.services.regulation_engine import RegulationEngine
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.reference_data_service import (
    count_dataset,
    count_small_islands,
    list_dataset,
    list_small_islands,
    find_nearest_ports,
    find_nearest_surf_spots,
    resolve_region_center,
)
from app.services.region_resolver_service import resolve_region_spatial
from app.services.ocean_narrative_service import build_ocean_narrative
from app.services.timeseries_service import (
    get_trend_summary,
    compare_this_week_vs_last_week,
    compare_today_vs_yesterday,    
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

    # kalau user sedang menanya kondisi laut, jangan paksa masuk graph
    if _looks_like_ocean_condition_query(q):
        return False

    graph_keywords = [
        "panglima laot",
        "panglima laot lhok",
        "adat laut",
        "masyarakat hukum adat laut",
        "apa hubungan",
        "terkait dengan apa",
        "wppnri",
        "ada berapa wppnri",
        "jumlah wppnri",
        "selat malaka terkait",
        "laut andaman terkait",
        "samudera hindia terkait",
        "zona perikanan tangkap",
        "kawasan konservasi",
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

    center = resolve_region_center(region_label)

    # nearest port
    if dataset == "ports" and "terdekat" in q:
        if not center:
            return None

        lat, lon = center
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
                "resolved_center": {"lat": lat, "lon": lon},
            },
            "data_status": {
                "dataset": "ports",
                "count": len(res),
            },
        }

    # nearest surf spot
    if dataset == "surf_spots" and "terdekat" in q:
        if not center:
            return None

        lat, lon = center
        res = find_nearest_surf_spots(lat, lon)

        return {
            "ok": True,
            "intent": "reference_data_query",
            "query_type": "nearest_surf_spots",
            "answer": {
                "headline": "Lokasi surfing terdekat berhasil ditemukan.",
                "summary": f"Surf spot terdekat antara lain: {', '.join([r['name'] for r in res])}.",
                "recommendation": "Gunakan lokasi terdekat sebagai pembacaan awal sebelum melihat detail ombak dan akses lapangan.",
                "caution": "Kualitas surfing tetap perlu dibaca bersama kondisi ombak, angin, dan akses lokasi.",
            },
            "evidence": {
                "items": res,
                "resolved_center": {"lat": lat, "lon": lon},
            },
            "data_status": {
                "dataset": "surf_spots",
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

def _detect_reference_dataset(question: str) -> str | None:
    q = (question or "").lower()

    if "pulau" in q:
        return "small_islands"
    if "pelabuhan" in q or "port" in q:
        return "ports"
    if "surf" in q or "surfing" in q or "ombak bagus" in q or "spot surfing" in q or "surf spot" in q:
        return "surf_spots"

    return None

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

def _fusion_confidence(needs: dict, evidence: dict) -> float:
    score = 0.55

    if needs.get("needs_ocean") and evidence.get("ocean"):
        score += 0.15
    if needs.get("needs_reference") and evidence.get("reference"):
        score += 0.10
    if needs.get("needs_graph") and evidence.get("graph"):
        score += 0.10
    if needs.get("needs_regulation") and evidence.get("regulation"):
        score += 0.10

    return round(min(score, 0.95), 2)


def _build_fusion_headline(needs: dict, evidence: dict) -> str:
    ocean = evidence.get("ocean", {}) or {}
    ref = evidence.get("reference", {}) or {}
    graph = evidence.get("graph", {}) or {}

    wave = ocean.get("wave_m")
    wind = ocean.get("wind_ms")

    if needs.get("needs_ocean"):
        if wave is not None and wind is not None:
            if wave <= 1.25 and wind <= 5:
                return "Kondisi laut relatif mendukung dan informasi pendukung berhasil dihimpun."
            if wave <= 2.0 and wind <= 8:
                return "Kondisi laut cukup mendukung, dengan beberapa catatan operasional."
            return "Kondisi laut perlu diwaspadai, tetapi informasi pendukung sudah tersedia."
        return "Informasi gabungan berhasil disusun dari beberapa sumber NELAYA-AI."

    if needs.get("needs_graph") and graph:
        return "Relasi wilayah dan informasi pendukung berhasil disusun."

    if needs.get("needs_reference") and ref:
        return "Data referensi berhasil ditemukan."

    return "Jawaban gabungan berhasil disusun."


def _build_fusion_summary(req: OceanAskRequest, needs: dict, evidence: dict) -> str:
    q = (req.question or "").lower()
    region = req.region or "wilayah ini"
  
    ocean = evidence.get("ocean", {}) or {}
    ref = evidence.get("reference", {}) or {}
    graph = evidence.get("graph", {}) or {}
    regulation = evidence.get("regulation", {}) or {}
    spatial = evidence.get("spatial", {})

    if spatial:
        name = spatial.get("name")
        center = spatial.get("center")
        bbox = spatial.get("bbox")

        if center:
            lat, lon = center
            paragraphs.append(
                f"Wilayah {name} secara spasial berada di sekitar koordinat "
                f"{lat:.2f}, {lon:.2f}, memberikan referensi posisi yang lebih presisi."
            )

        if bbox:
            paragraphs.append(
                f"Wilayah ini mencakup rentang area yang cukup luas, "
                f"sehingga kondisi laut dapat bervariasi antar titik di dalamnya."
            )

    paragraphs: List[str] = []

    # ocean
    if needs.get("needs_ocean") and ocean:
        wave = ocean.get("wave_m")
        wind = ocean.get("wind_ms")
        sst = ocean.get("sst_c")

        if "aman melaut" in q:
            if wave is not None and wind is not None:
                paragraphs.append(
                    f"Untuk {region}, tinggi gelombang saat ini sekitar {wave:.2f} m dan angin sekitar {wind:.2f} m/s. "
                    "Ini memberi pembacaan awal bahwa keputusan melaut tetap perlu mempertimbangkan perubahan lapangan."
                )
            elif wave is not None:
                paragraphs.append(
                    f"Untuk {region}, tinggi gelombang saat ini sekitar {wave:.2f} m."
                )
        elif "ombak" in q or "gelombang" in q:
            if wave is not None:
                paragraphs.append(f"Gelombang di {region} saat ini terbaca sekitar {wave:.2f} m.")
        elif "angin" in q and wind is not None:
            paragraphs.append(f"Angin di {region} saat ini sekitar {wind:.2f} m/s.")
        elif sst is not None:
            paragraphs.append(f"Suhu permukaan laut di {region} saat ini sekitar {sst:.2f} °C.")

    # reference
    if needs.get("needs_reference") and ref:
        items = ref.get("items", []) or []

        if "pelabuhan terdekat" in q and items:
            first = items[0]
            if isinstance(first, dict):
                nm = first.get("name", "pelabuhan terdekat")
                dist = first.get("distance_km")
                if dist is not None:
                    paragraphs.append(
                        f"Pelabuhan terdekat yang terbaca dari basis data referensi adalah {nm} "
                        f"dengan perkiraan jarak sekitar {dist:.2f} km."
                    )
                else:
                    paragraphs.append(f"Pelabuhan terdekat yang terbaca adalah {nm}.")
        elif ("surf terdekat" in q or "surf spot terdekat" in q or "lokasi surfing terdekat" in q) and items:
            first = items[0]
            if isinstance(first, dict):
                nm = first.get("name", "surf spot terdekat")
                dist = first.get("distance_km")
                if dist is not None:
                    paragraphs.append(
                        f"Surf spot terdekat yang terbaca dari basis data referensi adalah {nm} "
                        f"dengan perkiraan jarak sekitar {dist:.2f} km."
                    )
                else:
                    paragraphs.append(f"Surf spot terdekat yang terbaca adalah {nm}.")
        elif ("apa saja" in q or "daftar" in q or "sebutkan" in q) and items:
            sample = ", ".join(str(x) for x in items[:8])
            paragraphs.append(
                f"Beberapa data referensi yang relevan untuk {region} antara lain: {sample}."
            )

    # graph
    if needs.get("needs_graph") and graph:
        node = graph.get("node", {}) or {}
        rels = graph.get("relations", []) or []
        node_name = node.get("name")
        if node_name and rels:
            paragraphs.append(
                f"Dari sisi relasi wilayah, {node_name} dalam knowledge graph NELAYA-AI terhubung dengan: {rels[0]}."
            )

    # regulation
    if needs.get("needs_regulation") and regulation:
        srcs = regulation.get("sources", []) or []
        if srcs:
            first = srcs[0]
            title = first.get("title", "dokumen regulasi")
            pasal = first.get("pasal", "")
            suffix = f" {pasal}" if pasal else ""
            paragraphs.append(
                f"Dari sisi regulasi, rujukan utama yang paling dekat untuk pertanyaan ini adalah {title}{suffix}."
            )

    if not paragraphs:
        return "Beberapa sumber pengetahuan NELAYA-AI berhasil dibaca, tetapi ringkasan gabungan belum terbentuk optimal."

    return "\n\n".join(paragraphs)


def _build_fusion_recommendation(req: OceanAskRequest, needs: dict, evidence: dict) -> str:
    q = (req.question or "").lower()
    ocean = evidence.get("ocean", {}) or {}
    ref = evidence.get("reference", {}) or {}

    if "pelabuhan terdekat" in q and ref.get("items"):
        first = ref["items"][0]
        if isinstance(first, dict):
            nm = first.get("name")
            if nm:
                return f"Gunakan informasi kondisi laut bersama akses ke {nm} sebagai pertimbangan operasional awal."

    if "aman melaut" in q and ocean:
        return "Padukan pembacaan ini dengan pengamatan lapangan, prakiraan cuaca, dan rencana titik berangkat yang paling aman."

    return "Gunakan jawaban ini sebagai pembacaan gabungan awal sebelum mengambil keputusan lapangan."


def _build_fusion_caution(needs: dict) -> str:
    if needs.get("needs_ocean") and needs.get("needs_reference"):
        return "Data sistem membantu mempercepat pembacaan awal, tetapi keputusan akhir tetap harus mengikuti kondisi nyata di lapangan."
    if needs.get("needs_regulation"):
        return "Untuk aspek hukum, tetap pastikan konteks pasal dan wilayah penerapan dibaca dari dokumen resmi."
    return "Interpretasi terbaik tetap diperoleh dengan memadukan data sistem dan verifikasi lapangan."

def _build_multi_intent_narrative(
    req: OceanAskRequest,
    evidence: Dict[str, Any],
    needs: dict,
) -> Dict[str, str]:
    q = (req.question or "").lower()
    region = req.region or "wilayah ini"
    persona = (req.persona or "publik").strip().lower()

    ocean = evidence.get("ocean", {}) or {}
    reference = evidence.get("reference", {}) or {}
    graph = evidence.get("graph", {}) or {}
    regulation = evidence.get("regulation", {}) or {}

    parts: List[str] = []

    # 1. Ocean part
    wave = ocean.get("wave_m")
    wind = ocean.get("wind_ms")
    sst = ocean.get("sst_c")
    chl = ocean.get("chl_mg_m3")
    fgi = ocean.get("fgi_score")
    trend = ocean.get("trend")

    if wave is not None and wind is not None:
        parts.append(
            f"Kondisi laut di {region} saat ini menunjukkan gelombang sekitar {wave:.2f} m "
            f"dengan angin sekitar {wind:.2f} m/s."
        )

    if sst is not None and chl is not None:
        parts.append(
            f"Suhu permukaan laut berada di sekitar {sst:.2f} °C "
            f"dengan klorofil sekitar {chl:.2f} mg/m³."
        )

    if fgi is not None:
        if fgi < 0.3:
            parts.append("Indikator peluang ikan masih berada pada level rendah.")
        elif fgi < 0.6:
            parts.append("Indikator peluang ikan berada pada level cukup.")
        else:
            parts.append("Indikator peluang ikan berada pada level tinggi.")

    if trend:
        parts.append(f"Tren kondisi laut saat ini cenderung {trend}.")

    # 2. Reference part
    ref_items = reference.get("items", []) or []

    if "pelabuhan terdekat" in q and ref_items:
        first = ref_items[0]
        if isinstance(first, dict):
            nm = first.get("name", "pelabuhan terdekat")
            dist = first.get("distance_km")
            if dist is not None:
                parts.append(
                    f"Pelabuhan terdekat yang terbaca dari basis data referensi adalah {nm} "
                    f"dengan perkiraan jarak sekitar {dist:.2f} km."
                )
            else:
                parts.append(f"Pelabuhan terdekat yang terbaca adalah {nm}.")
    elif ("surf spot terdekat" in q or "surf terdekat" in q or "lokasi surfing terdekat" in q) and ref_items:
        first = ref_items[0]
        if isinstance(first, dict):
            nm = first.get("name", "surf spot terdekat")
            dist = first.get("distance_km")
            if dist is not None:
                parts.append(
                    f"Surf spot terdekat yang terbaca adalah {nm} "
                    f"dengan perkiraan jarak sekitar {dist:.2f} km."
                )
            else:
                parts.append(f"Surf spot terdekat yang terbaca adalah {nm}.")
    elif ref_items and any(k in q for k in ["apa saja", "daftar", "sebutkan"]):
        sample = ", ".join(str(x) for x in ref_items[:8])
        parts.append(f"Beberapa data referensi yang relevan antara lain: {sample}.")

    # 3. Graph part
    node = graph.get("node", {}) or {}
    rels = graph.get("relations", []) or []
    node_name = node.get("name")
    if node_name and rels:
        parts.append(
            f"Dari sisi relasi wilayah, {node_name} dalam knowledge graph NELAYA-AI "
            f"terhubung dengan: {rels[0]}."
        )

    # 4. Regulation part
    reg_sources = regulation.get("sources", []) or []
    if reg_sources:
        first = reg_sources[0]
        title = first.get("title", "dokumen regulasi")
        pasal = first.get("pasal")
        if pasal:
            parts.append(
                f"Untuk aspek regulasi, rujukan awal yang paling dekat adalah {title} {pasal}."
            )
        else:
            parts.append(
                f"Untuk aspek regulasi, rujukan awal yang paling dekat adalah {title}."
            )

    summary = " ".join(parts) if parts else "Jawaban gabungan berhasil dibentuk dari beberapa komponen pengetahuan NELAYA-AI."

    # Persona-aware headline / recommendation
    if persona == "nelayan":
        headline = "Pembacaan gabungan untuk operasi melaut."
        recommendation = (
            "Gunakan pembacaan ini sebagai dasar awal, lalu cek kondisi angin, gelombang, dan titik berangkat di lapangan sebelum berangkat."
        )
        caution = (
            "Keputusan melaut tetap harus mempertimbangkan perubahan cepat di laut, terutama pada wilayah terbuka."
        )
    elif persona in {"wisata", "surf", "surfer"}:
        headline = "Pembacaan gabungan untuk aktivitas wisata laut."
        recommendation = (
            "Padukan kondisi ombak, angin, dan akses lokasi sebelum menentukan waktu aktivitas di laut."
        )
        caution = (
            "Kondisi laut dapat berubah cepat, sehingga verifikasi lapangan tetap diperlukan."
        )
    elif persona in {"pemerintah", "policy", "pembuat_kebijakan"}:
        headline = "Pembacaan gabungan untuk pemantauan wilayah."
        recommendation = (
            "Gunakan ringkasan ini sebagai pembacaan awal untuk melihat dinamika ruang laut dan kebutuhan tindak lanjut."
        )
        caution = (
            "Interpretasi wilayah luas sebaiknya tidak bertumpu pada satu titik pembacaan saja."
        )
    else:
        headline = "Jawaban gabungan berhasil disusun."
        recommendation = (
            "Gunakan jawaban ini sebagai pembacaan awal sebelum mengambil keputusan lebih lanjut."
        )
        caution = (
            "Padukan data sistem dengan pengamatan lapangan dan sumber resmi yang relevan."
        )

    return {
        "headline": headline,
        "summary": summary,
        "recommendation": recommendation,
        "caution": caution,
    }

def _handle_fusion_query(req: OceanAskRequest):
    needs = _detect_brain_needs(req.question)
    active = [k for k, v in needs.items() if v]

    if len(active) < 2:
        return None

    evidence: Dict[str, Any] = {}
    explanations: List[str] = []
    sources: List[Dict[str, Any]] = []

    region = parsed.get("region") or req.region or "Aceh"

    # spatial resolve
    spatial = resolve_region_spatial(req.region)

    if spatial:
       evidence["spatial"] = spatial

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

        # 🔥 Fusion v9: Narrative Engine
        from app.services.ocean_narrative_service import build_ocean_narrative

        spatial = evidence.get("spatial")  # sudah ada dari fusion sebelumnya

        narrative = build_ocean_narrative(
            region=region,
            today={**today, "fgi_score": fgi.get("fgi_score") if isinstance(fgi, dict) else None,
                   "trend": trend.get("trend") if isinstance(trend, dict) else None},
            spatial=spatial,
        )

        # override hanya bagian "answer"
        built["answer"] = narrative

        # tetap simpan evidence & explanation dari engine lama
        evidence["ocean"] = built.get("evidence", {})
        explanations.extend((built.get("explanation") or [])[:2])

    # 2. Reference brain
    if needs["needs_reference"]:
        ref = _handle_reference_v2(req.question, req.region)
        if ref:
            evidence["reference"] = ref.get("evidence", {})
            explanations.extend((ref.get("explanation") or [])[:1])

    # 3. Graph brain
    if needs["needs_graph"]:
        graph_answer = graph_engine.answer(req.question)
        if graph_answer:
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
        evidence["regulation"] = {
            "sources": reg_answer.get("sources", [])[:3],
        }
        explanations.append("Jawaban regulasi dipadukan dari basis aturan yang telah diindeks dalam NELAYA-AI.")

        for s in reg_answer.get("sources", [])[:2]:
            sources.append(s)

    if not evidence:
        return None

    dedup_sources: List[Dict[str, Any]] = []
    seen = set()
    for s in sources:
        key = (s.get("title"), s.get("pasal"))
        if key in seen:
            continue
        seen.add(key)
        dedup_sources.append(s)

    confidence = _fusion_confidence(needs, evidence)

    narrative = _build_multi_intent_narrative(
        req=req,
        evidence=evidence,
        needs=needs,
    )

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
        "answer": narrative,
        "evidence": evidence,
        "scores": {
            "confidence_score": confidence,
        },
        "explanation": explanations[:5],
        "data_status": {
            "source_type": "fusion",
            "brains": active,
        },
        "sources": dedup_sources[:5],
        "results": [],
    }


def _looks_like_ocean_condition_query(question: str) -> bool:
    q = (question or "").lower()

    ocean_keywords = [
        "kondisi laut",
        "bagaimana kondisi laut",
        "bagaimana laut",
        "aman melaut",
        "aman",
        "gelombang",
        "ombak",
        "angin",
        "arus",
        "sst",
        "suhu laut",
        "chlorophyll",
        "chl",
        "hari ini",
        "minggu ini",
        "tren",
        "trend",
    ]

    return any(k in q for k in ocean_keywords)

def _build_trend_analysis_answer(
    req: OceanAskRequest,
    region: str,
    metric: str | None,
) -> dict:
    q = (req.question or "").lower()
    metric = metric or "sst"

    metric_label_map = {
        "sst": "suhu laut",
        "chlorophyll": "chlorophyll",
        "chl": "chlorophyll",
        "current": "arus",
        "wave": "gelombang",
        "wind": "angin",
        "fgi": "potensi ikan",
    }
    metric_label = metric_label_map.get(metric, metric)

    # default compare: minggu ini vs minggu lalu
    if "minggu ini" in q and "minggu lalu" in q:
        comp = compare_this_week_vs_last_week(region, metric)

        if not comp.get("enough_data"):
            return {
                "ok": True,
                "question": req.question,
                "intent": "trend_analysis",
                "sub_intents": [],
                "region": region,
                "persona": req.persona,
                "mode": req.mode,
                "answer": {
                    "headline": f"Data historis {metric_label} belum cukup untuk perbandingan mingguan.",
                    "summary": f"NELAYA-AI belum menemukan cukup data untuk membandingkan {metric_label} minggu ini dengan minggu lalu di {region}.",
                    "recommendation": "Gunakan data harian terbaru terlebih dahulu sambil melengkapi histori time series.",
                    "caution": "Perbandingan mingguan memerlukan data historis yang cukup dan konsisten.",
                },
                "evidence": comp,
                "scores": {"confidence_score": 0.55},
                "explanation": ["Data historis mingguan belum memadai."],
                "data_status": {"source_type": "csv_timeseries"},
            }

        delta = comp["delta"] or 0.0
        direction = comp["direction"]
        this_week_avg = comp["this_week_avg"]
        last_week_avg = comp["last_week_avg"]

        if metric == "sst":
            if direction == "naik":
                headline = f"{metric_label.capitalize()} minggu ini cenderung lebih hangat."
                summary = (
                    f"Rerata {metric_label} minggu ini di {region} sekitar {this_week_avg:.2f} °C, "
                    f"lebih tinggi dibanding minggu lalu yang sekitar {last_week_avg:.2f} °C. "
                    f"Selisihnya sekitar {abs(delta):.2f} °C, sehingga kondisi minggu ini dapat dibaca lebih panas secara ringan."
                )
            elif direction == "turun":
                headline = f"{metric_label.capitalize()} minggu ini cenderung lebih rendah."
                summary = (
                    f"Rerata {metric_label} minggu ini di {region} sekitar {this_week_avg:.2f} °C, "
                    f"lebih rendah dibanding minggu lalu yang sekitar {last_week_avg:.2f} °C. "
                    f"Selisihnya sekitar {abs(delta):.2f} °C."
                )
            else:
                headline = f"{metric_label.capitalize()} minggu ini relatif stabil."
                summary = (
                    f"Rerata {metric_label} minggu ini di {region} sekitar {this_week_avg:.2f} °C, "
                    f"hampir setara dengan minggu lalu yang sekitar {last_week_avg:.2f} °C. "
                    f"Perubahannya sekitar {abs(delta):.2f} °C, sehingga masih tergolong stabil."
                )
        else:
            if direction == "naik":
                headline = f"{metric_label.capitalize()} minggu ini cenderung meningkat."
            elif direction == "turun":
                headline = f"{metric_label.capitalize()} minggu ini cenderung menurun."
            else:
                headline = f"{metric_label.capitalize()} minggu ini relatif stabil."

            summary = (
                f"Rerata {metric_label} minggu ini di {region} sekitar {this_week_avg:.2f}, "
                f"dibanding minggu lalu sekitar {last_week_avg:.2f}. "
                f"Selisihnya sekitar {abs(delta):.2f} dengan arah {direction}."
            )

        return {
            "ok": True,
            "question": req.question,
            "intent": "trend_analysis",
            "sub_intents": [],
            "region": region,
            "persona": req.persona,
            "mode": req.mode,
            "answer": {
                "headline": headline,
                "summary": summary,
                "recommendation": "Gunakan pembacaan komparatif ini bersama indikator laut lain bila ingin melihat implikasi operasionalnya.",
                "caution": "Perbandingan mingguan menunjukkan kecenderungan umum, bukan kepastian kondisi di setiap titik laut.",
            },
            "evidence": comp,
            "scores": {"confidence_score": 0.9},
            "explanation": [
                f"Perbandingan mingguan menunjukkan arah {direction}.",
            ],
            "data_status": {"source_type": "csv_timeseries"},
        }

    # compare: hari ini vs kemarin
    if "hari ini" in q and "kemarin" in q:
        comp = compare_today_vs_yesterday(region, metric)

        if not comp.get("enough_data"):
            return {
                "ok": True,
                "question": req.question,
                "intent": "trend_analysis",
                "sub_intents": [],
                "region": region,
                "persona": req.persona,
                "mode": req.mode,
                "answer": {
                    "headline": f"Data historis {metric_label} belum cukup untuk perbandingan harian.",
                    "summary": f"NELAYA-AI belum menemukan cukup data untuk membandingkan {metric_label} hari ini dengan kemarin di {region}.",
                    "recommendation": "Gunakan pembacaan kondisi terbaru sambil melengkapi histori harian.",
                    "caution": "Perbandingan harian memerlukan data minimal dua hari yang valid.",
                },
                "evidence": comp,
                "scores": {"confidence_score": 0.55},
                "explanation": ["Data historis harian belum memadai."],
                "data_status": {"source_type": "csv_timeseries"},
            }

        delta = comp["delta"] or 0.0
        direction = comp["direction"]
        today_v = comp["today"]
        yday_v = comp["yesterday"]

        headline = f"{metric_label.capitalize()} hari ini {direction} dibanding kemarin."
        summary = (
            f"Nilai {metric_label} hari ini di {region} sekitar {today_v:.2f}, "
            f"sedangkan kemarin sekitar {yday_v:.2f}. "
            f"Selisihnya sekitar {abs(delta):.2f}, sehingga perubahannya dibaca {direction}."
        )

        return {
            "ok": True,
            "question": req.question,
            "intent": "trend_analysis",
            "sub_intents": [],
            "region": region,
            "persona": req.persona,
            "mode": req.mode,
            "answer": {
                "headline": headline,
                "summary": summary,
                "recommendation": "Padukan pembacaan ini dengan indikator laut lain jika ingin melihat dampaknya terhadap aktivitas lapangan.",
                "caution": "Perbandingan harian dapat berubah cepat bila ada dinamika cuaca atau laut yang kuat.",
            },
            "evidence": comp,
            "scores": {"confidence_score": 0.88},
            "explanation": [
                f"Perbandingan harian menunjukkan arah {direction}.",
            ],
            "data_status": {"source_type": "csv_timeseries"},
        }

    # fallback trend summary
    trend = get_trend_summary(region, metric)
    return {
        "ok": True,
        "question": req.question,
        "intent": "trend_analysis",
        "sub_intents": [],
        "region": region,
        "persona": req.persona,
        "mode": req.mode,
        "answer": {
            "headline": f"Tren {metric_label} berhasil dibaca.",
            "summary": f"Pembacaan tren {metric_label} di {region} saat ini cenderung {trend.get('trend', 'unknown')}.",
            "recommendation": "Gunakan tren ini sebagai pembacaan awal sebelum melihat perbandingan periode yang lebih spesifik.",
            "caution": "Interpretasi tren tetap bergantung pada panjang dan kualitas data historis.",
        },
        "evidence": trend,
        "scores": {"confidence_score": 0.8},
        "explanation": [f"Tren umum saat ini: {trend.get('trend', 'unknown')}."],
        "data_status": {"source_type": "csv_timeseries"},
    }

def _build_fgi_answer(
    req: OceanAskRequest,
    region: str,
    today: Dict[str, Any],
    fgi: Dict[str, Any],
) -> dict:
    score = fgi.get("fgi_score")
    band = fgi.get("band") or "unknown"

    if score is None:
        headline = "FGI belum terbaca dengan cukup kuat."
        summary = (
            f"NELAYA-AI belum menemukan skor FGI yang memadai untuk {region} pada pembacaan ini."
        )
        confidence = 0.55
    else:
        if score >= 0.75:
            headline = "FGI berada pada level tinggi."
            summary = (
                f"Skor Fish Ground Index (FGI) untuk {region} sekitar {score:.3f}, "
                "yang mengarah pada peluang relatif penangkapan ikan yang cukup baik."
            )
        elif score >= 0.50:
            headline = "FGI berada pada level sedang."
            summary = (
                f"Skor Fish Ground Index (FGI) untuk {region} sekitar {score:.3f}, "
                "yang menunjukkan peluang relatif penangkapan ikan berada pada tingkat menengah."
            )
        else:
            headline = "FGI berada pada level rendah."
            summary = (
                f"Skor Fish Ground Index (FGI) untuk {region} sekitar {score:.3f}, "
                "sehingga peluang relatif penangkapan ikan saat ini masih tergolong rendah."
            )
        confidence = 0.90

    return {
        "ok": True,
        "question": req.question,
        "intent": "fgi_indicator",
        "sub_intents": [],
        "region": region,
        "persona": req.persona,
        "mode": req.mode,
        "answer": {
            "headline": headline,
            "summary": summary,
            "recommendation": "Baca FGI bersama suhu laut, klorofil, angin, dan pengamatan lapangan sebelum mengambil keputusan.",
            "caution": "FGI adalah indikator peluang relatif, bukan jaminan hasil tangkapan di setiap titik dan waktu.",
        },
        "evidence": {
            "fgi_score": score,
            "band": band,
            "sst_c": today.get("sst_c"),
            "chl_mg_m3": today.get("chl_mg_m3"),
            "wind_ms": today.get("wind_ms"),
            "wave_m": today.get("wave_m"),
        },
        "scores": {
            "confidence_score": confidence,
        },
        "explanation": [
            "FGI dibaca sebagai indikator peluang relatif area penangkapan ikan.",
            "Interpretasi terbaik dilakukan bersama indikator oseanografi lain.",
        ],
        "data_status": {
            "date": today.get("date"),
            "generated_at": today.get("generated_at"),
            "stale": today.get("stale", True),
            "completeness": today.get("completeness", "low"),
            "source_type": "ocean_data",
        },
    }



@router.post("/ask")
def ask_ocean(req: OceanAskRequest = Body(...)):
    # 0) route utama seawal mungkin
    parsed = route_question(
        question=req.question,
        region=req.region,
        persona=req.persona,
    )

    region = parsed.get("region") or req.region or "Aceh"
    metric = parsed.get("metric")
    intent = parsed["intent"]

    # 1) fusion query dulu
    fusion = _handle_fusion_query(
        OceanAskRequest(
            question=req.question,
            region=region,
            persona=req.persona,
            mode=req.mode,
            context=req.context,
        )
    )
    if fusion:
        return fusion

    # 2) reference data pakai resolved region, bukan req.region mentah
    ref = _handle_reference_v2(req.question, region)
    if ref:
        return ref

    # 3) jalur khusus FGI
    if metric == "fgi" and any(k in (req.question or "").lower() for k in ["fgi", "fish ground index", "potensi ikan"]):
        today = get_ocean_today(region=region, context=req.context)
        fgi = get_fgi_today(region=region)
        return _build_fgi_answer(
            req=req,
            region=region,
            today=today,
            fgi=fgi,
        )

    # 4) trend analysis HARUS keluar lebih awal
    if intent == "trend_analysis":
        return _build_trend_analysis_answer(
            req=req,
            region=region,
            metric=metric,
        )

    # 5) knowledge graph
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
                "region": region,
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

    # 6) regulation
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
            "region": region,
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

    # 7) ocean brain biasa
    trend_metric = _pick_trend_metric(intent, metric)
    spatial = resolve_region_spatial(region)

    today = get_ocean_today(region=region, context=req.context)

    if spatial and spatial.get("bbox"):
        try:
            from app.services.spatial_sampling_service import sample_bbox_points

            points = sample_bbox_points(spatial["bbox"], n=3)
            samples = []

            for lat, lon in points:
                s = get_ocean_today(lat=lat, lon=lon, context=req.context)
                if s:
                    samples.append(s)

            if samples:
                def avg(key: str):
                    vals = [x.get(key) for x in samples if x.get(key) is not None]
                    return sum(vals) / len(vals) if vals else None

                today = {
                    "region": region,
                    "date": samples[0].get("date"),
                    "generated_at": samples[0].get("generated_at"),
                    "sst_c": avg("sst_c"),
                    "chl_mg_m3": avg("chl_mg_m3"),
                    "sal_psu": avg("sal_psu"),
                    "wind_ms": avg("wind_ms"),
                    "wave_m": avg("wave_m"),
                    "ssh_cm": avg("ssh_cm"),
                    "stale": samples[0].get("stale", True),
                    "completeness": samples[0].get("completeness", "low"),
                    "sampling_points": len(samples),
                }
        except Exception:
            pass

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

    if spatial:
        built["evidence"]["spatial"] = spatial

    narrative_today = {
        **today,
        "fgi_score": fgi.get("fgi_score") if isinstance(fgi, dict) else None,
        "trend": trend.get("trend") if isinstance(trend, dict) else None,
    }

    if intent in {"ocean_condition_today", "safety_check", "fishing_recommendation"}:
        built["answer"] = build_ocean_narrative(
            region=region,
            today=narrative_today,
            spatial=spatial,
            persona=req.persona,
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