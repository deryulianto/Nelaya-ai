from __future__ import annotations

from typing import Any


def classify_sst(val: float | None) -> str:
    if val is None:
        return "unknown"
    if val >= 30.5:
        return "sangat_hangat"
    if val >= 29.0:
        return "hangat"
    if val >= 27.5:
        return "normal"
    return "sejuk"


def classify_chl(val: float | None) -> str:
    if val is None:
        return "unknown"
    if val >= 0.5:
        return "tinggi"
    if val >= 0.15:
        return "sedang"
    return "rendah"


def classify_wind(val: float | None) -> str:
    if val is None:
        return "unknown"
    if val >= 10:
        return "sangat_kencang"
    if val >= 6:
        return "kencang"
    if val >= 3:
        return "sedang"
    return "lemah"


def classify_wave(val: float | None) -> str:
    if val is None:
        return "unknown"
    if val >= 2.5:
        return "sangat_tinggi"
    if val >= 1.5:
        return "tinggi"
    if val >= 0.5:
        return "sedang"
    return "rendah"


def classify_iod(dmi: float | None) -> str:
    if dmi is None:
        return "unknown"
    if dmi >= 0.4:
        return "positive"
    if dmi <= -0.4:
        return "negative"
    return "neutral"


def build_daily_ocean_insight(
    sst: float | None,
    chl: float | None,
    wind: float | None,
    wave: float | None,
    sal: float | None,
    ssh: float | None,
    dmi: float | None,
) -> dict[str, Any]:
    sst_c = classify_sst(sst)
    chl_c = classify_chl(chl)
    wind_c = classify_wind(wind)
    wave_c = classify_wave(wave)
    iod_phase = classify_iod(dmi)

    drivers: list[str] = []
    risks: list[str] = []
    caution: list[str] = []

    if chl_c in {"sedang", "tinggi"}:
        drivers.append("produktivitas permukaan mendukung")
    else:
        caution.append("produktivitas permukaan masih terbatas")

    if sst_c in {"normal", "hangat"}:
        drivers.append("suhu permukaan masih relatif mendukung")
    elif sst_c == "sangat_hangat":
        risks.append("suhu permukaan sangat hangat")
    elif sst_c == "sejuk":
        caution.append("suhu permukaan relatif sejuk")

    if wind_c == "kencang":
        risks.append("angin cukup kuat")
    elif wind_c == "sangat_kencang":
        risks.append("angin sangat kuat")

    if wave_c == "tinggi":
        risks.append("gelombang cukup tinggi")
    elif wave_c == "sangat_tinggi":
        risks.append("gelombang sangat tinggi")

    positive_count = len(drivers)
    risk_count = len(risks)

    if positive_count >= 2 and risk_count <= 1:
        opportunity = "cukup_baik"
    elif risk_count >= 3:
        opportunity = "terbatas"
    else:
        opportunity = "menengah"

    sentences: list[str] = []

    if opportunity == "cukup_baik":
        sentences.append(
            "Kondisi laut hari ini menunjukkan peluang yang cukup baik berdasarkan kombinasi sinyal lokal yang relatif mendukung."
        )
    elif opportunity == "terbatas":
        sentences.append(
            "Kondisi laut hari ini cenderung menantang karena beberapa faktor risiko muncul bersamaan."
        )
    else:
        sentences.append(
            "Kondisi laut hari ini berada pada tingkat menengah, sehingga peluang tetap ada tetapi perlu dibaca dengan hati-hati."
        )

    if drivers:
        sentences.append("Sinyal pendukung utama: " + ", ".join(drivers) + ".")
    if risks:
        sentences.append("Faktor risiko utama: " + ", ".join(risks) + ".")
    if caution:
        sentences.append("Catatan kehati-hatian: " + ", ".join(caution) + ".")

    if iod_phase == "positive":
        sentences.append(
            "IOD berada pada fase positif, sehingga dapat memberi konteks regional tambahan terhadap dinamika perairan Indonesia bagian barat."
        )
    elif iod_phase == "negative":
        sentences.append(
            "IOD berada pada fase negatif, sehingga konteks regional perlu dibaca bersama sinyal lokal Aceh."
        )
    elif iod_phase == "neutral":
        sentences.append(
            "IOD berada pada kondisi netral, sehingga pembacaan hari ini terutama bertumpu pada sinyal lokal."
        )

    return {
        "classification": {
            "sst": sst_c,
            "chl": chl_c,
            "wind": wind_c,
            "wave": wave_c,
            "iod": iod_phase,
        },
        "opportunity": opportunity,
        "drivers": drivers,
        "risks": risks,
        "caution": caution,
        "summary": " ".join(sentences),
    }
