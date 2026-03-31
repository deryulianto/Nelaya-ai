from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body

from app.schemas.ocean_ask import OceanAskRequest, OceanAskResponse
from app.services.ask_intents import (
    INTENT_OCEAN_CONDITION,
    INTENT_METRIC_EXPLAINER,
    INTENT_SAFETY_CHECK,
    INTENT_TREND_ANALYSIS,
    INTENT_FGI_INDICATOR,
    INTENT_RELATIVE_OPPORTUNITY,
    INTENT_FGI_COMPARE,
    INTENT_REFERENCE_DATA_QUERY,
    INTENT_KNOWLEDGE_ADAT,
    INTENT_REGULATION_QUERY,
    INTENT_OFF_DOMAIN_FEEDBACK,
    INTENT_FALLBACK,
)
from app.services.ask_intent_router import classify_intent
from app.services.ask_context import build_context
from app.services.ask_confidence import compute_confidence
from app.services.ask_response_builder import build_ocean_ask_response

from app.services.ocean_data_service import get_fgi_today, get_ocean_today
from app.services.timeseries_service import (
    get_trend_summary,
    compare_this_week_vs_last_week,
    compare_today_vs_yesterday,
)
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

router = APIRouter(prefix="/api/v1/ocean", tags=["Ocean Brain"])

engine = RegulationEngine()
graph_engine = KnowledgeGraphService()


# =========================================================
# Helper
# =========================================================

