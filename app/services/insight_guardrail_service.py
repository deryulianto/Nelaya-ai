from __future__ import annotations


def build_insight_guardrail_from_readiness(readiness_payload: dict) -> dict:
    readiness = readiness_payload.get("readiness", {})
    dashboard_card = readiness_payload.get("dashboard_card", {})
    source_confidence = readiness_payload.get("source_confidence", {})

    level = readiness.get("level")
    public_status = readiness.get("public_status")
    advisory_allowed = readiness.get("advisory_allowed", False)
    insight_mode = readiness.get("insight_mode")

    available_layers = dashboard_card.get("available_layers", [])
    stale_layers = dashboard_card.get("stale_layers", [])
    missing_layers = dashboard_card.get("missing_layers", [])
    invalid_layers = dashboard_card.get("invalid_layers", [])

    if level == "high":
        allowed_claim_level = "decision_support_language_allowed"
        tone = "percaya diri tetapi tetap rendah hati"
        headline_policy = "boleh menyebut decision support berbasis data relatif lengkap"
        required_disclaimer = (
            "Meskipun data relatif lengkap, kondisi lokal dan pengalaman nelayan tetap harus diperhatikan."
        )
        allowed_phrases = [
            "data relatif lengkap",
            "decision support dapat digunakan dengan kehati-hatian",
            "sinyal laut cukup konsisten",
            "tetap perlu memperhatikan kondisi lapangan",
        ]
        forbidden_phrases = [
            "ikan pasti ada",
            "jaminan hasil tangkapan",
            "kepastian lokasi ikan",
        ]

    elif level == "medium":
        allowed_claim_level = "cautious_indication_language_only"
        tone = "hati-hati, analitis, tidak mengarahkan secara mutlak"
        headline_policy = "boleh menyebut indikasi awal yang cukup terbaca, bukan advisory penuh"
        required_disclaimer = (
            "Informasi ini bersifat indikatif dan tetap memerlukan validasi lapangan."
        )
        allowed_phrases = [
            "indikasi awal",
            "perlu kehati-hatian",
            "belum menjadi advisory penuh",
            "validasi lapangan tetap diperlukan",
        ]
        forbidden_phrases = [
            "disarankan melaut",
            "zona tangkap utama",
            "peluang tinggi yang siap dioperasikan",
            "kepastian lokasi ikan",
            "jaminan hasil tangkapan",
        ]

    elif level == "low":
        allowed_claim_level = "limited_reading_language_only"
        tone = "sangat rendah hati, membatasi klaim, menekankan keterbatasan data"
        headline_policy = "hanya boleh menyebut pembacaan terbatas"
        required_disclaimer = (
            "Pembacaan hari ini masih terbatas dan tidak boleh digunakan sebagai advisory operasional penuh."
        )
        allowed_phrases = [
            "pembacaan terbatas",
            "indikasi awal",
            "belum cukup untuk advisory penuh",
            "data masih parsial",
            "sebagian layer belum tersedia",
            "validasi nelayan tetap penting",
        ]
        forbidden_phrases = [
            "peluang ikan tinggi",
            "disarankan melaut",
            "zona tangkap utama",
            "lokasi ikan terbaik",
            "advisory operasional",
            "kepastian lokasi ikan",
            "jaminan hasil tangkapan",
        ]

    else:
        allowed_claim_level = "no_ocean_claim_allowed"
        tone = "menahan diri dan tidak membuat klaim kondisi laut"
        headline_policy = "tidak boleh membuat klaim peluang ikan atau kondisi operasional"
        required_disclaimer = (
            "Data belum memadai untuk menghasilkan pembacaan laut yang bertanggung jawab."
        )
        allowed_phrases = [
            "data belum memadai",
            "belum dapat dibaca secara bertanggung jawab",
            "menunggu pembaruan data",
        ]
        forbidden_phrases = [
            "peluang ikan",
            "disarankan melaut",
            "zona tangkap",
            "decision support",
            "advisory",
            "kepastian lokasi ikan",
            "jaminan hasil tangkapan",
        ]

    template = _build_template(
        level=level,
        available_layers=available_layers,
        stale_layers=stale_layers,
        missing_layers=missing_layers,
        invalid_layers=invalid_layers,
        required_disclaimer=required_disclaimer,
    )

    return {
        "module": "insight_guardrail",
        "version": "0.1.0",
        "snapshot_date": readiness_payload.get("snapshot_date"),
        "guardrail": {
            "readiness_level": level,
            "public_status": public_status,
            "insight_mode": insight_mode,
            "advisory_allowed": advisory_allowed,
            "allowed_claim_level": allowed_claim_level,
            "recommended_tone": tone,
            "headline_policy": headline_policy,
            "required_disclaimer": required_disclaimer,
            "allowed_phrases": allowed_phrases,
            "forbidden_phrases": forbidden_phrases,
        },
        "insight_template": template,
        "source_layers": {
            "available_layers": available_layers,
            "stale_layers": stale_layers,
            "missing_layers": missing_layers,
            "invalid_layers": invalid_layers,
        },
        "source_confidence": source_confidence,
    }


def _fmt(items: list) -> str:
    return ", ".join(items) if items else "tidak ada"


def _build_template(
    level: str,
    available_layers: list,
    stale_layers: list,
    missing_layers: list,
    invalid_layers: list,
    required_disclaimer: str,
) -> dict:
    available_txt = _fmt(available_layers)
    stale_txt = _fmt(stale_layers)
    missing_txt = _fmt(missing_layers)
    invalid_txt = _fmt(invalid_layers)

    if level == "high":
        title_hint = "Membaca Laut Aceh dengan Data yang Relatif Lengkap"
        opening = (
            "NELAYA-AI hari ini membaca kondisi laut dengan dukungan data yang relatif lengkap."
        )
    elif level == "medium":
        title_hint = "Membaca Indikasi Awal Laut Aceh dengan Kehati-hatian"
        opening = (
            "NELAYA-AI hari ini menangkap indikasi awal kondisi laut, namun pembacaan tetap perlu dilakukan secara hati-hati."
        )
    elif level == "low":
        title_hint = "Membaca Laut Aceh Saat Data Masih Terbatas"
        opening = (
            "NELAYA-AI hari ini hanya dapat memberikan pembacaan terbatas karena sebagian layer utama belum tersedia atau belum sepenuhnya siap."
        )
    else:
        title_hint = "Menunggu Data Laut yang Lebih Memadai"
        opening = (
            "NELAYA-AI hari ini belum memiliki data yang cukup untuk memberikan pembacaan laut yang bertanggung jawab."
        )

    body = (
        f"Layer yang tersedia dan valid adalah: {available_txt}. "
        f"Layer yang stale: {stale_txt}. "
        f"Layer yang belum tersedia: {missing_txt}. "
        f"Layer yang invalid: {invalid_txt}."
    )

    closing = (
        f"{required_disclaimer} "
        "NELAYA-AI tetap menempatkan pengalaman nelayan dan validasi lapangan sebagai bagian penting dalam memahami laut."
    )

    return {
        "title_hint": title_hint,
        "opening": opening,
        "data_status_sentence": body,
        "required_closing": closing,
    }
