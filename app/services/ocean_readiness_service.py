from __future__ import annotations


def build_readiness_from_confidence(confidence_payload: dict) -> dict:
    confidence = confidence_payload.get("confidence", {})
    level = confidence.get("level")
    operational_status = confidence.get("operational_status")

    available_layers = confidence.get("available_layers", [])
    stale_layers = confidence.get("stale_layers", [])
    missing_layers = confidence.get("missing_layers", [])
    invalid_layers = confidence.get("invalid_layers", [])
    warnings = confidence.get("warnings", [])

    if level == "high":
        readiness_label = "Decision support ready"
        public_status = "data_cukup_kuat"
        insight_mode = "full_ocean_intelligence"
        advisory_allowed = True
        short_message = (
            "Data laut relatif lengkap. NELAYA-AI dapat memberikan decision support "
            "dengan tetap memperhatikan kondisi lapangan."
        )
    elif level == "medium":
        readiness_label = "Indicative decision support"
        public_status = "indikasi_cukup"
        insight_mode = "cautious_ocean_intelligence"
        advisory_allowed = False
        short_message = (
            "Data cukup untuk membaca indikasi awal, tetapi belum cukup untuk advisory penuh. "
            "Validasi lapangan tetap diperlukan."
        )
    elif level == "low":
        readiness_label = "Limited indication only"
        public_status = "indikasi_terbatas"
        insight_mode = "limited_reading"
        advisory_allowed = False
        short_message = (
            "Pembacaan NELAYA-AI masih terbatas. Informasi hari ini hanya boleh dibaca "
            "sebagai indikasi awal, bukan arahan operasional penuh."
        )
    else:
        readiness_label = "No responsible advisory"
        public_status = "data_belum_memadai"
        insight_mode = "no_ocean_advisory"
        advisory_allowed = False
        short_message = (
            "Data belum cukup untuk menghasilkan pembacaan laut yang bertanggung jawab."
        )

    dashboard_card = {
        "title": "Ocean Reading Readiness",
        "status": public_status,
        "confidence_level": level,
        "operational_status": operational_status,
        "readiness_label": readiness_label,
        "advisory_allowed": advisory_allowed,
        "available_layers": available_layers,
        "stale_layers": stale_layers,
        "missing_layers": missing_layers,
        "invalid_layers": invalid_layers,
        "message": short_message,
    }

    narrative_id = _build_indonesian_narrative(
        level=level,
        available_layers=available_layers,
        stale_layers=stale_layers,
        missing_layers=missing_layers,
        invalid_layers=invalid_layers,
    )

    return {
        "module": "ocean_readiness",
        "version": "0.1.0",
        "snapshot_date": confidence_payload.get("snapshot_date"),
        "readiness": {
            "level": level,
            "readiness_label": readiness_label,
            "public_status": public_status,
            "insight_mode": insight_mode,
            "advisory_allowed": advisory_allowed,
            "message": short_message,
            "warnings": warnings,
        },
        "dashboard_card": dashboard_card,
        "narrative": {
            "language": "id",
            "text": narrative_id,
        },
        "source_confidence": confidence,
        "source_health_summary": confidence_payload.get("source_health_summary", {}),
    }


def _build_indonesian_narrative(
    level: str,
    available_layers: list,
    stale_layers: list,
    missing_layers: list,
    invalid_layers: list,
) -> str:
    available_txt = ", ".join(available_layers) if available_layers else "belum ada layer utama"
    stale_txt = ", ".join(stale_layers) if stale_layers else "tidak ada"
    missing_txt = ", ".join(missing_layers) if missing_layers else "tidak ada"
    invalid_txt = ", ".join(invalid_layers) if invalid_layers else "tidak ada"

    if level == "high":
        opening = (
            "Pembacaan laut NELAYA-AI hari ini berada pada tingkat keyakinan tinggi."
        )
    elif level == "medium":
        opening = (
            "Pembacaan laut NELAYA-AI hari ini berada pada tingkat keyakinan sedang."
        )
    elif level == "low":
        opening = (
            "Pembacaan laut NELAYA-AI hari ini masih berada pada tingkat keyakinan rendah."
        )
    else:
        opening = (
            "Pembacaan laut NELAYA-AI hari ini belum memiliki data yang memadai."
        )

    body = (
        f" Layer yang tersedia dan valid: {available_txt}. "
        f"Layer stale: {stale_txt}. "
        f"Layer missing: {missing_txt}. "
        f"Layer invalid: {invalid_txt}."
    )

    closing = (
        " Karena itu, informasi ini harus dibaca secara rendah hati sebagai bagian dari "
        "proses memahami laut, bukan sebagai kepastian lokasi ikan. Validasi lapangan "
        "dan pengalaman nelayan tetap menjadi bagian penting dari pembacaan NELAYA-AI."
    )

    return opening + body + closing
