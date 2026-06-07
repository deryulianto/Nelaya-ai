from __future__ import annotations


CORE_LAYERS = [
    "chl_nrt",
    "sst_nrt",
    "wind_nrt",
    "wave_anfc",
    "ssh_anfc",
    "sal_anfc",
]

BIOLOGICAL_LAYERS = ["chl_nrt"]

PHYSICAL_LAYERS = [
    "sst_nrt",
    "wind_nrt",
    "wave_anfc",
    "ssh_anfc",
    "sal_anfc",
]


def build_confidence_from_health(health: dict) -> dict:
    checks = health.get("checks", [])
    status_map = {c.get("kind"): c.get("status") for c in checks}

    available_layers = [
        layer for layer in CORE_LAYERS
        if status_map.get(layer) == "available"
    ]

    stale_layers = [
        layer for layer in CORE_LAYERS
        if status_map.get(layer) == "stale"
    ]

    missing_layers = [
        layer for layer in CORE_LAYERS
        if status_map.get(layer) == "missing"
    ]

    invalid_layers = [
        layer for layer in CORE_LAYERS
        if status_map.get(layer) == "invalid"
    ]

    problematic_layers = [
        layer for layer in CORE_LAYERS
        if status_map.get(layer) not in ["available", "missing", None]
    ]

    available_count = len(available_layers)
    total_count = len(CORE_LAYERS)

    completeness_score = available_count / total_count if total_count else 0.0

    biological_ready = all(
        status_map.get(layer) == "available"
        for layer in BIOLOGICAL_LAYERS
    )

    biological_stale = any(
        status_map.get(layer) == "stale"
        for layer in BIOLOGICAL_LAYERS
    )

    physical_available_count = sum(
        1 for layer in PHYSICAL_LAYERS
        if status_map.get(layer) == "available"
    )

    physical_ready = physical_available_count >= 3
    physical_partial = physical_available_count >= 1

    if available_count >= 5 and biological_ready and physical_ready:
        level = "high"
        label = "High confidence"
        operational_status = "decision_support_ready"
    elif available_count >= 3 and physical_partial:
        level = "medium"
        label = "Medium confidence"
        operational_status = "indicative_decision_support"
    elif available_count >= 1:
        level = "low"
        label = "Low confidence"
        operational_status = "limited_indication_only"
    else:
        level = "unavailable"
        label = "Unavailable"
        operational_status = "no_advisory"

    warnings = []

    if biological_stale:
        warnings.append(
            "Lapisan biologis tersedia sebagai file, tetapi tanggal internalnya lebih tua dari snapshot."
        )

    if not biological_ready:
        warnings.append(
            "Lapisan biologis belum siap sepenuhnya untuk mendukung FGI."
        )

    if not physical_ready:
        warnings.append(
            "Lapisan fisika laut belum lengkap untuk advisory operasional penuh."
        )

    if invalid_layers:
        warnings.append(
            "Ada layer invalid dan tidak boleh dipakai sebagai dasar keputusan."
        )

    if missing_layers:
        warnings.append(
            "Beberapa layer belum tersedia pada path standar."
        )

    if level == "high":
        main_message = (
            "Data relatif lengkap dan dapat mendukung decision support, "
            "dengan catatan tetap memperhatikan kondisi lapangan."
        )
    elif level == "medium":
        main_message = (
            "Pembacaan NELAYA-AI cukup untuk indikasi keputusan awal, "
            "tetapi masih memerlukan kehati-hatian dan validasi lapangan."
        )
    elif level == "low":
        main_message = (
            "Pembacaan NELAYA-AI masih terbatas. Output boleh digunakan sebagai indikasi awal, "
            "bukan advisory operasional penuh."
        )
    else:
        main_message = (
            "Data belum cukup untuk menghasilkan pembacaan laut yang bertanggung jawab."
        )

    return {
        "module": "ocean_confidence",
        "version": "0.1.0",
        "snapshot_date": health.get("snapshot_date"),
        "confidence": {
            "level": level,
            "label": label,
            "operational_status": operational_status,
            "completeness_score": round(completeness_score, 3),
            "available_layers": available_layers,
            "stale_layers": stale_layers,
            "missing_layers": missing_layers,
            "invalid_layers": invalid_layers,
            "problematic_layers": problematic_layers,
            "biological_ready": biological_ready,
            "biological_stale": biological_stale,
            "physical_available_count": physical_available_count,
            "physical_ready": physical_ready,
            "physical_partial": physical_partial,
            "message": main_message,
            "warnings": warnings,
        },
        "source_health_summary": health.get("summary", {}),
    }
