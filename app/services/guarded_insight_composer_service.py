from __future__ import annotations


LAYER_LABELS = {
    "sst_nrt": "Suhu permukaan laut/SST",
    "chl_nrt": "Klorofil-a/CHL",
    "wind_nrt": "Angin permukaan",
    "wave_anfc": "Gelombang laut",
    "ssh_anfc": "Tinggi muka laut/SSH",
    "sal_anfc": "Salinitas",
}


def _label_layers(layers: list[str]) -> list[str]:
    return [LAYER_LABELS.get(layer, layer) for layer in layers]


def _join_id(items: list[str]) -> str:
    if not items:
        return "tidak ada"

    if len(items) == 1:
        return items[0]

    return ", ".join(items[:-1]) + ", dan " + items[-1]


def build_guarded_insight_from_guardrail(guardrail_payload: dict) -> dict:
    guardrail = guardrail_payload.get("guardrail", {})
    template = guardrail_payload.get("insight_template", {})
    source_layers = guardrail_payload.get("source_layers", {})
    source_confidence = guardrail_payload.get("source_confidence", {})

    level = guardrail.get("readiness_level")
    advisory_allowed = guardrail.get("advisory_allowed", False)
    allowed_claim_level = guardrail.get("allowed_claim_level")

    available_layers = _label_layers(source_layers.get("available_layers", []))
    stale_layers = _label_layers(source_layers.get("stale_layers", []))
    missing_layers = _label_layers(source_layers.get("missing_layers", []))
    invalid_layers = _label_layers(source_layers.get("invalid_layers", []))

    available_txt = _join_id(available_layers)
    stale_txt = _join_id(stale_layers)
    missing_txt = _join_id(missing_layers)
    invalid_txt = _join_id(invalid_layers)

    if level == "high":
        title = "Membaca Laut Aceh dengan Dukungan Data yang Relatif Lengkap"
        subtitle = "NELAYA-AI membaca kondisi laut dengan confidence tinggi, namun tetap menjaga kehati-hatian lapangan."
        opening = (
            "NELAYA-AI hari ini membaca kondisi laut Aceh dengan dukungan data yang relatif lengkap. "
            "Pembacaan ini dapat menjadi decision support, dengan tetap memperhatikan kondisi lokal, keselamatan, dan pengalaman nelayan."
        )
        interpretation = (
            "Karena sebagian besar layer utama tersedia, sistem memiliki dasar yang lebih kuat untuk membaca dinamika laut. "
            "Namun, pembacaan ini tetap bukan jaminan hasil tangkapan."
        )

    elif level == "medium":
        title = "Membaca Indikasi Awal Laut Aceh dengan Kehati-hatian"
        subtitle = "Sebagian data utama tersedia, tetapi NELAYA-AI tetap menempatkan hasil ini sebagai indikasi awal."
        opening = (
            "NELAYA-AI hari ini menangkap indikasi awal kondisi laut Aceh. "
            "Pembacaan dapat membantu memahami arah perubahan laut, tetapi belum boleh diperlakukan sebagai advisory operasional penuh."
        )
        interpretation = (
            "Sistem mulai memiliki beberapa sinyal yang dapat dibaca, namun validasi lapangan dan kehati-hatian tetap diperlukan."
        )

    elif level == "low":
        title = "Membaca Laut Aceh Saat Data Masih Terbatas"
        subtitle = "Pembacaan hari ini hanya bersifat indikasi awal, bukan advisory operasional penuh."
        opening = (
            "NELAYA-AI hari ini hanya dapat memberikan pembacaan terbatas karena sebagian layer utama belum tersedia atau belum sepenuhnya siap. "
            "Karena itu, informasi ini perlu dibaca secara rendah hati sebagai indikasi awal."
        )
        interpretation = (
            "Dengan kondisi data saat ini, NELAYA-AI belum memiliki dasar yang cukup untuk menyampaikan arahan operasional. "
            "Pembacaan terutama berguna untuk memahami keterbatasan data dan menunggu pembaruan layer berikutnya."
        )

    else:
        title = "Menunggu Data Laut yang Lebih Memadai"
        subtitle = "NELAYA-AI belum memiliki cukup data untuk membaca kondisi laut secara bertanggung jawab."
        opening = (
            "NELAYA-AI hari ini belum memiliki data yang cukup untuk memberikan pembacaan laut yang bertanggung jawab."
        )
        interpretation = (
            "Sistem menahan diri dari membuat klaim kondisi laut karena data belum memadai."
        )

    data_status = (
        f"Layer yang tersedia dan valid: {available_txt}. "
        f"Layer yang stale: {stale_txt}. "
        f"Layer yang belum tersedia: {missing_txt}. "
        f"Layer yang invalid: {invalid_txt}."
    )

    safety_note = guardrail.get(
        "required_disclaimer",
        "Pembacaan ini harus digunakan secara hati-hati dan tetap memerlukan validasi lapangan.",
    )

    closing = (
        f"{safety_note} "
        "NELAYA-AI tetap menempatkan pengalaman nelayan, keselamatan melaut, dan validasi lapangan sebagai bagian penting dalam memahami laut."
    )

    return {
        "module": "guarded_insight_composer",
        "version": "0.1.0",
        "snapshot_date": guardrail_payload.get("snapshot_date"),
        "guarded_insight": {
            "title": title,
            "subtitle": subtitle,
            "readiness_level": level,
            "advisory_allowed": advisory_allowed,
            "allowed_claim_level": allowed_claim_level,
            "opening": opening,
            "data_status": data_status,
            "interpretation": interpretation,
            "safety_note": safety_note,
            "closing": closing,
            "full_text": "\n\n".join([
                title,
                subtitle,
                opening,
                data_status,
                interpretation,
                closing,
            ]),
        },
        "guardrail": guardrail,
        "source_confidence": source_confidence,
        "source_template": template,
    }
