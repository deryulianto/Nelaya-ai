from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from app.services.delta_insight import compute_delta, build_delta_sentence


# -----------------------------------------------------------------------------
# Prinsip NELAYA-AI
# 1. Narasi hanya boleh sejauh data mendukung.
# 2. Model menafsirkan sinyal, bukan menetapkan kepastian mutlak.
# 3. Ketidakpastian harus disebut bila data terbatas.
# 4. Semakin luas pembacaan, semakin rendah hati kesimpulan.
# -----------------------------------------------------------------------------


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Optional[float], digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "tidak tersedia"
    return f"{value:.{digits}f}{suffix}"


def _classify_sst(sst: Optional[float]) -> str:
    if sst is None:
        return "tidak diketahui"
    if sst >= 30.5:
        return "sangat hangat"
    if sst >= 29.0:
        return "hangat"
    if sst >= 27.5:
        return "normal"
    return "sejuk"


def _classify_chl(chl: Optional[float]) -> str:
    if chl is None:
        return "tidak diketahui"
    if chl >= 0.5:
        return "tinggi"
    if chl >= 0.15:
        return "sedang"
    return "rendah"


def _classify_wind(wind: Optional[float]) -> str:
    if wind is None:
        return "tidak diketahui"
    if wind >= 10:
        return "sangat kencang"
    if wind >= 6:
        return "kencang"
    if wind >= 3:
        return "sedang"
    return "lemah"


def _classify_wave(wave: Optional[float]) -> str:
    if wave is None:
        return "tidak diketahui"
    if wave >= 2.5:
        return "sangat tinggi"
    if wave >= 1.5:
        return "tinggi"
    if wave >= 0.5:
        return "sedang"
    return "rendah"


def _classify_index(
    value: Optional[float],
    high: float = 0.66,
    medium: float = 0.33,
) -> str:
    if value is None:
        return "tidak diketahui"
    if value >= high:
        return "tinggi"
    if value >= medium:
        return "sedang"
    return "rendah"


