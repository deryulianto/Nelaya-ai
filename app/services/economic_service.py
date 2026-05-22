from __future__ import annotations

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))

def estimate_fuel_liter(distance_km: float, km_per_liter: float = 1.4) -> float:
    if km_per_liter <= 0:
        km_per_liter = 1.4
    return round(distance_km / km_per_liter, 2)

def calculate_economic_score(
    fgi_probability: float,
    fuel_efficiency_score: float,
    risk_score: float,
    distance_score: float,
) -> float:
    score = (
        0.45 * clamp(fgi_probability)
        + 0.25 * clamp(fuel_efficiency_score)
        + 0.20 * clamp(risk_score)
        + 0.10 * clamp(distance_score)
    )
    return round(score * 100, 1)

def risk_to_score(risk_level: str) -> float:
    risk_level = (risk_level or "").lower()
    if risk_level == "rendah":
        return 0.9
    if risk_level == "sedang":
        return 0.6
    if risk_level == "tinggi":
        return 0.25
    return 0.5

def infer_risk_level(wave_m: float | None, wind_ms: float | None) -> str:
    """
    Risk awal berbasis gelombang dan angin.
    Rendah : wave < 1.5 m dan wind < 5 m/s
    Sedang : wave 1.5–2.5 m atau wind 5–8 m/s
    Tinggi : wave > 2.5 m atau wind > 8 m/s
    """

    wave = wave_m if isinstance(wave_m, (int, float)) else 0.0
    wind = wind_ms if isinstance(wind_ms, (int, float)) else 0.0

    if wave > 2.5 or wind > 8.0:
        return "tinggi"

    if wave >= 1.5 or wind >= 5.0:
        return "sedang"

    return "rendah"

def decision_label_from_score(score: float) -> str:
    """
    Label keputusan awal untuk nelayan.
    Ini bukan perintah melaut, tetapi bahasa bantu keputusan.
    """

    if score >= 80:
        return "sangat layak dipertimbangkan"

    if score >= 65:
        return "layak dipertimbangkan dengan kehati-hatian"

    if score >= 50:
        return "perlu pertimbangan tambahan"

    return "sebaiknya ditunda atau cari opsi lain"

def build_explanation(
    fgi_probability: float,
    risk_level: str,
    fuel_liter: float,
    estimated_trip_cost_idr: int,
    distance_km: float,
) -> list[str]:
    why = []

    if fgi_probability >= 0.75:
        why.append("FGI current-aware cukup tinggi sehingga peluang lingkungan relatif baik.")
    elif fgi_probability >= 0.55:
        why.append("FGI berada pada tingkat sedang sehingga peluang lingkungan masih perlu dibaca hati-hati.")
    else:
        why.append("FGI rendah sehingga peluang lingkungan belum cukup kuat.")

    if risk_level == "rendah":
        why.append("Risiko laut terbaca rendah berdasarkan gelombang dan angin.")
    elif risk_level == "sedang":
        why.append("Gelombang atau angin berada pada tingkat sedang sehingga perlu kehati-hatian.")
    else:
        why.append("Risiko laut tinggi sehingga keputusan melaut perlu dipertimbangkan ulang.")

    why.append(f"Estimasi BBM sekitar {fuel_liter:.2f} liter.")
    why.append(f"Estimasi biaya perjalanan sekitar Rp{estimated_trip_cost_idr:,.0f}.".replace(",", "."))
    why.append(f"Jarak estimasi perjalanan sekitar {distance_km:.1f} km dari pelabuhan.")

    return why

def advice_for_fishermen(
    decision_label: str,
    risk_level: str,
    economic_score: float
) -> str:

    if risk_level == "tinggi":
        return (
            "Risiko laut saat ini relatif tinggi. Pertimbangkan keselamatan, "
            "kondisi kapal, awak, serta alternatif waktu atau lokasi lain."
        )

    if economic_score >= 80:
        return (
            "Peluang lingkungan terlihat cukup baik. Tetap periksa kondisi "
            "kapal, BBM, dan perubahan cuaca sebelum berangkat."
        )

    if economic_score >= 65:
        return (
            "Peluang lingkungan cukup baik, tetapi perlu kehati-hatian. "
            "Perhatikan gelombang, kondisi awak, serta efisiensi perjalanan."
        )

    if economic_score >= 50:
        return (
            "Kondisi saat ini memerlukan pertimbangan tambahan. "
            "Membandingkan beberapa alternatif lokasi dapat membantu."
        )

    return (
        "Kondisi lingkungan saat ini belum cukup mendukung. "
        "Menunggu perubahan kondisi laut dapat menjadi pilihan."
    )

def economy_match(
    catch_kg: float | None,
    actual_fuel_liter: float | None,
    estimated_fuel_liter: float,
) -> str:

    if catch_kg is None:
        return "belum ada validasi"

    fuel = (
        actual_fuel_liter
        if isinstance(actual_fuel_liter, (int, float))
        else estimated_fuel_liter
    )

    if (
        catch_kg >= 40
        and fuel <= (estimated_fuel_liter + 3)
    ):
        return "cukup sesuai"

    if catch_kg >= 20:
        return "sebagian sesuai"

    return "belum sesuai"
