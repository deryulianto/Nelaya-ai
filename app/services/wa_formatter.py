from __future__ import annotations

from typing import Any, Dict, List


def _fmt_num(x: Any, digits: int = 0, default: str = "—") -> str:
    try:
        if x is None:
            return default
        return f"{float(x):.{digits}f}"
    except Exception:
        return default


def _bullet_lines(items: List[str]) -> str:
    cleaned = [str(x).strip() for x in items if str(x).strip()]
    if not cleaned:
        return "• Belum ada saran spesifik"
    return "\n".join(f"• {x}" for x in cleaned)


def _translate_level(label: Any) -> str:
    s = str(label or "").strip().lower()

    mapping = {
        "very strong": "Sangat kuat",
        "strong": "Kuat",
        "moderate": "Sedang",
        "weak": "Lemah",
        "high": "Tinggi",
        "low": "Rendah",
        "unknown": "Belum terbaca",
    }
    return mapping.get(s, str(label or "—"))


def format_whatsapp_text(brief: Dict[str, Any], audience: str = "nelayan") -> str:
    date = brief.get("date", "—")
    region = brief.get("region", "Aceh")

    osi = ((brief.get("scores") or {}).get("osi") or {})
    fgi = ((brief.get("scores") or {}).get("fgi") or {})
    spatial = brief.get("spatial") or {}

    osi_value = _fmt_num(osi.get("value"), 0)
    osi_label = _translate_level(osi.get("label", "—"))
    osi_conf = _fmt_num(osi.get("confidence"), 0)

    fgi_value = _fmt_num(fgi.get("value"), 0)
    fgi_label = _translate_level(fgi.get("label", "—"))

    hotspot_count = _fmt_num(spatial.get("hotspot_count"), 0)
    summary_short = brief.get("summary_short", "Belum ada ringkasan.")
    actions = brief.get("actions") or []
    warnings = brief.get("warnings") or []
    links = brief.get("links") or {}
    detail_link = links.get("insights") or links.get("dashboard") or links.get("map") or ""

    if audience == "stakeholder":
        strong_regions = spatial.get("strong_regions") or []
        weak_regions = spatial.get("weak_regions") or []

        strong_text = ", ".join(strong_regions[:3]) if strong_regions else "Belum teridentifikasi"
        weak_text = ", ".join(weak_regions[:2]) if weak_regions else "Belum teridentifikasi"

        msg = (
            f"📘 NELAYA-AI Ringkas Laut Harian | {region} | {date}\n\n"
            f"Indeks kondisi laut (OSI): {osi_value} ({osi_label})\n"
            f"Indeks potensi ikan (FGI): {fgi_value} ({fgi_label})\n"
            f"Titik menonjol: {hotspot_count} grid\n"
            f"Keyakinan data: {osi_conf}\n\n"
            f"Makna cepat:\n{summary_short}\n\n"
            f"Wilayah relatif kuat:\n{strong_text}\n\n"
            f"Wilayah relatif lemah:\n{weak_text}\n\n"
            f"Saran:\n{_bullet_lines(actions)}\n\n"
            f"Catatan: ini alat bantu pembacaan kondisi laut. Tetap rujuk BMKG dan verifikasi lapangan.\n\n"
            f"Detail:\n{detail_link}"
        )
        return msg

    if audience == "internal":
        signals = brief.get("signals") or {}
        msg = (
            f"🧪 NELAYA-AI Ringkas Internal | {region} | {date}\n\n"
            f"Kondisi laut (OSI): {osi_value} ({osi_label}) • keyakinan {osi_conf}\n"
            f"Potensi ikan (FGI): {fgi_value} ({fgi_label})\n"
            f"Titik menonjol: {hotspot_count}\n\n"
            f"Sinyal:\n"
            f"- SST: {_fmt_num(signals.get('sst_c'), 2)} °C\n"
            f"- CHL: {_fmt_num(signals.get('chl_mg_m3'), 3)} mg/m³\n"
            f"- Angin: {_fmt_num(signals.get('wind_ms'), 1)} m/s\n"
            f"- Gelombang: {_fmt_num(signals.get('wave_m'), 2)} m\n"
            f"- Salinitas: {_fmt_num(signals.get('sal_psu'), 2)} psu\n\n"
            f"Ringkasan:\n{summary_short}\n\n"
            f"Tindak lanjut:\n{_bullet_lines(actions)}\n\n"
            f"Peringatan:\n{_bullet_lines(warnings)}\n\n"
            f"Detail:\n{detail_link}"
        )
        return msg

    warning_line = "Catatan: tetap cek BMKG dan kondisi lapangan."
    if warnings:
        warning_line = f"Catatan: {warnings[0]}"

    msg = (
        f"🌊 NELAYA-AI PAGI | {region} | {date}\n\n"
        f"Kondisi laut (OSI): {osi_value} ({osi_label})\n"
        f"Potensi ikan (FGI): {fgi_value} ({fgi_label})\n"
        f"Titik menonjol: {hotspot_count} grid\n"
        f"Keyakinan data: {osi_conf}\n\n"
        f"Makna cepat:\n{summary_short}\n\n"
        f"Saran:\n{_bullet_lines(actions)}\n\n"
        f"{warning_line}\n\n"
        f"Detail peta:\n{detail_link}"
    )
    return msg