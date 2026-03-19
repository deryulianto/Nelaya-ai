from typing import Dict, Any


def _fmt(v, unit="", digits=2):
    if v is None:
        return None
    return f"{round(v, digits)}{unit}"


def classify_wave(w):
    if w is None:
        return None
    if w < 0.5:
        return "tenang"
    elif w < 1.25:
        return "rendah"
    elif w < 2.0:
        return "sedang"
    else:
        return "tinggi"


def classify_wind(w):
    if w is None:
        return None
    if w < 3:
        return "lemah"
    elif w < 7:
        return "sedang"
    else:
        return "kuat"


def classify_fgi(f):
    if f is None:
        return None
    if f < 0.3:
        return "rendah"
    elif f < 0.6:
        return "cukup"
    else:
        return "tinggi"


def build_ocean_narrative(
    region: str,
    today: Dict[str, Any],
    spatial: Dict[str, Any] | None = None,
    persona: str = "publik",
) -> Dict[str, str]:

    persona = (persona or "publik").strip().lower()

    wave = today.get("wave_m")
    wind = today.get("wind_ms")
    sst = today.get("sst_c")
    chl = today.get("chl_mg_m3")
    fgi = today.get("fgi_score")
    trend = today.get("trend")

    wave_txt = classify_wave(wave)
    wind_txt = classify_wind(wind)
    fgi_txt = classify_fgi(fgi)

    parts = []

    if wave is not None and wind is not None:
        parts.append(
            f"Gelombang di {region} berada pada kategori {wave_txt} (~{_fmt(wave, ' m')}) "
            f"dengan angin {wind_txt} (~{_fmt(wind, ' m/s')})."
        )

    if sst is not None and chl is not None:
        parts.append(
            f"Suhu permukaan laut sekitar {_fmt(sst, ' °C')} "
            f"dengan konsentrasi klorofil {_fmt(chl)} mg/m³."
        )

    if fgi is not None:
        parts.append(f"Indeks potensi ikan (FGI) berada pada level {fgi_txt}.")

    if trend:
        parts.append(f"Tren kondisi laut saat ini cenderung {trend}.")

    if spatial and spatial.get("bbox"):
        parts.append("Karena wilayah ini cukup luas, kondisi laut dapat bervariasi antar area.")

    summary = " ".join(parts) if parts else "Kondisi laut berhasil dibaca dari indikator utama yang tersedia."

    if persona == "nelayan":
        headline = "Pembacaan laut untuk operasi melaut."
        recommendation = (
            "Perhatikan gelombang dan angin sebelum berangkat, dan gunakan informasi ini sebagai pembacaan awal bersama kondisi lapangan."
        )
        caution = (
            "Keputusan melaut tetap harus mempertimbangkan perubahan cepat di lapangan, terutama pada wilayah terbuka."
        )
    elif persona in {"wisata", "surf", "surfer"}:
        headline = "Pembacaan laut untuk aktivitas wisata dan ombak."
        recommendation = (
            "Padukan informasi ombak, angin, dan akses lokasi sebelum menentukan waktu aktivitas di laut."
        )
        caution = (
            "Kondisi ombak dan angin dapat berubah cepat, sehingga pemeriksaan lapangan tetap penting."
        )
    elif persona in {"policy", "pembuat_kebijakan", "pemerintah"}:
        headline = "Pembacaan laut untuk pemantauan wilayah."
        recommendation = (
            "Gunakan ringkasan ini sebagai pembacaan awal untuk melihat dinamika wilayah dan kebutuhan pemantauan lanjutan."
        )
        caution = (
            "Wilayah laut yang luas dapat memperlihatkan variasi kondisi antar lokasi, sehingga interpretasi sebaiknya tidak bergantung pada satu titik saja."
        )
    else:
        headline = "Kondisi laut terpantau secara dinamis."
        recommendation = (
            "Gunakan informasi ini sebagai pembacaan awal, dan padukan dengan kondisi lapangan sebelum beraktivitas."
        )
        caution = (
            "Perubahan cuaca dan dinamika laut dapat terjadi cepat, terutama pada wilayah terbuka."
        )

    return {
        "headline": headline,
        "summary": summary,
        "recommendation": recommendation,
        "caution": caution,
    }