def _extract_metrics(payload: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """
    Mendukung beberapa bentuk payload:
    - flat: {"sst": ..., "chl": ..., "wind": ..., "wave": ...}
    - nested metrics: {"metrics": {"sst": {"value": ...}, ...}}
    - nested signals/today style
    """
    metrics = payload.get("metrics") or {}
    quick_compare = payload.get("quick_compare") or {}

    def pick(*keys: str) -> Optional[float]:
        for key in keys:
            # flat
            if key in payload:
                v = payload.get(key)
                if isinstance(v, dict):
                    vv = v.get("value")
                    f = _safe_float(vv)
                    if f is not None:
                        return f
                else:
                    f = _safe_float(v)
                    if f is not None:
                        return f

            # nested metrics
            if key in metrics:
                mv = metrics.get(key)
                if isinstance(mv, dict):
                    f = _safe_float(mv.get("value"))
                    if f is not None:
                        return f
                else:
                    f = _safe_float(mv)
                    if f is not None:
                        return f

        return None

    sst = pick("sst", "sea_surface_temperature", "thetao", "analysed_sst")
    chl = pick("chl", "chlorophyll", "chlor_a", "CHL")
    wind = pick("wind", "wind_speed")
    wave = pick("wave", "wave_height", "hs", "VHM0")
    sal = pick("sal", "salinity")
    ssh = pick("ssh", "sea_surface_height", "zos")
    fgi = pick("fgi", "fgi_score")
    osi = pick("osi", "ocean_stability_index", "ocean_status_index")
    msi = pick("msi", "marine_sustainability_index", "marine_stewardship_index")

    return {
        "sst": sst,
        "chl": chl,
        "wind": wind,
        "wave": wave,
        "sal": sal,
        "ssh": ssh,
        "fgi": fgi,
        "osi": osi,
        "msi": msi,
        "has_quick_compare": 1.0 if quick_compare else 0.0,
    }


@dataclass
class InsightContext:
    sst: Optional[float]
    chl: Optional[float]
    wind: Optional[float]
    wave: Optional[float]
    sal: Optional[float]
    ssh: Optional[float]
    fgi: Optional[float]
    osi: Optional[float]
    msi: Optional[float]

    sst_label: str
    chl_label: str
    wind_label: str
    wave_label: str

    fgi_label: str
    osi_label: str
    msi_label: str


def build_context(payload: Dict[str, Any]) -> InsightContext:
    m = _extract_metrics(payload)
    return InsightContext(
        sst=m["sst"],
        chl=m["chl"],
        wind=m["wind"],
        wave=m["wave"],
        sal=m["sal"],
        ssh=m["ssh"],
        fgi=m["fgi"],
        osi=m["osi"],
        msi=m["msi"],
        sst_label=_classify_sst(m["sst"]),
        chl_label=_classify_chl(m["chl"]),
        wind_label=_classify_wind(m["wind"]),
        wave_label=_classify_wave(m["wave"]),
        fgi_label=_classify_index(m["fgi"]),
        osi_label=_classify_index(m["osi"]),
        msi_label=_classify_index(m["msi"]),
    )


def determine_scenario(ctx: InsightContext) -> str:
    """
    Skenario fisik-biologis utama.
    """
    if ctx.wave is not None and ctx.wave >= 2.5:
        return "high_risk_sea"

    if ctx.sst is not None and ctx.sst >= 30.5:
        if ctx.chl is not None and ctx.chl < 0.15:
            return "thermal_stress_low_productivity"
        return "thermal_stress"

    if ctx.chl is not None and ctx.chl >= 0.5:
        if (ctx.wave is None or ctx.wave < 1.5) and (ctx.wind is None or ctx.wind < 10):
            return "productive_stable"
        return "productive_but_dynamic"

    if ctx.chl is not None and ctx.chl < 0.15:
        return "low_productivity"

    return "neutral_transition"


def build_data_points(ctx: InsightContext) -> List[str]:
    points: List[str] = []

    if ctx.sst is not None:
        points.append(f"SST {_fmt(ctx.sst, 2, ' °C')} ({ctx.sst_label})")
    if ctx.chl is not None:
        points.append(f"Klorofil {_fmt(ctx.chl, 2, ' mg/m³')} ({ctx.chl_label})")
    if ctx.wind is not None:
        points.append(f"Angin {_fmt(ctx.wind, 1, ' m/s')} ({ctx.wind_label})")
    if ctx.wave is not None:
        points.append(f"Gelombang {_fmt(ctx.wave, 1, ' m')} ({ctx.wave_label})")
    if ctx.sal is not None:
        points.append(f"Salinitas {_fmt(ctx.sal, 2, ' psu')}")
    if ctx.ssh is not None:
        points.append(f"SSH {_fmt(ctx.ssh, 2, ' cm')}")
    if ctx.fgi is not None:
        points.append(f"FGI {_fmt(ctx.fgi, 3)} ({ctx.fgi_label})")
    if ctx.osi is not None:
        points.append(f"OSI {_fmt(ctx.osi, 3)} ({ctx.osi_label})")
    if ctx.msi is not None:
        points.append(f"MSI {_fmt(ctx.msi, 3)} ({ctx.msi_label})")

    return points


def build_hook(scenario: str) -> str:
    hooks = {
        "productive_stable": "Laut Aceh hari ini menunjukkan fase yang relatif produktif dan cukup stabil.",
        "productive_but_dynamic": "Laut Aceh hari ini tampak produktif, namun tetap bergerak dalam dinamika yang aktif.",
        "high_risk_sea": "Laut Aceh hari ini memperlihatkan kondisi yang perlu dibaca dengan kehati-hatian lebih tinggi.",
        "thermal_stress": "Laut Aceh hari ini menunjukkan sinyal perairan yang sangat hangat.",
        "thermal_stress_low_productivity": "Laut Aceh hari ini mengarah pada kombinasi perairan sangat hangat dengan produktivitas yang lemah.",
        "low_productivity": "Laut Aceh hari ini cenderung berada pada fase produktivitas yang rendah.",
        "neutral_transition": "Laut Aceh hari ini berada pada fase transisi yang relatif netral.",
    }
    return hooks.get(scenario, "Laut Aceh hari ini menunjukkan dinamika yang menarik untuk dibaca.")


def build_scientific_interpretation(ctx: InsightContext, scenario: str) -> str:
    mapping = {
        "productive_stable": (
            "Kombinasi klorofil yang baik, gelombang yang masih terkendali, dan angin yang tidak terlalu ekstrem "
            "mengarah pada kondisi yang mendukung produktivitas perairan sekaligus aktivitas operasional."
        ),
        "productive_but_dynamic": (
            "Produktivitas perairan tampak terdukung, tetapi dinamika angin atau gelombang menunjukkan bahwa "
            "ruang operasional tetap perlu dibaca secara cermat."
        ),
        "high_risk_sea": (
            "Gelombang yang tinggi menjadi sinyal dominan bahwa risiko operasional meningkat, walaupun indikator lain "
            "mungkin masih terlihat mendukung."
        ),
        "thermal_stress": (
            "Suhu permukaan laut yang sangat hangat dapat menjadi penanda tekanan termal pada sistem laut, "
            "terutama bila kondisi ini bertahan dalam beberapa hari."
        ),
        "thermal_stress_low_productivity": (
            "Perairan yang sangat hangat disertai klorofil rendah dapat menunjukkan fase laut yang kurang subur, "
            "sekaligus memberi sinyal tekanan ekologis yang perlu diwaspadai."
        ),
        "low_productivity": (
            "Klorofil yang rendah menunjukkan dukungan produktivitas primer yang terbatas, sehingga peluang "
            "terbentuknya rantai makanan yang kuat juga cenderung melemah."
        ),
        "neutral_transition": (
            "Belum tampak satu sinyal yang sangat dominan, sehingga kondisi hari ini lebih tepat dibaca sebagai "
            "fase transisi antar-pola dinamika laut."
        ),
    }
    return mapping[scenario]


def build_integrated_diagnosis(ctx: InsightContext, scenario: str) -> Dict[str, str]:
    """
    Diagnosis gabungan v3:
    menghubungkan peluang ikan (FGI), kestabilan/kesehatan laut (OSI),
    dan keberlanjutan/tekanan (MSI) agar tidak terlalu sering jatuh ke mixed_conditions.
    """
    fgi_label = ctx.fgi_label
    osi_label = ctx.osi_label
    msi_label = ctx.msi_label

    if fgi_label == "tidak diketahui" and osi_label == "tidak diketahui" and msi_label == "tidak diketahui":
        return {
            "status": "indices_unavailable",
            "fgi_label": fgi_label,
            "osi_label": osi_label,
            "msi_label": msi_label,
            "message": "Indeks gabungan belum cukup lengkap, sehingga narasi hari ini lebih bertumpu pada sinyal fisik-biologis yang tersedia.",
        }

    if scenario == "thermal_stress" and osi_label == "tinggi" and msi_label in {"sedang", "tinggi"}:
        return {
            "status": "stable_but_warm",
            "fgi_label": fgi_label,
            "osi_label": osi_label,
            "msi_label": msi_label,
            "message": "Laut relatif stabil, tetapi tekanan panas tetap menuntut kehati-hatian dalam membaca kondisi hari ini.",
        }

    if fgi_label in {"sedang", "tinggi"} and (
        scenario in {"thermal_stress", "thermal_stress_low_productivity", "high_risk_sea"}
        or msi_label == "rendah"
    ):
        return {
            "status": "productive_but_stressed",
            "fgi_label": fgi_label,
            "osi_label": osi_label,
            "msi_label": msi_label,
            "message": "Peluang pemanfaatan masih terbuka, tetapi ada tekanan lingkungan yang membuat pembacaan harus lebih hati-hati.",
        }

    if fgi_label in {"sedang", "tinggi"} and osi_label in {"sedang", "tinggi"} and msi_label in {"sedang", "tinggi"}:
        return {
            "status": "supportive_conditions",
            "fgi_label": fgi_label,
            "osi_label": osi_label,
            "msi_label": msi_label,
            "message": "Kondisi laut hari ini relatif mendukung, meski tetap perlu dibaca sesuai batas-batas yang ditunjukkan data.",
        }

    if fgi_label == "rendah" and osi_label in {"sedang", "tinggi"} and msi_label in {"sedang", "tinggi"}:
        return {
            "status": "healthy_but_unproductive",
            "fgi_label": fgi_label,
            "osi_label": osi_label,
            "msi_label": msi_label,
            "message": "Laut relatif terjaga, tetapi belum menunjukkan peluang tangkap yang kuat pada hari ini.",
        }

    if msi_label == "rendah" or (osi_label == "rendah" and msi_label in {"rendah", "sedang"}):
        return {
            "status": "ecologically_cautious",
            "fgi_label": fgi_label,
            "osi_label": osi_label,
            "msi_label": msi_label,
            "message": "Sinyal keberlanjutan hari ini cenderung lemah, sehingga keputusan perlu dibuat secara lebih konservatif.",
        }

    return {
        "status": "mixed_conditions",
        "fgi_label": fgi_label,
        "osi_label": osi_label,
        "msi_label": msi_label,
        "message": "Indikator hari ini menunjukkan kondisi campuran yang tidak sepenuhnya mengarah pada satu pesan dominan.",
    }


def compute_confidence(ctx: InsightContext) -> str:
    """
    Tingkat keyakinan narasi berdasarkan kelengkapan sinyal utama.
    """
    available = sum([
        ctx.sst is not None,
        ctx.chl is not None,
        ctx.wind is not None,
        ctx.wave is not None,
        ctx.fgi is not None,
        ctx.osi is not None,
        ctx.msi is not None,
    ])

    if available >= 6:
        return "high"
    if available >= 4:
        return "medium"
    return "low"


def build_meaning_layer(scenario: str, integrated_status: str) -> str:
    if integrated_status == "stable_but_warm":
        return (
            "Data menunjukkan bahwa kestabilan laut hari ini belum hilang, tetapi tekanan panas mengingatkan bahwa keseimbangan tidak selalu berarti tanpa risiko."
        )

    if integrated_status == "productive_but_stressed":
        return (
            "Hari seperti ini menunjukkan bahwa peluang pemanfaatan dan tekanan lingkungan bisa hadir bersamaan, sehingga manfaat tidak boleh dibaca terpisah dari batas."
        )

    if integrated_status == "supportive_conditions":
        return (
            "Dalam keadaan seperti ini, laut tidak hanya menjadi ruang fisik, tetapi juga sistem yang masih memberi dukungan bagi kehidupan dan aktivitas manusia."
        )

    if integrated_status == "healthy_but_unproductive":
        return (
            "Ada hari ketika laut tampak relatif terjaga, tetapi belum membuka peluang tangkap yang kuat; itu pun bagian dari ritme alaminya."
        )

    if integrated_status == "ecologically_cautious":
        return (
            "Ketika sinyal keberlanjutan melemah, laut seakan meminta agar pembacaan manusia tidak hanya berhenti pada manfaat, tetapi juga pada tanggung jawab."
        )

    mapping = {
        "productive_stable": (
            "Dalam keadaan seperti ini, laut tidak hanya menjadi ruang fisik, tetapi juga sistem yang sedang membuka peluang kehidupan."
        ),
        "productive_but_dynamic": (
            "Laut memperlihatkan bahwa peluang dan kehati-hatian sering hadir bersamaan dalam satu waktu."
        ),
        "high_risk_sea": (
            "Laut mengingatkan bahwa tidak setiap hari dibuka untuk ditaklukkan; ada hari-hari yang lebih layak dibaca daripada dipaksa."
        ),
        "thermal_stress": (
            "Ketika laut memanas, kita diingatkan bahwa keseimbangan ekologis selalu memiliki batas yang tidak boleh terus-menerus ditekan."
        ),
        "thermal_stress_low_productivity": (
            "Saat tekanan termal bertemu dengan lemahnya produktivitas, laut memberi tanda bahwa keseimbangan bukan sesuatu yang bisa dianggap tetap."
        ),
        "low_productivity": (
            "Fase seperti ini mengingatkan bahwa laut juga memiliki masa tenang, masa hemat, dan masa pemulihan."
        ),
        "neutral_transition": (
            "Dalam masa transisi, laut seakan mengajarkan bahwa perubahan besar sering tumbuh dari sinyal-sinyal kecil."
        ),
    }
    return mapping[scenario]


def build_reflection_layer(scenario: str, integrated_status: str, confidence: str) -> str:
    if integrated_status == "stable_but_warm":
        base = (
            "Kestabilan yang masih tampak hari ini tidak boleh membuat kita lupa bahwa panas yang berlebihan sering menjadi tanda awal dari tekanan yang lebih dalam."
        )
    elif integrated_status == "productive_but_stressed":
        base = (
            "Saat peluang masih terlihat di tengah tekanan, mungkin di situlah manusia diuji untuk tidak membaca laut hanya dari manfaat sesaat."
        )
    elif integrated_status == "supportive_conditions":
        base = (
            "Ketika laut masih memberi dukungan, ada saatnya kita berhenti sejenak dan menyadari bahwa keteraturan seperti ini bukan sesuatu yang patut disikapi dengan kesombongan."
        )
    elif integrated_status == "healthy_but_unproductive":
        base = (
            "Tidak setiap kestabilan harus segera diterjemahkan menjadi hasil tangkap; kadang laut sedang menjaga ritmenya sendiri."
        )
    elif integrated_status == "ecologically_cautious":
        base = (
            "Saat sinyal keberlanjutan melemah, tugas manusia bukan sekadar mengambil keputusan, tetapi juga menahan diri."
        )
    else:
        base = {
            "productive_stable": (
                "Ada saatnya kita berhenti sejenak dan menyadari bahwa keteraturan seperti ini tidak hadir secara acak."
            ),
            "productive_but_dynamic": (
                "Keseimbangan di laut sering lahir bukan dari keadaan yang sepenuhnya tenang, tetapi dari hukum yang tetap bekerja."
            ),
            "high_risk_sea": (
                "Mungkin di situlah kita belajar bahwa membaca tanda lebih penting daripada memaksakan kehendak."
            ),
            "thermal_stress": (
                "Bila laut terus memberi tanda, barangkali manusialah yang perlu lebih jujur untuk mendengarkan."
            ),
            "thermal_stress_low_productivity": (
                "Ketika laut tampak melemah, sesungguhnya yang sedang diuji bukan hanya ekosistem, tetapi juga tanggung jawab manusia."
            ),
            "low_productivity": (
                "Tidak semua keadaan rendah berarti kosong; kadang ia adalah cara alam menjaga dirinya sendiri."
            ),
            "neutral_transition": (
                "Di fase yang tampak biasa, sering tersembunyi pelajaran tentang kesabaran dalam membaca perubahan."
            ),
        }[scenario]

    if confidence == "low":
        return base + " Namun karena data hari ini belum lengkap, kesimpulan ini perlu dijaga tetap hati-hati."
    if confidence == "medium":
        return base + " Pembacaan ini cukup berguna, tetapi tetap perlu diperlakukan sebagai indikasi, bukan kepastian mutlak."
    return base


def build_operational_advice(scenario: str, integrated_status: str) -> List[str]:
    advice_map = {
        "productive_stable": [
            "Peluang operasional relatif baik.",
            "Tetap cek variasi lokal di lapangan sebelum berangkat.",
        ],
        "productive_but_dynamic": [
            "Peluang masih ada, tetapi kondisi laut perlu dibaca lebih hati-hati.",
            "Prioritaskan area yang aman dan efisien secara operasional.",
        ],
        "high_risk_sea": [
            "Risiko operasional meningkat.",
            "Pertimbangkan penundaan atau pembatasan radius operasi.",
        ],
        "thermal_stress": [
            "Pantau perubahan kondisi beberapa hari ke depan.",
            "Perlu kehati-hatian bila suhu tinggi bertahan lama.",
        ],
        "thermal_stress_low_productivity": [
            "Peluang biologis cenderung melemah.",
            "Operasional perlu lebih selektif dan hemat.",
        ],
        "low_productivity": [
            "Peluang agregasi biologis cenderung terbatas.",
            "Gunakan strategi hemat dan evaluasi lokasi alternatif.",
        ],
        "neutral_transition": [
            "Belum ada sinyal dominan yang sangat kuat.",
            "Keputusan operasional sebaiknya mengandalkan pembacaan lokal tambahan.",
        ],
    }

    advice = advice_map[scenario][:]

    if integrated_status == "stable_but_warm":
        advice.append("Kondisi relatif stabil, tetapi panas laut tetap perlu diperhitungkan sebagai faktor pembatas.")
    elif integrated_status == "productive_but_stressed":
        advice.append("Peluang ada, tetapi jangan abaikan sinyal tekanan lingkungan saat mengambil keputusan.")
    elif integrated_status == "supportive_conditions":
        advice.append("Kondisi mendukung, namun keputusan tetap harus mengikuti variasi lokal dan pembacaan lapangan.")
    elif integrated_status == "healthy_but_unproductive":
        advice.append("Laut relatif terjaga, tetapi peluang tangkap belum tentu kuat pada hari ini.")
    elif integrated_status == "ecologically_cautious":
        advice.append("Gunakan keputusan yang lebih konservatif karena sinyal keberlanjutan belum cukup kuat.")

    return advice


def build_signature() -> str:
    return "Laut itu data.\nKita hanya perlu belajar membacanya. 🌊\nNELAYA-AI"


def generate_narrative(
    payload: Dict[str, Any],
    mode: str = "reflective",
    region_name: str = "Aceh, Indonesia",
) -> Dict[str, Any]:
    """
    mode:
      - operational
      - education
      - reflective
    """
    mode = (mode or "reflective").strip().lower()
    if mode not in {"operational", "education", "reflective"}:
        mode = "reflective"

    ctx = build_context(payload)
    scenario = determine_scenario(ctx)
    data_points = build_data_points(ctx)
    integrated = build_integrated_diagnosis(ctx, scenario)
    confidence = compute_confidence(ctx)
    delta = compute_delta()
    delta_sentence = build_delta_sentence(delta)

    hook = build_hook(scenario)
    scientific = build_scientific_interpretation(ctx, scenario)
    meaning = build_meaning_layer(scenario, integrated["status"])
    reflection = build_reflection_layer(scenario, integrated["status"], confidence)
    advice = build_operational_advice(scenario, integrated["status"])
    signature = build_signature()

    data_sentence = (
        "Data utama hari ini: " + "; ".join(data_points) + "."
        if data_points
        else "Data utama hari ini belum cukup lengkap untuk merangkum kondisi secara penuh."
    )

    confidence_sentence = {
        "high": "Keyakinan pembacaan relatif tinggi karena data utama cukup lengkap.",
        "medium": "Keyakinan pembacaan berada pada tingkat menengah karena sebagian data utama tersedia.",
        "low": "Keyakinan pembacaan masih rendah karena data utama belum lengkap.",
    }[confidence]

    if mode == "operational":
        title = "Ringkasan Operasional Laut Hari Ini"

        summary_parts = [
            hook,
            data_sentence,
            scientific,
        ]
        if delta_sentence:
            summary_parts.append(delta_sentence)
        summary_parts.extend([
            integrated["message"],
            confidence_sentence,
            " ".join(advice),
        ])
        summary = " ".join(summary_parts)

        body = [
            hook,
            data_sentence,
            scientific,
        ]
        if delta_sentence:
            body.append(delta_sentence)
        body.extend([
            integrated["message"],
            confidence_sentence,
            "Arahan operasional:",
            *[f"- {item}" for item in advice],
            signature,
        ])

    elif mode == "education":
        title = "Penjelasan Edukatif Dinamika Laut Hari Ini"

        summary_parts = [
            hook,
            data_sentence,
            scientific,
        ]
        if delta_sentence:
            summary_parts.append(delta_sentence)
        summary_parts.extend([
            integrated["message"],
            meaning,
            confidence_sentence,
        ])
        summary = " ".join(summary_parts)

        body = [
            hook,
            data_sentence,
            scientific,
        ]
        if delta_sentence:
            body.append(delta_sentence)
        body.extend([
            integrated["message"],
            meaning,
            confidence_sentence,
            signature,
        ])

    else:  # reflective
        title = "Narasi Reflektif Laut Hari Ini"

        summary_parts = [
            hook,
            data_sentence,
            scientific,
        ]
        if delta_sentence:
            summary_parts.append(delta_sentence)
        summary_parts.extend([
            integrated["message"],
            meaning,
            reflection,
        ])
        summary = " ".join(summary_parts)

        body = [
            hook,
            data_sentence,
            scientific,
        ]
        if delta_sentence:
            body.append(delta_sentence)
        body.extend([
            integrated["message"],
            meaning,
            reflection,
            confidence_sentence,
            signature,
        ])

    generated_at = datetime.now(timezone.utc).isoformat()

    return {
        "title": title,
        "region": region_name,
        "mode": mode,
        "scenario": scenario,
        "summary": summary,
        "body": body,
        "data_points": data_points,
        "operational_advice": advice,
        "generated_at": generated_at,
        "confidence": confidence,
        "integrated": integrated,
        "delta": delta,
        "delta_sentence": delta_sentence,
        "meta": {
            "sst": ctx.sst,
            "chl": ctx.chl,
            "wind": ctx.wind,
            "wave": ctx.wave,
            "sal": ctx.sal,
            "ssh": ctx.ssh,
            "fgi": ctx.fgi,
            "osi": ctx.osi,
            "msi": ctx.msi,
            "labels": {
                "sst": ctx.sst_label,
                "chl": ctx.chl_label,
                "wind": ctx.wind_label,
                "wave": ctx.wave_label,
                "fgi": ctx.fgi_label,
                "osi": ctx.osi_label,
                "msi": ctx.msi_label,
            },
        },
    }