def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _pick_first(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _pick_from_today(today: Dict[str, Any], keys: List[str]) -> Any:
    v = _pick_first(today, keys)
    if v is not None:
        return v

    metrics = today.get("metrics") if isinstance(today.get("metrics"), dict) else {}
    if metrics:
        v = _pick_first(metrics, keys)
        if isinstance(v, dict):
            return v.get("value")
        if v is not None:
            return v

    return None


def _extract_ocean_metrics(today: Dict[str, Any], fgi: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    fgi = fgi or {}

    wave = _pick_from_today(today, ["wave_m", "wave_hs_m", "hs_m", "wave"])
    wind = _pick_from_today(today, ["wind_ms", "wind_speed_ms", "wind"])
    sst = _pick_from_today(today, ["sst_c", "sst", "temp_c"])
    chl = _pick_from_today(today, ["chl_mg_m3", "chlorophyll_mg_m3", "chl", "chlorophyll"])
    sal = _pick_from_today(today, ["sal_psu", "salinity_psu", "salinity"])
    ssh = _pick_from_today(today, ["ssh_cm", "ssh", "sea_surface_height_cm"])

    fgi_score = _pick_first(fgi, ["fgi_score", "score", "fgi"])
    band = _pick_first(fgi, ["band", "label"])

    return {
        "wave": wave,
        "wind": wind,
        "sst": sst,
        "chl": chl,
        "sal": sal,
        "ssh": ssh,
        "fgi_score": fgi_score,
        "fgi_band": band,
    }


def _freshness_from_today(today: Dict[str, Any]) -> str:
    stale = today.get("stale", True)
    return "recent" if stale else "fresh"


def _confidence_from_today(today: Dict[str, Any]) -> str:
    completeness = str(today.get("completeness", "low")).lower()
    if completeness in {"high", "full", "complete"}:
        return "high"
    if completeness in {"medium", "moderate"}:
        return "medium"
    return "low"


def _build_ocean_trust(
    today: Dict[str, Any],
    *,
    source: str,
    basis_type: str,
    mode: str,
    caveat: str,
) -> Dict[str, Any]:
    return {
        "source": source,
        "date_utc": today.get("date") or today.get("date_utc"),
        "generated_at": today.get("generated_at") or today.get("meta", {}).get("generated_at"),
        "freshness_status": _freshness_from_today(today),
        "confidence": _confidence_from_today(today),
        "basis_type": basis_type,
        "mode": mode,
        "caveat": caveat,
    }


def _label_wave(wave_m: Optional[float]) -> str:
    if wave_m is None:
        return "belum terbaca"
    if wave_m < 0.5:
        return "rendah"
    if wave_m < 1.5:
        return "rendah-sedang"
    if wave_m < 2.5:
        return "sedang-tinggi"
    return "tinggi"


def _label_wind(wind_ms: Optional[float]) -> str:
    if wind_ms is None:
        return "belum terbaca"
    if wind_ms < 3:
        return "lemah"
    if wind_ms < 6:
        return "lemah-sedang"
    if wind_ms < 10:
        return "sedang-kuat"
    return "kuat"


def _safety_label(wave_m: Optional[float], wind_ms: Optional[float]) -> str:
    if wave_m is None and wind_ms is None:
        return "belum bisa dibaca dengan cukup kuat"
    if (wave_m is not None and wave_m <= 1.25) and (wind_ms is not None and wind_ms <= 5.0):
        return "relatif cukup aman untuk pembacaan umum"
    if (wave_m is not None and wave_m <= 2.0) and (wind_ms is not None and wind_ms <= 8.0):
        return "cukup aman tetapi perlu kewaspadaan"
    return "perlu kewaspadaan lebih tinggi"


def _ocean_drivers(today: Dict[str, Any], metrics: Dict[str, Any]) -> List[str]:
    drivers: List[str] = []

    sst = _safe_float(metrics.get("sst"))
    chl = _safe_float(metrics.get("chl"))
    wind = _safe_float(metrics.get("wind"))
    wave = _safe_float(metrics.get("wave"))

    if sst is not None:
        if sst >= 30.5:
            drivers.append("SST hangat, menandakan perairan permukaan cukup aktif secara termal.")
        elif sst >= 29.0:
            drivers.append("SST berada pada kisaran hangat tropis.")
        else:
            drivers.append("SST relatif moderat dan tidak terlalu menekan kondisi umum.")

    if chl is not None:
        if chl < 0.15:
            drivers.append("Klorofil-a rendah, sehingga dukungan produktivitas permukaan cenderung terbatas.")
        elif chl < 0.5:
            drivers.append("Klorofil-a berada pada level sedang, cukup mendukung tetapi belum menonjol.")
        else:
            drivers.append("Klorofil-a relatif tinggi dan mendukung produktivitas permukaan lebih baik.")

    if wave is not None:
        drivers.append(f"Gelombang relatif {_label_wave(wave)}, sehingga dinamika permukaan tidak terlalu menekan kondisi umum.")

    if wind is not None:
        drivers.append(f"Angin {_label_wind(wind)}, sehingga tekanan atmosferik permukaan tidak terlalu dominan.")

    return drivers[:4]


def _fgi_drivers(metrics: Dict[str, Any]) -> List[str]:
    drivers: List[str] = []

    score = _safe_float(metrics.get("fgi_score"))
    band = str(metrics.get("fgi_band") or "unknown")
    sst = _safe_float(metrics.get("sst"))
    chl = _safe_float(metrics.get("chl"))
    sal = _safe_float(metrics.get("sal"))

    if score is not None:
        drivers.append(f"Skor FGI env saat ini sekitar {score:.3f} dan berada pada band {band}.")

    if sst is not None:
        if sst >= 30.5:
            drivers.append("Suhu permukaan laut cenderung sangat hangat, yang pada beberapa kondisi dapat menekan kecocokan habitat permukaan.")
        else:
            drivers.append("Suhu permukaan laut masih berada pada kisaran yang relatif mendukung kondisi tropis.")

    if chl is not None:
        if chl < 0.15:
            drivers.append("Klorofil-a masih rendah, sehingga dukungan pakan alami permukaan belum kuat.")
        elif chl < 0.5:
            drivers.append("Klorofil-a berada pada tingkat sedang, cukup mendukung tetapi belum terlalu kuat.")
        else:
            drivers.append("Klorofil-a relatif tinggi dan mendukung produktivitas permukaan lebih baik.")

    if sal is not None:
        if 30 <= sal <= 35:
            drivers.append("Salinitas berada pada kisaran laut terbuka yang relatif stabil.")
        else:
            drivers.append("Salinitas berada di luar kisaran ideal umum dan dapat memengaruhi pembacaan skor.")

    return drivers[:4]


def _base_right_panel(cards: List[Dict[str, Any]], trust: Dict[str, Any], title: str) -> Dict[str, Any]:
    return {
        "title": title,
        "cards": cards,
        "trust": trust,
    }

def _resolve_effective_region(req: OceanAskRequest, ctx: Dict[str, Any]) -> str:
    """
    Prioritas region:
    1. jika pertanyaan menyebut wilayah eksplisit -> pakai itu
    2. jika tidak, pakai field wilayah dari form
    """
    q = (req.question or "").lower().strip()

    # urutkan dari yang lebih spesifik dulu bila perlu
    region_aliases = [
        ("banda aceh", "Banda Aceh"),
        ("aceh besar", "Aceh Besar"),
        ("aceh barat", "Aceh Barat"),
        ("aceh barat daya", "Aceh Barat Daya"),
        ("aceh jaya", "Aceh Jaya"),
        ("aceh selatan", "Aceh Selatan"),
        ("aceh singkil", "Aceh Singkil"),
        ("singkil", "Singkil"),
        ("aceh tamiang", "Aceh Tamiang"),
        ("aceh tengah", "Aceh Tengah"),
        ("aceh tenggara", "Aceh Tenggara"),
        ("aceh timur", "Aceh Timur"),
        ("aceh utara", "Aceh Utara"),
        ("pidie", "Pidie"),
        ("pidie jaya", "Pidie Jaya"),
        ("bener meriah", "Bener Meriah"),
        ("bieureuen", "Bireuen"),
        ("bireuen", "Bireuen"),
        ("gayo lues", "Gayo Lues"),
        ("nagan raya", "Nagan Raya"),
        ("aceh tamiang", "Aceh Tamiang"),
        ("subulussalam", "Subulussalam"),
        ("lhokseumawe", "Lhokseumawe"),
        ("langsa", "Langsa"),
        ("sabang", "Sabang"),
        ("simeulue", "Simeulue"),
        ("aceh", "Aceh"),
        ("tamiang", "Tamiang"),
    ]

    for needle, canonical in region_aliases:
        if f"di {needle}" in q or f"wilayah {needle}" in q or q.endswith(needle) or f" {needle} " in f" {q} ":
            return canonical

    return ctx["region"]

def _normalize_text(s: Any) -> str:
    return str(s or "").strip().lower()


def _looks_like_regulation_followup(req: OceanAskRequest) -> bool:
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
    ]
    return any(m in q for m in markers)


def _carry_intent_from_context(req: OceanAskRequest, detected_intent: str) -> str:
    """
    Jika pertanyaan sekarang berupa follow-up regulasi, dan pertanyaan sebelumnya
    memang regulasi, maka jangan jatuh ke fallback.
    """
    ctx = req.context or {}
    last_intent = _normalize_text(ctx.get("last_intent"))
    last_query_type = _normalize_text(ctx.get("last_query_type"))
    has_last_source = bool(ctx.get("last_primary_source"))

    if detected_intent == INTENT_FALLBACK and _looks_like_regulation_followup(req):
        if last_intent == INTENT_REGULATION_QUERY:
            return INTENT_REGULATION_QUERY
        if last_query_type == "knowledge" and has_last_source:
            return INTENT_REGULATION_QUERY

    return detected_intent


def _detect_regulation_subintent(req: OceanAskRequest) -> str:
    q = _normalize_text(req.question)

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
        return "regulation_compliance"
    if any(m in q for m in scope_markers):
        return "regulation_scope"
    return "regulation_explainer"


def _compose_regulation_scope_answer(req: OceanAskRequest, reg_answer: Dict[str, Any], sources: List[Dict[str, Any]]) -> Dict[str, str]:
    ctx = req.context or {}
    last_region = ctx.get("last_region")
    primary_source = ctx.get("last_primary_source") or (sources[0]["title"] if sources else None)
    primary_pasal = ctx.get("last_primary_pasal") or (sources[0].get("pasal") if sources else None)

    if primary_source:
        summary = (
            f"Pembacaan awal menunjukkan pertanyaan tentang wilayah berlaku harus dibaca dari cakupan dokumen utama, "
            f"yaitu {primary_source}"
        )
        if primary_pasal:
            summary += f" ({primary_pasal})"
        summary += ". "
    else:
        summary = (
            "Wilayah berlaku aturan ini belum bisa ditegaskan penuh hanya dari pertanyaan lanjutan, "
            "tetapi tetap perlu dibaca dari ruang lingkup dokumen sumbernya. "
        )

    if last_region:
        summary += f"Konteks percakapan sebelumnya terbaca terkait wilayah {last_region}. "

    summary += (
        "Untuk memastikan wilayah berlakunya, baca bagian ruang lingkup, objek yang diatur, "
        "serta pasal yang relevan pada dokumen sumber."
    )

    return {
        "headline": "Cakupan wilayah aturan berhasil dibaca.",
        "summary": summary,
        "recommendation": "Periksa dokumen utama dan pasal sumber untuk memastikan ruang berlaku aturan secara tepat.",
        "caution": "Ini adalah pembacaan awal cakupan aturan, bukan penafsiran hukum final.",
    }


def _compose_regulation_compliance_answer(req: OceanAskRequest, reg_answer: Dict[str, Any], sources: List[Dict[str, Any]]) -> Dict[str, str]:
    q = _normalize_text(req.question)
    primary_source = sources[0]["title"] if sources else None
    primary_pasal = sources[0].get("pasal") if sources else None

    if "bom" in q:
        verdict = "Tidak boleh."
        summary = (
            "Menangkap ikan dengan bom tidak boleh. Ini termasuk praktik destruktif yang merusak sumber daya ikan "
            "dan harus dibaca dalam kerangka larangan penggunaan cara atau alat yang merusak."
        )
    elif "setrum" in q:
        verdict = "Tidak boleh."
        summary = (
            "Menangkap ikan dengan setrum tidak boleh. Ini termasuk praktik yang merusak dan tidak dapat dibenarkan "
            "sebagai cara penangkapan ikan yang aman dan berkelanjutan."
        )
    elif "racun" in q or "potas" in q:
        verdict = "Tidak boleh."
        summary = (
            "Menangkap ikan dengan racun atau bahan berbahaya tidak boleh. Ini termasuk praktik yang merusak ekosistem "
            "dan bertentangan dengan pengelolaan perikanan yang benar."
        )
    elif "alat tangkap yang dilarang" in q or "jenis alat tangkap yang dilarang" in q:
        verdict = "Perlu dibaca sebagai daftar larangan dan pembatasan."
        summary = (
            "Jenis alat tangkap yang dilarang atau dibatasi harus dibaca dari dokumen sumber yang mengatur klasifikasi alat tangkap, "
            "termasuk yang diperbolehkan, dibatasi, dan dilarang."
        )
    else:
        verdict = "Perlu dibaca dari dasar regulasi."
        summary = reg_answer.get("answer") or "Jawaban kepatuhan belum dapat ditegaskan penuh dari pembacaan awal."

    if primary_source:
        summary += f" Rujukan utamanya saat ini adalah {primary_source}"
        if primary_pasal:
            summary += f" ({primary_pasal})."

    return {
        "headline": f"{verdict} Jawaban regulasi ditemukan.",
        "summary": summary,
        "recommendation": "Periksa pasal sumber untuk memastikan konteks hukum yang tepat.",
        "caution": "Untuk penggunaan formal, tetap baca dokumen asli dan konteks pasalnya.",
    }

# =========================================================
# Handlers
# =========================================================

def _handle_ocean_condition(req: OceanAskRequest, ctx: Dict[str, Any]) -> OceanAskResponse:
    region = ctx["region"]
    metric = ctx.get("metric")

    today = get_ocean_today(region=region, context=req.context) or {}
    fgi = get_fgi_today(region=region) or {}
    trend = get_trend_summary(region=region, metric=metric or "sst") or {}

    metrics = _extract_ocean_metrics(today, fgi)
    drivers = _ocean_drivers(today, metrics)

    evidence = {
        "intent_match": True,
        "data": {
            "wave_m": metrics["wave"],
            "wind_ms": metrics["wind"],
            "sst_c": metrics["sst"],
            "chl_mg_m3": metrics["chl"],
            "sal_psu": metrics["sal"],
            "ssh_cm": metrics["ssh"],
            "fgi_score": metrics["fgi_score"],
            "trend": trend.get("trend"),
        },
        "wave_m": metrics["wave"],
        "wind_ms": metrics["wind"],
        "sst_c": metrics["sst"],
        "chl_mg_m3": metrics["chl"],
        "sal_psu": metrics["sal"],
        "ssh_cm": metrics["ssh"],
        "fgi_score": metrics["fgi_score"],
        "explain": {
            "drivers": drivers,
        },
        "trust": _build_ocean_trust(
            today,
            source="Earth / Laut Hari Ini",
            basis_type="derived_daily_ocean_snapshot",
            mode="daily-synthesis",
            caveat="Ini adalah ringkasan sintesis kondisi laut harian, bukan pengukuran langsung seluruh kesehatan ekosistem.",
        ),
        "sources": [],
        "missing_core_fields": sum(
            1 for x in [metrics["wave"], metrics["wind"], metrics["sst"], metrics["chl"]]
            if x is None
        ) >= 3,
    }

    confidence = compute_confidence(
        intent=INTENT_OCEAN_CONDITION,
        evidence=evidence,
        answer_kind="default",
    )

    q = (req.question or "").lower()
    wave = _safe_float(metrics["wave"])
    wind = _safe_float(metrics["wind"])

    if metric == "wave" or "gelombang" in q or "ombak" in q:
        headline = f"Gelombang {region} hari ini berhasil dibaca."
        if wave is not None:
            summary = (
                f"Tinggi gelombang untuk pembacaan umum {region} hari ini sekitar {wave:.2f} m "
                f"dan berada pada level {_label_wave(wave)}."
            )
        else:
            summary = f"Tinggi gelombang {region} hari ini belum terbaca cukup kuat."
    else:
        headline = f"Kondisi laut {region} hari ini berhasil dibaca."
        summary = (
            f"Secara umum, kondisi laut {region} hari ini relatif stabil, "
            f"dengan gelombang {_label_wave(wave)} dan angin {_label_wind(wind)}."
        )

    answer_block = {
        "headline": headline,
        "summary": summary,
        "recommendation": "Gunakan pembacaan ini sebagai dasar awal sebelum melihat detail ombak, FGI, atau OSI.",
        "caution": "Kondisi spot lokal dapat berbeda dari pembacaan wilayah umum.",
    }

    right_panel = _base_right_panel(
        [
            {"label": "Gelombang", "value": metrics["wave"], "unit": "m"},
            {"label": "Angin", "value": metrics["wind"], "unit": "m/s"},
            {"label": "SST", "value": metrics["sst"], "unit": "°C"},
            {"label": "Klorofil-a", "value": metrics["chl"], "unit": "mg/m³"},
            {"label": "FGI", "value": metrics["fgi_score"], "unit": ""},
        ],
        evidence["trust"],
        "Kondisi laut hari ini",
    )

    return build_ocean_ask_response(
        req=req,
        intent=INTENT_OCEAN_CONDITION,
        sub_intents=[],
        region=region,
        query_type=ctx["query_type"],
        topics=ctx["topics"],
        answer_block=answer_block,
        evidence=evidence,
        confidence=confidence,
        explanation=drivers,
        data_status={
            "date": today.get("date") or today.get("date_utc"),
            "generated_at": today.get("generated_at") or today.get("meta", {}).get("generated_at"),
            "stale": today.get("stale", True),
            "completeness": today.get("completeness", "low"),
            "trend_metric": metric or "sst",
            "source_type": "ocean_data",
        },
        right_panel=right_panel,
        followups=[
            "Apa yang paling berubah hari ini?",
            "Apakah ombak hari ini aman?",
            "Mengapa klorofil-a rendah?",
        ],
    )


def _handle_metric_explainer(req: OceanAskRequest, ctx: Dict[str, Any]) -> OceanAskResponse:
    region = _resolve_effective_region(req, ctx)
    metric = ctx.get("metric")

    today = get_ocean_today(region=region, context=req.context) or {}
    fgi = get_fgi_today(region=region) or {}
    metrics = _extract_ocean_metrics(today, fgi)

    q = (req.question or "").lower()
    drivers: List[str] = []
    headline = "Penjelasan metrik berhasil dibaca."
    summary = "Ringkasan metrik belum cukup spesifik."
    answer_kind = "generic"

    # =========================
    # SST / suhu laut
    # =========================
    if metric == "sst":
        sst = _safe_float(metrics["sst"])
        ask_value = ("berapa" in q) or ("rata-rata" in q) or ("rata rata" in q)
        ask_reason = ("mengapa" in q) or ("kenapa" in q)

        if ask_value:
            headline = f"Suhu laut {region} berhasil dibaca."
            if sst is None:
                summary = f"Suhu permukaan laut rata-rata pembacaan wilayah {region} belum terbaca cukup kuat."
                answer_kind = "generic"
            else:
                summary = (
                    f"Suhu permukaan laut rata-rata pembacaan wilayah {region} saat ini sekitar {sst:.2f} °C."
                )
                answer_kind = "default"

            drivers = [
                "Nilai ini adalah pembacaan rata-rata wilayah pada snapshot data yang tersedia.",
                "SST membantu membaca kondisi termal permukaan laut.",
                "Interpretasinya paling baik jika dipadukan dengan klorofil-a, angin, dan gelombang.",
            ]

        elif ask_reason:
            headline = f"Suhu laut {region} berhasil dijelaskan."
            if sst is None:
                summary = f"Suhu permukaan laut untuk {region} belum terbaca cukup kuat."
                answer_kind = "generic"
            else:
                summary = (
                    f"Suhu permukaan laut {region} saat ini sekitar {sst:.2f} °C. "
                    f"Nilai ini menunjukkan kondisi termal permukaan laut yang perlu dibaca bersama dinamika musim, angin, dan pencampuran massa air."
                )
                answer_kind = "default"

            drivers = [
                "SST dipengaruhi oleh pemanasan matahari, dinamika musim, dan pencampuran massa air.",
                "Pada wilayah tropis seperti Aceh, suhu permukaan laut cenderung hangat sepanjang tahun.",
                "Pembacaan ini adalah kondisi permukaan, bukan seluruh kolom air.",
            ]
        else:
            headline = "SST berhasil dijelaskan."
            if sst is None:
                summary = f"Suhu permukaan laut untuk {region} belum terbaca cukup kuat."
                answer_kind = "generic"
            else:
                summary = (
                    f"SST adalah suhu permukaan laut. Di {region}, nilainya saat ini sekitar {sst:.2f} °C dan membantu membaca dinamika massa air serta kenyamanan habitat."
                )
                answer_kind = "default"

            drivers = [
                "SST membantu membaca kondisi termal permukaan laut.",
                "Interpretasinya perlu dipadukan dengan klorofil-a dan dinamika angin/gelombang.",
            ]

    # =========================
    # Klorofil-a
    # =========================
    elif metric == "chl":
        chl = _safe_float(metrics["chl"])
        ask_value = ("berapa" in q) or ("rata-rata" in q) or ("rata rata" in q)
        ask_reason = ("mengapa" in q) or ("kenapa" in q)

        if ask_value:
            headline = f"Klorofil-a {region} berhasil dibaca."
            if chl is None:
                summary = f"Nilai klorofil-a untuk {region} belum terbaca cukup kuat."
                answer_kind = "generic"
            else:
                summary = (
                    f"Klorofil-a rata-rata pembacaan wilayah {region} saat ini sekitar {chl:.3f} mg/m³."
                )
                answer_kind = "default"

            drivers = [
                "Nilai ini membantu membaca produktivitas perairan permukaan.",
                "Interpretasi terbaik didapat bila dibaca bersama suhu laut dan angin.",
            ]

        elif ask_reason:
            headline = f"Klorofil-a {region} berhasil dijelaskan."
            if chl is None:
                summary = f"Nilai klorofil-a untuk {region} belum terbaca cukup kuat."
                answer_kind = "generic"
            elif chl < 0.15:
                summary = (
                    f"Klorofil-a di {region} saat ini tergolong rendah. Ini biasanya menandakan dukungan produktivitas permukaan belum kuat."
                )
                answer_kind = "default"
            elif chl < 0.5:
                summary = (
                    f"Klorofil-a di {region} berada pada tingkat sedang. Artinya produktivitas permukaan ada, tetapi belum terlalu kuat."
                )
                answer_kind = "default"
            else:
                summary = (
                    f"Klorofil-a di {region} relatif tinggi, yang berarti dukungan produktivitas permukaan cenderung lebih baik."
                )
                answer_kind = "default"

            drivers = [
                "Klorofil-a adalah indikator produktivitas permukaan perairan.",
                "Ini adalah pembacaan permukaan, bukan keseluruhan kondisi rantai makanan laut.",
            ]
        else:
            headline = "Klorofil-a berhasil dijelaskan."
            if chl is None:
                summary = f"Nilai klorofil-a untuk {region} belum terbaca cukup kuat."
                answer_kind = "generic"
            else:
                summary = (
                    f"Klorofil-a membantu membaca produktivitas permukaan. Di {region}, nilainya saat ini sekitar {chl:.3f} mg/m³."
                )
                answer_kind = "default"

            drivers = [
                "Klorofil-a rendah berarti pakan alami permukaan belum menonjol.",
                "Klorofil-a sedang hingga tinggi menunjukkan produktivitas permukaan lebih aktif.",
            ]

    # =========================
    # SSH
    # =========================
    elif metric == "ssh":
        ssh = _safe_float(metrics["ssh"])
        headline = "SSH berhasil dijelaskan."
        if ssh is None:
            summary = f"Data muka laut permukaan untuk {region} belum terbaca cukup kuat."
            answer_kind = "generic"
        else:
            summary = (
                f"SSH adalah tinggi muka laut permukaan. Di {region}, pembacaan saat ini sekitar {ssh:.2f} cm dan dipakai sebagai sinyal tambahan untuk membaca dinamika regional."
            )
            answer_kind = "default"

        drivers = [
            "SSH membantu membaca variasi muka laut permukaan regional.",
            "Interpretasinya tidak berdiri sendiri dan perlu dibaca bersama sinyal laut lainnya.",
        ]

    else:
        summary = "Pertanyaan metrik ini belum didukung penuh pada tahap MVP."
        drivers = ["Coba tanyakan metrik yang lebih spesifik seperti suhu laut, klorofil-a, atau SSH."]

    evidence = {
        "intent_match": True,
        "data": {
            "wave_m": metrics["wave"],
            "wind_ms": metrics["wind"],
            "sst_c": metrics["sst"],
            "chl_mg_m3": metrics["chl"],
            "ssh_cm": metrics["ssh"],
            "fgi_score": metrics["fgi_score"],
        },
        "wave_m": metrics["wave"],
        "wind_ms": metrics["wind"],
        "sst_c": metrics["sst"],
        "chl_mg_m3": metrics["chl"],
        "ssh_cm": metrics["ssh"],
        "fgi_score": metrics["fgi_score"],
        "explain": {"drivers": drivers},
        "trust": _build_ocean_trust(
            today,
            source="Earth / Penjelasan metrik",
            basis_type="metric_explainer",
            mode="explanation",
            caveat="Penjelasan ini adalah pembacaan awal berbasis data dan heuristik domain, bukan penjelasan kausal final.",
        ),
        "sources": [],
        "missing_core_fields": False,
    }

    confidence = compute_confidence(
        intent=INTENT_METRIC_EXPLAINER,
        evidence=evidence,
        answer_kind=answer_kind,
    )

    right_panel = _base_right_panel(
        [
            {"label": "SST", "value": metrics["sst"], "unit": "°C"},
            {"label": "Klorofil-a", "value": metrics["chl"], "unit": "mg/m³"},
            {"label": "Gelombang", "value": metrics["wave"], "unit": "m"},
            {"label": "Angin", "value": metrics["wind"], "unit": "m/s"},
            {"label": "FGI", "value": metrics["fgi_score"], "unit": ""},
        ],
        evidence["trust"],
        "Penjelasan metrik",
    )

    return build_ocean_ask_response(
        req=req,
        intent=INTENT_METRIC_EXPLAINER,
        sub_intents=[],
        region=region,
        query_type=ctx["query_type"],
        topics=ctx["topics"],
        answer_block={
            "headline": headline,
            "summary": summary,
            "recommendation": "Gunakan penjelasan ini bersama pembacaan kondisi laut secara keseluruhan.",
            "caution": "Pembacaan metrik tunggal tidak cukup untuk menggambarkan seluruh kondisi laut.",
        },
        evidence=evidence,
        confidence=confidence,
        explanation=drivers,
        data_status={
            "date": today.get("date") or today.get("date_utc"),
            "generated_at": today.get("generated_at") or today.get("meta", {}).get("generated_at"),
            "stale": today.get("stale", True),
            "completeness": today.get("completeness", "low"),
            "source_type": "ocean_data",
        },
        right_panel=right_panel,
        followups=[
            "Bagaimana kondisi laut hari ini?",
            "Mengapa FGI rendah?",
            "Bagaimana ketinggian gelombang hari ini?",
        ],
    )


def _handle_safety_check(req: OceanAskRequest, ctx: Dict[str, Any]) -> OceanAskResponse:
    region = ctx["region"]

    today = get_ocean_today(region=region, context=req.context) or {}
    trend = get_trend_summary(region=region, metric="wave") or {}
    metrics = _extract_ocean_metrics(today, None)

    wave_m = _safe_float(metrics["wave"])
    wind_ms = _safe_float(metrics["wind"])
    safety_label = _safety_label(wave_m, wind_ms)

    drivers: List[str] = []
    if wave_m is not None:
        drivers.append(f"Tinggi gelombang terbaca sekitar {wave_m:.2f} m.")
    if wind_ms is not None:
        drivers.append(f"Kecepatan angin terbaca sekitar {wind_ms:.2f} m/s.")
    drivers.append(f"Tren gelombang saat ini cenderung {trend.get('trend', 'unknown')}.")

    evidence = {
        "intent_match": True,
        "data": {
            "wave_m": wave_m,
            "wind_ms": wind_ms,
            "sst_c": metrics["sst"],
            "chl_mg_m3": metrics["chl"],
            "fgi_score": metrics["fgi_score"],
            "safety_label": safety_label,
            "trend": trend.get("trend"),
        },
        "wave_m": wave_m,
        "wind_ms": wind_ms,
        "sst_c": metrics["sst"],
        "chl_mg_m3": metrics["chl"],
        "fgi_score": metrics["fgi_score"],
        "explain": {
            "drivers": drivers,
        },
        "trust": _build_ocean_trust(
            today,
            source="Surf / Kondisi Gelombang",
            basis_type="model_snapshot",
            mode="safety-check",
            caveat="Ini pembacaan umum wilayah. Spot lokal, kapal kecil, dan perubahan cuaca cepat tetap harus dipantau di lapangan.",
        ),
        "sources": [],
        "missing_core_fields": sum(1 for x in [wave_m, wind_ms] if x is None) >= 1,
    }

    confidence = compute_confidence(
        intent=INTENT_SAFETY_CHECK,
        evidence=evidence,
        answer_kind="default",
    )

    answer_block = {
        "headline": f"Pembacaan keselamatan melaut untuk {region}.",
        "summary": (
            f"Untuk pembacaan umum, kondisi hari ini {safety_label}. "
            f"Gelombang berada pada level {_label_wave(wave_m)} dengan angin {_label_wind(wind_ms)}."
        ),
        "recommendation": "Gunakan pembacaan ini bersama pengamatan nahkoda, kondisi kapal, dan prakiraan cuaca sebelum berangkat.",
        "caution": "Keputusan melaut tetap harus mengikuti kondisi nyata di lapangan, terutama di perairan terbuka.",
    }

    right_panel = _base_right_panel(
        [
            {"label": "Gelombang", "value": wave_m, "unit": "m"},
            {"label": "Angin", "value": wind_ms, "unit": "m/s"},
            {"label": "SST", "value": metrics["sst"], "unit": "°C"},
            {"label": "Klorofil-a", "value": metrics["chl"], "unit": "mg/m³"},
            {"label": "FGI", "value": metrics["fgi_score"], "unit": ""},
        ],
        evidence["trust"],
        "Keamanan relatif melaut",
    )

    return build_ocean_ask_response(
        req=req,
        intent=INTENT_SAFETY_CHECK,
        sub_intents=[],
        region=region,
        query_type=ctx["query_type"],
        topics=ctx["topics"],
        answer_block=answer_block,
        evidence=evidence,
        confidence=confidence,
        explanation=drivers,
        data_status={
            "date": today.get("date") or today.get("date_utc"),
            "generated_at": today.get("generated_at") or today.get("meta", {}).get("generated_at"),
            "stale": today.get("stale", True),
            "completeness": today.get("completeness", "low"),
            "trend_metric": "wave",
            "source_type": "ocean_data",
        },
        right_panel=right_panel,
        followups=[
            "Bagaimana tren gelombang minggu ini?",
            "Berapa tinggi gelombang hari ini?",
            "Laut Aceh hari ini bagaimana?",
        ],
    )


def _handle_trend_analysis(req: OceanAskRequest, ctx: Dict[str, Any]) -> OceanAskResponse:
    region = ctx["region"]
    metric = ctx.get("metric") or "wave"
    q = (req.question or "").lower()

    metric_label_map = {
        "sst": "suhu laut",
        "chl": "klorofil-a",
        "wave": "gelombang",
        "wind": "angin",
        "fgi": "potensi ikan",
        "current": "arus",
    }
    metric_label = metric_label_map.get(metric, metric)

    if "minggu ini" in q and "minggu lalu" in q:
        comp = compare_this_week_vs_last_week(region, metric) or {}
        enough = bool(comp.get("enough_data"))
        direction = comp.get("direction", "unknown")

        evidence = {
            "intent_match": True,
            "data": comp,
            "trust": {
                "source": "Time series / Perbandingan mingguan",
                "date_utc": None,
                "generated_at": None,
                "freshness_status": "unknown",
                "confidence": "high" if enough else "low",
                "basis_type": "trend_compare",
                "mode": "trend-analysis",
                "caveat": "Perbandingan mingguan menunjukkan kecenderungan umum, bukan kepastian kondisi di setiap titik laut.",
            },
            "sources": [],
            "missing_core_fields": not enough,
        }

        confidence = compute_confidence(
            intent=INTENT_TREND_ANALYSIS,
            evidence=evidence,
            answer_kind="default" if enough else "generic",
        )

        if enough:
            summary = (
                f"Rerata {metric_label} minggu ini di {region} sekitar {comp.get('this_week_avg', 0):.2f}, "
                f"dibanding minggu lalu sekitar {comp.get('last_week_avg', 0):.2f}. "
                f"Arahnya cenderung {direction}."
            )
            explanation = [f"Perbandingan mingguan menunjukkan arah {direction}."]
        else:
            summary = f"Data historis {metric_label} belum cukup untuk perbandingan mingguan di {region}."
            explanation = ["Data historis mingguan belum memadai."]

        return build_ocean_ask_response(
            req=req,
            intent=INTENT_TREND_ANALYSIS,
            sub_intents=[],
            region=region,
            query_type=ctx["query_type"],
            topics=ctx["topics"],
            answer_block={
                "headline": f"Tren {metric_label} minggu ini berhasil dibaca.",
                "summary": summary,
                "recommendation": "Gunakan pembacaan tren ini bersama indikator laut lain bila ingin melihat implikasi operasionalnya.",
                "caution": "Interpretasi tren tetap bergantung pada panjang dan kualitas data historis.",
            },
            evidence=evidence,
            confidence=confidence,
            explanation=explanation,
            data_status={"source_type": "csv_timeseries"},
            right_panel=_base_right_panel(
                [
                    {"label": "Metrik", "value": metric_label, "unit": ""},
                    {"label": "Arah", "value": comp.get("direction"), "unit": ""},
                    {"label": "Minggu ini", "value": comp.get("this_week_avg"), "unit": ""},
                    {"label": "Minggu lalu", "value": comp.get("last_week_avg"), "unit": ""},
                ],
                evidence["trust"],
                "Tren mingguan",
            ),
            followups=[
                "Bagaimana kondisi laut hari ini?",
                "Apakah ombak hari ini aman?",
                "Mengapa FGI rendah?",
            ],
        )

    if "hari ini" in q and "kemarin" in q:
        comp = compare_today_vs_yesterday(region, metric) or {}
        enough = bool(comp.get("enough_data"))
        direction = comp.get("direction", "unknown")

        evidence = {
            "intent_match": True,
            "data": comp,
            "trust": {
                "source": "Time series / Perbandingan harian",
                "date_utc": None,
                "generated_at": None,
                "freshness_status": "unknown",
                "confidence": "high" if enough else "low",
                "basis_type": "trend_compare",
                "mode": "trend-analysis",
                "caveat": "Perbandingan harian dapat berubah cepat bila ada dinamika cuaca atau laut yang kuat.",
            },
            "sources": [],
            "missing_core_fields": not enough,
        }

        confidence = compute_confidence(
            intent=INTENT_TREND_ANALYSIS,
            evidence=evidence,
            answer_kind="default" if enough else "generic",
        )

        if enough:
            summary = (
                f"Nilai {metric_label} hari ini di {region} sekitar {comp.get('today', 0):.2f}, "
                f"sedangkan kemarin sekitar {comp.get('yesterday', 0):.2f}. "
                f"Arahnya cenderung {direction}."
            )
            explanation = [f"Perbandingan harian menunjukkan arah {direction}."]
        else:
            summary = f"Data historis {metric_label} belum cukup untuk perbandingan harian di {region}."
            explanation = ["Data historis harian belum memadai."]

        return build_ocean_ask_response(
            req=req,
            intent=INTENT_TREND_ANALYSIS,
            sub_intents=[],
            region=region,
            query_type=ctx["query_type"],
            topics=ctx["topics"],
            answer_block={
                "headline": f"Tren {metric_label} harian berhasil dibaca.",
                "summary": summary,
                "recommendation": "Gunakan pembacaan ini bersama indikator lain bila ingin melihat dampaknya terhadap operasi lapangan.",
                "caution": "Perbandingan harian tidak selalu mewakili perubahan di semua titik laut.",
            },
            evidence=evidence,
            confidence=confidence,
            explanation=explanation,
            data_status={"source_type": "csv_timeseries"},
            right_panel=_base_right_panel(
                [
                    {"label": "Metrik", "value": metric_label, "unit": ""},
                    {"label": "Arah", "value": comp.get("direction"), "unit": ""},
                    {"label": "Hari ini", "value": comp.get("today"), "unit": ""},
                    {"label": "Kemarin", "value": comp.get("yesterday"), "unit": ""},
                ],
                evidence["trust"],
                "Tren harian",
            ),
            followups=[
                "Bagaimana kondisi laut hari ini?",
                "Apakah ombak hari ini aman?",
                "Bagaimana tren gelombang minggu ini?",
            ],
        )

    trend = get_trend_summary(region, metric) or {}
    evidence = {
        "intent_match": True,
        "data": trend,
        "trust": {
            "source": "Time series / Ringkasan tren",
            "date_utc": None,
            "generated_at": None,
            "freshness_status": "unknown",
            "confidence": "medium" if trend else "low",
            "basis_type": "trend_summary",
            "mode": "trend-analysis",
            "caveat": "Ringkasan tren adalah pembacaan awal dan sangat bergantung pada panjang seri yang tersedia.",
        },
        "sources": [],
        "missing_core_fields": not bool(trend),
    }

    confidence = compute_confidence(
        intent=INTENT_TREND_ANALYSIS,
        evidence=evidence,
        answer_kind="default" if trend else "generic",
    )

    return build_ocean_ask_response(
        req=req,
        intent=INTENT_TREND_ANALYSIS,
        sub_intents=[],
        region=region,
        query_type=ctx["query_type"],
        topics=ctx["topics"],
        answer_block={
            "headline": f"Tren {metric_label} berhasil dibaca.",
            "summary": f"Pembacaan tren {metric_label} di {region} saat ini cenderung {trend.get('trend', 'unknown')}.",
            "recommendation": "Gunakan tren ini sebagai pembacaan awal sebelum melihat perbandingan periode yang lebih spesifik.",
            "caution": "Interpretasi tren tetap bergantung pada panjang dan kualitas data historis.",
        },
        evidence=evidence,
        confidence=confidence,
        explanation=[f"Tren umum saat ini: {trend.get('trend', 'unknown')}."],
        data_status={"source_type": "csv_timeseries"},
        right_panel=_base_right_panel(
            [
                {"label": "Metrik", "value": metric_label, "unit": ""},
                {"label": "Tren", "value": trend.get("trend"), "unit": ""},
            ],
            evidence["trust"],
            "Ringkasan tren",
        ),
        followups=[
            "Bagaimana kondisi laut hari ini?",
            "Apakah ombak hari ini aman?",
            "Mengapa FGI rendah?",
        ],
    )


def _handle_fgi_indicator(req: OceanAskRequest, ctx: Dict[str, Any]) -> OceanAskResponse:
    region = ctx["region"]
    q = (req.question or "").lower()

    today = get_ocean_today(region=region, context=req.context) or {}
    fgi = get_fgi_today(region=region) or {}
    metrics = _extract_ocean_metrics(today, fgi)

    score = _safe_float(metrics["fgi_score"])
    band = metrics["fgi_band"] or "unknown"
    drivers = _fgi_drivers(metrics)

    if "apa arti" in q or "apa itu" in q:
            is_definition = ("apa arti" in q) or ("apa itu" in q)
    is_general_summary = (
        ("informasi fgi" in q)
        or ("gambaran fgi" in q)
        or ("ringkasan fgi" in q)
        or ("secara umum" in q and "fgi" in q)
        or ("kondisi fgi" in q)
    )

    if is_definition:
        headline = f"FGI env {region} berhasil dijelaskan."
        if score is None:
            summary = "FGI env adalah indikator peluang relatif area penangkapan ikan, tetapi nilainya belum terbaca cukup kuat pada pembacaan ini."
            answer_kind = "generic"
        else:
            summary = (
                f"FGI env adalah indikator peluang relatif area penangkapan ikan berbasis kondisi oseanografi. "
                f"Untuk {region}, nilainya saat ini sekitar {score:.3f} dan berada pada band {band}."
            )
            answer_kind = "default"

    elif is_general_summary:
        headline = f"Ringkasan FGI {region} hari ini berhasil dibaca."
        if score is None:
            summary = (
                f"FGI env hari ini untuk {region} belum terbaca cukup kuat, "
                "sehingga ringkasan peluang relatif belum bisa ditegaskan."
            )
            answer_kind = "generic"
        else:
            summary = (
                f"FGI env hari ini memberi pembacaan awal tentang peluang relatif penangkapan ikan di {region}. "
                f"Nilainya saat ini sekitar {score:.3f} dan berada pada band {band}. "
                "Ini bukan jaminan hasil tangkapan, tetapi indikasi awal yang sebaiknya dibaca bersama suhu laut, klorofil-a, dan kondisi operasi."
            )
            answer_kind = "default"

    else:
        headline = f"FGI env {region} berhasil dibaca."
        if score is None:
            summary = f"FGI env untuk {region} belum terbaca cukup kuat pada pembacaan ini."
            answer_kind = "generic"
        else:
            summary = (
                f"FGI env untuk {region} saat ini sekitar {score:.3f} dan berada pada band {band}. "
                f"Ini adalah pembacaan peluang relatif, bukan jaminan hasil tangkapan."
            )
            answer_kind = "default"
        

    evidence = {
        "intent_match": True,
        "data": {
            "wave_m": metrics["wave"],
            "wind_ms": metrics["wind"],
            "sst_c": metrics["sst"],
            "chl_mg_m3": metrics["chl"],
            "sal_psu": metrics["sal"],
            "fgi_score": score,
            "band": band,
        },
        "wave_m": metrics["wave"],
        "wind_ms": metrics["wind"],
        "sst_c": metrics["sst"],
        "chl_mg_m3": metrics["chl"],
        "sal_psu": metrics["sal"],
        "fgi_score": score,
        "band": band,
        "explain": {
            "drivers": drivers,
        },
        "trust": {
            "source": "FGI env snapshot",
            "date_utc": today.get("date") or today.get("date_utc"),
            "generated_at": today.get("generated_at") or today.get("meta", {}).get("generated_at"),
            "freshness_status": _freshness_from_today(today),
            "confidence": _confidence_from_today(today),
            "basis_type": "model_based_score",
            "mode": "indicator",
            "caveat": "FGI env adalah skor indikatif berbasis kondisi oseanografi, bukan jaminan hasil tangkapan.",
        },
        "sources": [],
        "missing_core_fields": score is None,
    }

    confidence = compute_confidence(
        intent=INTENT_FGI_INDICATOR,
        evidence=evidence,
        answer_kind=answer_kind,
    )

    answer_block = {
        "headline": headline,
        "summary": summary,
        "recommendation": "Baca FGI env bersama suhu laut, klorofil-a, dan pengamatan lapangan sebelum mengambil keputusan.",
        "caution": "Interpretasi terbaik didapat bila FGI env dipadukan dengan FGI-R dan kondisi operasional.",
    }

    right_panel = _base_right_panel(
        [
            {"label": "Gelombang", "value": metrics["wave"], "unit": "m"},
            {"label": "Angin", "value": metrics["wind"], "unit": "m/s"},
            {"label": "SST", "value": metrics["sst"], "unit": "°C"},
            {"label": "Klorofil-a", "value": metrics["chl"], "unit": "mg/m³"},
            {"label": "FGI", "value": score, "unit": ""},
        ],
        evidence["trust"],
        "FGI env",
    )

    return build_ocean_ask_response(
        req=req,
        intent=INTENT_FGI_INDICATOR,
        sub_intents=[],
        region=region,
        query_type=ctx["query_type"],
        topics=ctx["topics"],
        answer_block=answer_block,
        evidence=evidence,
        confidence=confidence,
        explanation=drivers,
        data_status={
            "date": today.get("date") or today.get("date_utc"),
            "generated_at": today.get("generated_at") or today.get("meta", {}).get("generated_at"),
            "stale": today.get("stale", True),
            "completeness": today.get("completeness", "low"),
            "source_type": "fgi_env",
        },
        right_panel=right_panel,
        followups=[
            "Apa beda FGI env dan FGI-R?",
            "Mana area relatif lebih menjanjikan?",
            "Bagaimana kondisi laut hari ini?",
        ],
    )

def _handle_relative_opportunity(req: OceanAskRequest, ctx: Dict[str, Any]) -> OceanAskResponse:
    region = _resolve_effective_region(req, ctx)

    today = get_ocean_today(region=region, context=req.context) or {}
    fgi = get_fgi_today(region=region) or {}
    metrics = _extract_ocean_metrics(today, fgi)

    score = _safe_float(metrics.get("fgi_score"))
    band = metrics.get("fgi_band") or "unknown"
    sst = _safe_float(metrics.get("sst"))
    chl = _safe_float(metrics.get("chl"))
    wave = _safe_float(metrics.get("wave"))
    wind = _safe_float(metrics.get("wind"))

    drivers: List[str] = []

    if score is not None:
        drivers.append(
            f"FGI env saat ini sekitar {score:.3f} dan berada pada band {band}."
        )
    else:
        drivers.append(
            "FGI env belum terbaca cukup kuat untuk memberi pembacaan peluang relatif yang lebih tegas."
        )

    if chl is not None:
        if chl < 0.15:
            drivers.append(
                "Klorofil-a masih rendah, sehingga dukungan produktivitas permukaan belum kuat."
            )
        elif chl < 0.5:
            drivers.append(
                "Klorofil-a berada pada tingkat sedang, cukup mendukung tetapi belum terlalu kuat."
            )
        else:
            drivers.append(
                "Klorofil-a relatif tinggi, yang biasanya lebih mendukung produktivitas permukaan."
            )

    if sst is not None:
        if sst >= 30.5:
            drivers.append(
                "Suhu permukaan laut cenderung hangat, sehingga interpretasi peluang perlu dibaca hati-hati bersama sinyal lain."
            )
        else:
            drivers.append(
                "Suhu permukaan laut masih berada pada kisaran yang relatif mendukung kondisi tropis."
            )

    if wave is not None and wind is not None:
        drivers.append(
            f"Gelombang {_label_wave(wave)} dan angin {_label_wind(wind)} memberi konteks tambahan untuk membaca peluang relatif dan kenyamanan operasi."
        )

    if score is None:
        headline = f"Indikasi kelimpahan relatif ikan di {region} belum terbaca kuat."
        summary = (
            "NELAYA-AI belum mengukur kelimpahan ikan absolut secara langsung, "
            "dan saat ini pembacaan peluang relatif untuk wilayah ini juga belum cukup kuat."
        )
        answer_kind = "generic"
    else:
        headline = f"Indikasi kelimpahan relatif ikan di {region} berhasil dibaca."
        summary = (
            "NELAYA-AI belum mengukur kelimpahan ikan absolut secara langsung, "
            "tetapi dapat memberi pembacaan awal tentang indikasi kelimpahan relatif "
            "berdasarkan FGI, suhu laut, klorofil-a, dan kondisi oseanografi lain. "
            f"Untuk {region}, pembacaan peluang relatif saat ini berada pada level {band} "
            f"dengan FGI env sekitar {score:.3f}."
        )
        answer_kind = "default"

    evidence = {
        "intent_match": True,
        "data": {
            "wave_m": metrics.get("wave"),
            "wind_ms": metrics.get("wind"),
            "sst_c": metrics.get("sst"),
            "chl_mg_m3": metrics.get("chl"),
            "sal_psu": metrics.get("sal"),
            "ssh_cm": metrics.get("ssh"),
            "fgi_score": metrics.get("fgi_score"),
            "band": band,
        },
        "wave_m": metrics.get("wave"),
        "wind_ms": metrics.get("wind"),
        "sst_c": metrics.get("sst"),
        "chl_mg_m3": metrics.get("chl"),
        "sal_psu": metrics.get("sal"),
        "ssh_cm": metrics.get("ssh"),
        "fgi_score": metrics.get("fgi_score"),
        "band": band,
        "explain": {
            "drivers": drivers,
        },
        "trust": {
            "source": "FGI env + ocean snapshot",
            "date_utc": today.get("date") or today.get("date_utc"),
            "generated_at": today.get("generated_at") or today.get("meta", {}).get("generated_at"),
            "freshness_status": _freshness_from_today(today),
            "confidence": _confidence_from_today(today),
            "basis_type": "relative_opportunity_proxy",
            "mode": "relative-opportunity",
            "caveat": "Ini adalah pembacaan indikasi kelimpahan relatif atau peluang awal penangkapan, bukan estimasi stok ikan absolut.",
        },
        "sources": [],
        "missing_core_fields": score is None,
    }

    confidence = compute_confidence(
        intent=INTENT_RELATIVE_OPPORTUNITY,
        evidence=evidence,
        answer_kind=answer_kind,
    )

    right_panel = _base_right_panel(
        [
            {"label": "FGI", "value": metrics.get("fgi_score"), "unit": ""},
            {"label": "Band", "value": band, "unit": ""},
            {"label": "Klorofil-a", "value": metrics.get("chl"), "unit": "mg/m³"},
            {"label": "SST", "value": metrics.get("sst"), "unit": "°C"},
            {"label": "Gelombang", "value": metrics.get("wave"), "unit": "m"},
            {"label": "Angin", "value": metrics.get("wind"), "unit": "m/s"},
        ],
        evidence["trust"],
        "Peluang relatif ikan",
    )

    return build_ocean_ask_response(
        req=req,
        intent=INTENT_RELATIVE_OPPORTUNITY,
        sub_intents=[],
        region=region,
        query_type="ocean",
        topics=ctx["topics"],
        answer_block={
            "headline": headline,
            "summary": summary,
            "recommendation": "Gunakan pembacaan ini sebagai indikasi awal, lalu padukan dengan pengamatan lapangan sebelum mengambil keputusan.",
            "caution": "Ini bukan estimasi stok ikan absolut dan bukan jaminan hasil tangkapan.",
        },
        evidence=evidence,
        confidence=confidence,
        explanation=drivers,
        data_status={
            "date": today.get("date") or today.get("date_utc"),
            "generated_at": today.get("generated_at") or today.get("meta", {}).get("generated_at"),
            "stale": today.get("stale", True),
            "completeness": today.get("completeness", "low"),
            "source_type": "relative_opportunity",
        },
        right_panel=right_panel,
        followups=[
            "Mengapa FGI rendah?",
            "Bagaimana kondisi laut hari ini?",
            "Apakah ombak hari ini aman?",
        ],
    )


def _handle_fgi_compare(req: OceanAskRequest, ctx: Dict[str, Any]) -> OceanAskResponse:
    region = ctx["region"]

    evidence = {
        "intent_match": True,
        "data": {
            "fgi_env_basis": "skor lingkungan laut",
            "fgi_r_basis": "skor rekomendasi operasional",
        },
        "trust": {
            "source": "Knowledge internal NELAYA-AI",
            "date_utc": None,
            "generated_at": None,
            "freshness_status": "unknown",
            "confidence": "high",
            "basis_type": "knowledge_template",
            "mode": "comparison",
            "caveat": "Ini adalah penjelasan konsep internal NELAYA-AI dan tetap harus dibaca bersama konteks penggunaan masing-masing indeks.",
        },
        "sources": [],
        "missing_core_fields": False,
    }

    confidence = compute_confidence(
        intent=INTENT_FGI_COMPARE,
        evidence=evidence,
        answer_kind="default",
    )

    return build_ocean_ask_response(
        req=req,
        intent=INTENT_FGI_COMPARE,
        sub_intents=[],
        region=region,
        query_type="knowledge",
        topics=ctx["topics"],
        answer_block={
            "headline": "Perbedaan FGI env dan FGI-R berhasil dijelaskan.",
            "summary": (
                "FGI env membaca kecocokan lingkungan laut, sedangkan FGI-R menambahkan "
                "pertimbangan operasional seperti jarak, biaya, dan konteks rumpon. "
                "Jadi, FGI env lebih dekat ke pembacaan habitat, sementara FGI-R lebih dekat ke rekomendasi praktis."
            ),
            "recommendation": "Gunakan FGI env untuk membaca kualitas lingkungan laut, dan gunakan FGI-R saat ingin membandingkan peluang relatif dengan konteks operasional.",
            "caution": "Kedua indeks tidak boleh dibaca sebagai jaminan hasil tangkapan, melainkan sebagai alat bantu keputusan.",
        },
        evidence=evidence,
        confidence=confidence,
        explanation=[
            "FGI env berfokus pada kecocokan kondisi oseanografi.",
            "FGI-R memadukan skor lingkungan dengan aspek operasional.",
            "FGI-R lebih cocok dipakai untuk keputusan praktis di lapangan.",
        ],
        data_status={"source_type": "knowledge_template"},
        right_panel=_base_right_panel(
            [
                {"label": "FGI env", "value": "Lingkungan", "unit": ""},
                {"label": "FGI-R", "value": "Operasional", "unit": ""},
                {"label": "Basis", "value": "Konsep internal", "unit": ""},
            ],
            evidence["trust"],
            "Perbandingan indeks",
        ),
        followups=[
            "Mengapa FGI rendah?",
            "Mana area relatif lebih menjanjikan?",
            "Kalau budget saya sekian, dari mana paling masuk akal?",
        ],
    )


def _handle_reference_query(req: OceanAskRequest, ctx: Dict[str, Any]) -> OceanAskResponse:
    q = (req.question or "").lower()
    region = _resolve_effective_region(req, ctx)

    dataset = None
    if "pulau" in q:
        dataset = "small_islands"
    elif "pelabuhan" in q or "port" in q:
        dataset = "ports"
    elif "surf" in q or "surfing" in q or "spot surfing" in q or "lokasi surfing" in q:
        dataset = "surf_spots"

    if not dataset:
        return _handle_fallback(req, ctx)

    label_map = {
        "small_islands": "pulau",
        "ports": "pelabuhan",
        "surf_spots": "lokasi surfing",
    }
    label = label_map[dataset]

    items: List[Any] = []
    count: int = 0
    headline = "Data referensi berhasil ditemukan."
    summary = "Data referensi berhasil dibaca."

    if dataset == "ports" and "terdekat" in q:
        center = resolve_region_center(region)
        if center:
            lat, lon = center
            res = find_nearest_ports(lat, lon)
            items = res
            count = len(res)
            names = ", ".join([r["name"] for r in res[:5]]) if res else "belum ada"
            headline = "Pelabuhan terdekat berhasil ditemukan."
            summary = f"Pelabuhan terdekat di sekitar {region} antara lain: {names}."
    elif dataset == "surf_spots" and "terdekat" in q:
        center = resolve_region_center(region)
        if center:
            lat, lon = center
            res = find_nearest_surf_spots(lat, lon)
            items = res
            count = len(res)
            names = ", ".join([r["name"] for r in res[:5]]) if res else "belum ada"
            headline = "Lokasi surfing terdekat berhasil ditemukan."
            summary = f"Lokasi surfing terdekat di sekitar {region} antara lain: {names}."
    elif "berapa" in q or "jumlah" in q or "ada berapa" in q:
        if dataset == "small_islands":
            res = count_small_islands(region)
        else:
            res = count_dataset(dataset, region)
        items = res.get("items", [])[:10]
        count = res.get("count", 0)
        headline = f"Jumlah {label} di {region} berhasil dihitung."
        summary = f"Terdapat sekitar {count} {label} yang terdata di {region}."
    else:
        if dataset == "small_islands":
            res = list_small_islands(region, limit=30)
        else:
            res = list_dataset(dataset, region, limit=30)
        items = res.get("items", [])
        count = res.get("count", len(items))
        sample = ", ".join(str(x) for x in items[:10]) if items else "belum ada"
        headline = f"Daftar {label} di {region} berhasil ditemukan."
        summary = f"Beberapa {label} yang terdata di {region} antara lain: {sample}."

    evidence = {
        "intent_match": True,
        "items": items,
        "data": {"count": count},
        "trust": {
            "source": "Reference data NELAYA-AI",
            "date_utc": None,
            "generated_at": None,
            "freshness_status": "unknown",
            "confidence": "medium",
            "basis_type": "reference_lookup",
            "mode": "reference",
            "caveat": "Data referensi membantu pembacaan awal dan tetap perlu diverifikasi bila dipakai operasional.",
        },
        "sources": [],
        "missing_core_fields": count == 0,
    }

    confidence = compute_confidence(
        intent=INTENT_REFERENCE_DATA_QUERY,
        evidence=evidence,
        answer_kind="default" if count > 0 else "generic",
    )

    return build_ocean_ask_response(
        req=req,
        intent=INTENT_REFERENCE_DATA_QUERY,
        sub_intents=[],
        region=region,
        query_type="reference",
        topics=ctx["topics"],
        answer_block={
            "headline": headline,
            "summary": summary,
            "recommendation": "Gunakan data ini sebagai pembacaan awal sebelum analisis lanjutan.",
            "caution": "Jumlah dan daftar tergantung pada kelengkapan dataset yang tersedia.",
        },
        evidence=evidence,
        confidence=confidence,
        explanation=[f"Dataset {dataset} untuk {region} berhasil dibaca."],
        data_status={
            "dataset": dataset,
            "count": count,
            "source_type": "reference_data",
        },
        right_panel=_base_right_panel(
            [
                {"label": "Dataset", "value": dataset, "unit": ""},
                {"label": "Jumlah", "value": count, "unit": ""},
            ],
            evidence["trust"],
            "Data referensi",
        ),
        followups=[
            "Berapa jumlah pulau kecil di Aceh?",
            "Pelabuhan terdekat di mana?",
            "Surf spot terdekat di mana?",
        ],
    )


def _handle_knowledge_adat(req: OceanAskRequest, ctx: Dict[str, Any]) -> OceanAskResponse:
    region = ctx["region"]

    graph_answer = graph_engine.answer(req.question) or {}
    relations = graph_answer.get("relations", []) or []
    sources = graph_answer.get("sources", []) or []
    node = graph_answer.get("node") or {}

    evidence = {
        "intent_match": True,
        "data": {
            "node": node,
            "relations": relations[:3],
        },
        "trust": {
            "source": "Knowledge Graph NELAYA-AI",
            "date_utc": None,
            "generated_at": None,
            "freshness_status": "unknown",
            "confidence": "high" if relations else "low",
            "basis_type": "knowledge_graph",
            "mode": "adat",
            "caveat": "Knowledge graph adalah lapisan pengetahuan bantu, bukan satu-satunya sumber kebenaran.",
        },
        "sources": sources,
        "missing_core_fields": not bool(relations),
    }

    confidence = compute_confidence(
        intent=INTENT_KNOWLEDGE_ADAT,
        evidence=evidence,
        answer_kind="default" if relations else "generic",
    )

    return build_ocean_ask_response(
        req=req,
        intent=INTENT_KNOWLEDGE_ADAT,
        sub_intents=[],
        region=region,
        query_type="knowledge",
        topics=ctx["topics"],
        answer_block={
            "headline": graph_answer.get("headline", "Relasi pengetahuan ditemukan."),
            "summary": graph_answer.get("summary", "Knowledge graph menemukan relasi yang relevan."),
            "recommendation": "Gunakan pembacaan ini sebagai pengetahuan awal sebelum melihat dokumen atau sumber resmi yang lebih rinci.",
            "caution": "Knowledge graph adalah lapisan pengetahuan bantu, bukan satu-satunya sumber kebenaran.",
        },
        evidence=evidence,
        confidence=confidence,
        explanation=relations[:3],
        data_status={
            "source_type": "knowledge_graph",
            "nodes": graph_answer.get("stats", {}).get("nodes", 0),
            "edges": graph_answer.get("stats", {}).get("edges", 0),
        },
        right_panel=_base_right_panel(
            [
                {"label": "Node", "value": node.get("name"), "unit": ""},
                {"label": "Relasi", "value": len(relations), "unit": ""},
                {"label": "Sumber", "value": len(sources), "unit": ""},
            ],
            evidence["trust"],
            "Dasar pengetahuan",
        ),
        followups=[
            "Apa dasar pengakuan Panglima Laot?",
            "Apa kaitannya dengan qanun?",
            "Apa hubungannya dengan nelayan tradisional?",
        ],
    )


def _handle_regulation_query(req: OceanAskRequest, ctx: Dict[str, Any]) -> OceanAskResponse:
    region = _resolve_effective_region(req, ctx)

    reg_answer = engine.answer(req.question) or {}
    sources = reg_answer.get("sources", []) or []
    subintent = _detect_regulation_subintent(req)

    primary_source = sources[0]["title"] if sources else None
    primary_pasal = sources[0].get("pasal") if sources else None

    if subintent == "regulation_scope":
        answer_block = _compose_regulation_scope_answer(req, reg_answer, sources)
        answer_kind = "default" if sources else "generic"
    elif subintent == "regulation_compliance":
        answer_block = _compose_regulation_compliance_answer(req, reg_answer, sources)
        answer_kind = "default" if sources else "generic"
    else:
        answer_block = {
            "headline": "Jawaban regulasi ditemukan.",
            "summary": reg_answer.get("answer") or "Belum ada jawaban regulasi yang cukup relevan.",
            "recommendation": "Periksa pasal sumber untuk memastikan konteks hukum yang tepat.",
            "caution": "Untuk penggunaan formal, tetap baca dokumen asli dan konteks pasalnya.",
        }
        answer_kind = "default" if sources else "generic"

    evidence = {
        "intent_match": True,
        "documents": sources,
        "data": {
            "documents_count": len(sources),
            "subintent": subintent,
        },
        "trust": {
            "source": "Regulation Engine / Dokumen terindeks",
            "date_utc": None,
            "generated_at": None,
            "freshness_status": "unknown",
            "confidence": "high" if sources else "low",
            "basis_type": "document_retrieval",
            "mode": "regulation",
            "caveat": "Jawaban ini adalah pembacaan awal regulasi dan tidak menggantikan penafsiran hukum resmi.",
        },
        "sources": sources,
        "missing_core_fields": not bool(sources),
    }

    confidence = compute_confidence(
        intent=INTENT_REGULATION_QUERY,
        evidence=evidence,
        answer_kind=answer_kind,
    )

    return build_ocean_ask_response(
        req=req,
        intent=INTENT_REGULATION_QUERY,
        sub_intents=[subintent],
        region=region,
        query_type="knowledge",
        topics=ctx["topics"],
        answer_block=answer_block,
        evidence=evidence,
        confidence=confidence,
        explanation=[
            "Jawaban ini disusun dari basis regulasi yang telah diindeks dalam NELAYA-AI."
        ],
        data_status={
            "documents": engine.stats().get("documents", 0),
            "articles": engine.stats().get("articles", 0),
            "source_type": "regulations",
            "primary_source": primary_source,
            "primary_pasal": primary_pasal,
            "subintent": subintent,
        },
        right_panel=_base_right_panel(
            [
                {"label": "Jenis query", "value": "Regulasi", "unit": ""},
                {"label": "Jumlah dokumen", "value": len(sources), "unit": ""},
                {"label": "Sumber utama", "value": primary_source, "unit": ""},
                {"label": "Pasal", "value": primary_pasal, "unit": ""},
            ],
            evidence["trust"],
            "Dasar jawaban regulasi",
        ),
        followups=[
            "Wilayah berlaku aturan ini di mana?",
            "Apa pasal yang paling relevan?",
            "Apa kaitannya dengan nelayan kecil?",
        ],
    )

def _handle_off_domain_feedback(req: OceanAskRequest, ctx: Dict[str, Any]) -> OceanAskResponse:
    region = _resolve_effective_region(req, ctx)

    evidence = {
        "intent_match": True,
        "is_feedback": True,
        "trust": {
            "source": "Tanya NELAYA-AI conversational fallback",
            "date_utc": None,
            "generated_at": None,
            "freshness_status": "unknown",
            "confidence": "medium",
            "basis_type": "feedback_response",
            "mode": "conversation",
            "caveat": "Ini bukan jawaban domain laut, melainkan respons percakapan ringan.",
        },
        "sources": [],
    }

    confidence = compute_confidence(
        intent=INTENT_OFF_DOMAIN_FEEDBACK,
        evidence=evidence,
        answer_kind="default",
    )

    return build_ocean_ask_response(
        req=req,
        intent=INTENT_OFF_DOMAIN_FEEDBACK,
        sub_intents=[],
        region=region,
        query_type="conversation",
        topics=ctx["topics"],
        answer_block={
            "headline": "Terima kasih, saya memang masih terus belajar.",
            "summary": (
                "Kalau ada jawaban saya yang belum pas, itu masukan yang baik. "
                "Coba beri saya pertanyaan yang lebih spesifik tentang kondisi laut, FGI, gelombang, "
                "regulasi, atau data referensi, dan saya akan mencoba menjawab lebih baik."
            ),
            "recommendation": "Arahkan saya ke pertanyaan yang lebih spesifik agar pembacaan saya lebih tepat.",
            "caution": "Saya masih dalam tahap penguatan dan terus diperbaiki dari waktu ke waktu.",
        },
        evidence=evidence,
        confidence=confidence,
        explanation=[
            "Respons ini ditujukan untuk umpan balik ringan, bukan pertanyaan domain laut.",
        ],
        data_status={
            "source_type": "conversation_feedback",
        },
        right_panel=_base_right_panel(
            [
                {"label": "Jenis query", "value": "Feedback", "unit": ""},
                {"label": "Mode", "value": "Percakapan", "unit": ""},
            ],
            evidence["trust"],
            "Respons percakapan",
        ),
        followups=[
            "Bagaimana kondisi laut hari ini?",
            "Apa itu FGI?",
            "Apakah ombak hari ini aman?",
            "Apa itu rumpon?",
        ],
    )


def _handle_fallback(req: OceanAskRequest, ctx: Dict[str, Any]) -> OceanAskResponse:
    region = ctx["region"]

    evidence = {
        "intent_match": False,
        "is_fallback": True,
        "trust": {
            "source": "Tanya NELAYA-AI MVP",
            "date_utc": None,
            "generated_at": None,
            "freshness_status": "unknown",
            "confidence": "low",
            "basis_type": "fallback",
            "mode": "fallback",
            "caveat": "Pertanyaan belum dapat dipetakan kuat ke engine yang tepat pada tahap ini.",
        },
        "sources": [],
    }

    confidence = compute_confidence(
        intent=INTENT_FALLBACK,
        evidence=evidence,
        answer_kind="generic",
    )

    return build_ocean_ask_response(
        req=req,
        intent=INTENT_FALLBACK,
        sub_intents=[],
        region=region,
        query_type="fallback",
        topics=ctx["topics"],
        answer_block={
            "headline": "Pertanyaan belum bisa dipetakan dengan cukup kuat.",
            "summary": f"Saya baru bisa memberi pembacaan awal untuk wilayah {region}, tetapi belum cukup yakin untuk memilih engine terbaik bagi pertanyaan ini.",
            "recommendation": "Coba buat pertanyaan lebih spesifik, misalnya tentang ombak, FGI, OSI, rumpon, atau qanun.",
            "caution": "Pada tahap MVP, tidak semua pertanyaan kompleks sudah didukung penuh.",
        },
        evidence=evidence,
        confidence=confidence,
        explanation=["Pertanyaan belum cukup spesifik atau belum didukung penuh pada tahap MVP."],
        data_status={"source_type": "fallback"},
        right_panel=_base_right_panel(
            [
                {"label": "Jenis query", "value": "Fallback", "unit": ""},
                {"label": "Keyakinan", "value": confidence["label"], "unit": ""},
            ],
            evidence["trust"],
            "Status jawaban",
        ),
        followups=[
            "Laut Aceh hari ini bagaimana?",
            "Apakah ombak hari ini aman?",
            "Mengapa FGI rendah?",
            "Apa itu rumpon?",
        ],
    )


# =========================================================
# Endpoint utama
# =========================================================

@router.post("/ask", response_model=OceanAskResponse)
def ask_ocean(req: OceanAskRequest = Body(...)) -> OceanAskResponse:
    routing = classify_intent(req.question)
    ctx = build_context(req, routing)
    
    intent = _carry_intent_from_context(req, routing["intent"])

    if intent == INTENT_OCEAN_CONDITION:
        return _handle_ocean_condition(req, ctx)

    if intent == INTENT_METRIC_EXPLAINER:
        return _handle_metric_explainer(req, ctx)

    if intent == INTENT_SAFETY_CHECK:
        return _handle_safety_check(req, ctx)

    if intent == INTENT_TREND_ANALYSIS:
        return _handle_trend_analysis(req, ctx)

    if intent == INTENT_FGI_INDICATOR:
        return _handle_fgi_indicator(req, ctx)

    if intent == INTENT_RELATIVE_OPPORTUNITY:
        return _handle_relative_opportunity(req, ctx)

    if intent == INTENT_FGI_COMPARE:
        return _handle_fgi_compare(req, ctx)

    if intent == INTENT_REFERENCE_DATA_QUERY:
        return _handle_reference_query(req, ctx)

    if intent == INTENT_KNOWLEDGE_ADAT:
        return _handle_knowledge_adat(req, ctx)

    if intent == INTENT_REGULATION_QUERY:
        return _handle_regulation_query(req, ctx)

    if intent == INTENT_OFF_DOMAIN_FEEDBACK:
        return _handle_off_domain_feedback(req, ctx)

    return _handle_fallback(req, ctx)


@router.post("/quick-check")
def quick_check(req: OceanAskRequest):
    routing = classify_intent(req.question)
    ctx = build_context(req, routing)
    resp = _handle_safety_check(req, ctx)

    score = resp.scores.get("confidence_score", 0.5)
    badge = "AMAN" if "aman" in resp.answer.summary.lower() else "WASPADA"

    return {
        "ok": True,
        "headline": resp.answer.headline,
        "badge": badge,
        "reason": resp.explanation[0] if resp.explanation else "Pembacaan keselamatan terbatas.",
        "confidence": score,
        "region": resp.region,
        "trend_metric": "wave",
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

    if q in {"chl", "chlorophyll", "chlorofil", "klorofil-a"}:
        return {
            "ok": True,
            "term": "Chlorophyll",
            "title": "Klorofil-a",
            "summary": "Indikator produktivitas perairan yang membantu membaca dasar rantai makanan laut.",
        }

    if q in {"sst", "suhu laut"}:
        return {
            "ok": True,
            "term": "SST",
            "title": "Sea Surface Temperature",
            "summary": "Suhu permukaan laut yang membantu membaca dinamika massa air dan kenyamanan habitat.",
        }

    if q in {"osi"}:
        return {
            "ok": True,
            "term": "OSI",
            "title": "Ocean State Index",
            "summary": "Indeks sintesis yang merangkum beberapa sinyal oseanografi harian untuk membaca kondisi laut secara ringkas.",
        }

    if q in {"fgi-r", "fgi r"}:
        return {
            "ok": True,
            "term": "FGI-R",
            "title": "FGI-R",
            "summary": "FGI-R adalah pembacaan peluang relatif yang menambahkan konteks operasional seperti jarak, biaya, dan rumpon ke atas skor lingkungan.",
        }

    return {
        "ok": True,
        "term": term,
        "title": term,
        "summary": "Istilah belum tersedia di glossary v1.",
    }