from __future__ import annotations

from typing import Any, Dict, Optional


def _fmt_num(v: Any, digits: int = 2) -> Optional[str]:
    try:
        if v is None:
            return None
        return f"{float(v):.{digits}f}"
    except Exception:
        return None


def _headline_for_safety(score: float) -> str:
    if score >= 0.80:
        return "Kondisi relatif aman untuk melaut."
    if score >= 0.60:
        return "Kondisi cukup aman, tetapi tetap perlu waspada."
    if score >= 0.40:
        return "Kondisi perlu diwaspadai untuk operasi melaut."
    return "Kondisi cenderung berisiko untuk melaut."


def _headline_for_opportunity(score: float) -> str:
    if score >= 0.75:
        return "Peluang kondisi penangkapan relatif baik."
    if score >= 0.50:
        return "Peluang penangkapan berada pada level sedang."
    return "Peluang penangkapan saat ini cenderung rendah."


def _metric_explanation(metric: Optional[str]) -> Dict[str, str]:
    m = (metric or "").strip().lower()

    if m == "fgi":
        return {
            "headline": "FGI adalah indikator peluang relatif area penangkapan ikan.",
            "summary": "FGI membantu membaca apakah kombinasi kondisi oseanografi cenderung mendukung atau kurang mendukung peluang ikan. Ini indikator pendukung, bukan jaminan hasil tangkap.",
            "recommendation": "Gunakan FGI bersama indikator lain seperti gelombang, angin, dan pengalaman lapangan.",
            "caution": "FGI sebaiknya dibaca sebagai petunjuk, bukan kepastian.",
        }

    if m in {"chlorophyll", "chl"}:
        return {
            "headline": "Chlorophyll membantu membaca produktivitas perairan.",
            "summary": "Secara sederhana, chlorophyll memberi petunjuk tentang keberadaan fitoplankton yang menjadi dasar rantai makanan laut.",
            "recommendation": "Baca bersama suhu laut dan dinamika arus agar interpretasinya lebih utuh.",
            "caution": "Nilai tinggi tidak selalu langsung berarti banyak ikan di lokasi yang sama.",
        }

    if m == "sst":
        return {
            "headline": "SST adalah suhu permukaan laut.",
            "summary": "Suhu permukaan laut penting karena memengaruhi kenyamanan habitat, produktivitas, dan dinamika massa air.",
            "recommendation": "Gunakan bersama chlorophyll dan arus untuk membaca kondisi perikanan secara lebih baik.",
            "caution": "Suhu ideal dapat berbeda tergantung spesies dan wilayah.",
        }

    if m == "mpi":
        return {
            "headline": "MPI dibaca sebagai indikator perlindungan atau sensitivitas kawasan laut.",
            "summary": "Maknanya bergantung pada definisi kartu atau modul yang dipakai dalam sistem NELAYA-AI.",
            "recommendation": "Untuk publik, tampilkan MPI bersama penjelasan sederhana dan konteks wilayah.",
            "caution": "Definisi operasional MPI perlu dibuat konsisten di seluruh portal.",
        }

    return {
        "headline": "Istilah ini adalah bagian dari indikator pembacaan laut.",
        "summary": "Indikator dalam NELAYA-AI dipakai untuk membantu memahami kondisi laut secara lebih terstruktur.",
        "recommendation": "Baca indikator bersama konteks lokasi dan waktu.",
        "caution": "Satu indikator saja tidak cukup untuk menggambarkan seluruh kondisi laut.",
    }


def _numeric_lookup_answer(
    question: str,
    region: Optional[str],
    metric: Optional[str],
    today: Dict[str, Any],
    trend: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    q = (question or "").lower()
    region_label = region or "wilayah ini"

    metric_name = metric
    if not metric_name:
        if "gelombang" in q:
            metric_name = "wave"
        elif "angin" in q:
            metric_name = "wind"
        elif "sst" in q or "suhu" in q:
            metric_name = "sst"
        elif "chlorophyll" in q or "chl" in q:
            metric_name = "chlorophyll"
        elif "fgi" in q:
            metric_name = "fgi"
        elif "ssh" in q:
            metric_name = "ssh"

    if metric_name == "wave":
        val = today.get("wave_m")
        if val is None:
            return None
        return {
            "answer": {
                "headline": f"Tinggi gelombang di {region_label} hari ini sekitar {_fmt_num(val)} m.",
                "summary": f"Nilai gelombang permukaan yang terbaca untuk {region_label} saat ini sekitar {_fmt_num(val)} meter.",
                "recommendation": "Tetap baca bersama angin dan kondisi lapangan sebelum berangkat.",
                "caution": "Ini adalah pembacaan data sistem dan tetap perlu diverifikasi dengan kondisi nyata di laut.",
            },
            "evidence": {
                "wave_m": today.get("wave_m"),
                "wind_ms": today.get("wind_ms"),
                "sst_c": today.get("sst_c"),
                "chl_mg_m3": today.get("chl_mg_m3"),
                "fgi_score": None,
                "trend": trend.get("trend"),
            },
        }

    if metric_name == "wind":
        val = today.get("wind_ms")
        if val is None:
            return None
        return {
            "answer": {
                "headline": f"Kecepatan angin di {region_label} hari ini sekitar {_fmt_num(val)} m/s.",
                "summary": f"Angin permukaan yang terbaca untuk {region_label} saat ini sekitar {_fmt_num(val)} meter per detik.",
                "recommendation": "Baca bersama gelombang dan perubahan cuaca lapangan.",
                "caution": "Nilai angin dapat berubah cepat tergantung waktu dan lokasi operasional.",
            },
            "evidence": {
                "wave_m": today.get("wave_m"),
                "wind_ms": today.get("wind_ms"),
                "sst_c": today.get("sst_c"),
                "chl_mg_m3": today.get("chl_mg_m3"),
                "fgi_score": None,
                "trend": trend.get("trend"),
            },
        }

    if metric_name == "sst":
        val = today.get("sst_c")
        if val is None:
            return None
        return {
            "answer": {
                "headline": f"Suhu permukaan laut di {region_label} hari ini sekitar {_fmt_num(val)} °C.",
                "summary": f"SST yang terbaca untuk {region_label} saat ini sekitar {_fmt_num(val)} derajat Celsius.",
                "recommendation": "Baca bersama chlorophyll dan dinamika arus bila dipakai untuk analisis perikanan.",
                "caution": "Suhu laut adalah salah satu indikator dan tidak cukup dibaca sendirian.",
            },
            "evidence": {
                "wave_m": today.get("wave_m"),
                "wind_ms": today.get("wind_ms"),
                "sst_c": today.get("sst_c"),
                "chl_mg_m3": today.get("chl_mg_m3"),
                "fgi_score": None,
                "trend": trend.get("trend"),
            },
        }

    if metric_name in {"chlorophyll", "chl"}:
        val = today.get("chl_mg_m3")
        if val is None:
            return None
        return {
            "answer": {
                "headline": f"Nilai chlorophyll di {region_label} hari ini sekitar {_fmt_num(val)} mg/m³.",
                "summary": f"Chlorophyll permukaan yang terbaca untuk {region_label} saat ini sekitar {_fmt_num(val)} mg per meter kubik.",
                "recommendation": "Gunakan bersama suhu laut dan indikator peluang ikan agar interpretasi lebih utuh.",
                "caution": "Nilai chlorophyll tidak otomatis berarti banyak ikan di titik yang sama.",
            },
            "evidence": {
                "wave_m": today.get("wave_m"),
                "wind_ms": today.get("wind_ms"),
                "sst_c": today.get("sst_c"),
                "chl_mg_m3": today.get("chl_mg_m3"),
                "fgi_score": None,
                "trend": trend.get("trend"),
            },
        }

    return None


def build_answer(
    question: str,
    intent: str,
    persona: str,
    mode: str,
    region: Optional[str],
    today: Dict[str, Any],
    fgi: Dict[str, Any],
    trend: Dict[str, Any],
    reasoning: Dict[str, Any],
) -> Dict[str, Any]:
    scores = reasoning.get("scores", {})
    safety_score = float(scores.get("safety_score", 0.0) or 0.0)
    opportunity_score = float(scores.get("opportunity_score", 0.0) or 0.0)
    metric = reasoning.get("metric")
    question_type = reasoning.get("question_type")

    if question_type == "numeric_lookup":
        numeric = _numeric_lookup_answer(question, region, metric, today, trend)
        if numeric is not None:
            return {
                "answer": numeric["answer"],
                "evidence": numeric["evidence"],
                "scores": scores,
                "explanation": reasoning.get("explanation", []),
            }

    if intent == "metric_explanation":
        answer = _metric_explanation(metric or "fgi")
        return {
            "answer": answer,
            "evidence": {},
            "scores": {
                "confidence_score": scores.get("confidence_score", 0.75)
            },
            "explanation": reasoning.get("explanation", []),
        }

    if intent == "trend_analysis":
        metric_name = trend.get("metric", "indikator")
        today_v = trend.get("today")
        avg_7d = trend.get("avg_7d")
        anomaly = trend.get("anomaly")
        trend_name = trend.get("trend", "unknown")

        headline = f"Tren {metric_name} saat ini cenderung {trend_name}."
        summary = (
            f"Nilai terbaru {metric_name} sekitar {_fmt_num(today_v)} "
            f"dengan rerata 7 hari sekitar {_fmt_num(avg_7d)}."
        )
        recommendation = "Gunakan tren ini sebagai konteks, bukan satu-satunya dasar keputusan."
        caution = (
            f"Anomali terhadap baseline saat ini sekitar {_fmt_num(anomaly)}."
            if anomaly is not None else
            "Data tren masih perlu dibaca bersama indikator lain."
        )
        return {
            "answer": {
                "headline": headline,
                "summary": summary,
                "recommendation": recommendation,
                "caution": caution,
            },
            "evidence": trend,
            "scores": scores,
            "explanation": reasoning.get("explanation", []),
        }

    if intent == "safety_check":
        headline = _headline_for_safety(safety_score)
        summary = (
            "Gelombang dan angin masih dalam kisaran yang cukup bersahabat untuk operasi skala kecil."
            if safety_score >= 0.80 else
            "Ada sinyal yang masih cukup mendukung, tetapi perubahan lapangan tetap perlu diperhatikan."
            if safety_score >= 0.60 else
            "Kondisi permukaan menunjukkan perlunya kehati-hatian lebih tinggi."
            if safety_score >= 0.40 else
            "Indikator keselamatan menunjukkan risiko yang tidak kecil."
        )
        recommendation = (
            "Berangkat pagi lebih disarankan dan tetap pantau perubahan angin serta gelombang."
            if safety_score >= 0.60 else
            "Tunda operasi yang terlalu jauh atau gunakan pertimbangan lapangan yang sangat hati-hati."
        )
        caution = "Keputusan akhir tetap harus mempertimbangkan kondisi nyata di lapangan."

    elif intent == "fishing_recommendation":
        headline = _headline_for_opportunity(opportunity_score)
        summary = (
            "Kombinasi indikator oseanografi menunjukkan peluang yang cukup mendukung."
            if opportunity_score >= 0.75 else
            "Kondisi oseanografi menunjukkan peluang sedang, belum pada kondisi puncak."
            if opportunity_score >= 0.50 else
            "Indikator produktivitas belum menunjukkan dukungan yang kuat."
        )
        recommendation = (
            "Gunakan area prioritas yang dekat dan efisien, terutama bila keselamatan masih baik."
            if safety_score >= 0.60 else
            "Utamakan keselamatan terlebih dahulu sebelum mengejar peluang tangkap."
        )
        caution = "Peluang ikan tetap dipengaruhi dinamika lapangan dan pengalaman lokal."

    elif intent == "regulation_lookup":
        headline = "Aturan perlu dibaca berdasarkan lokasi dan jenis aktivitas."
        summary = (
            "Untuk topik seperti rumpon, alat tangkap, atau kawasan konservasi, interpretasi harus dikaitkan dengan wilayah dan ketentuan yang berlaku."
        )
        recommendation = "Tampilkan jawaban regulasi bersama sumber aturan dan area yang dimaksud."
        caution = "Jawaban regulasi tidak boleh dilepas dari dokumen hukum yang menjadi rujukan."

    elif intent == "system_explanation":
        headline = "Rekomendasi sistem dibentuk dari data, rule, dan tren."
        summary = (
            "Ocean Brain membaca kondisi laut terbaru, memberi bobot pada keselamatan dan peluang, lalu menyusun jawaban sesuai konteks pertanyaan."
        )
        recommendation = "Gunakan penjelasan evidence dan confidence untuk membangun kepercayaan pengguna."
        caution = "Jika data belum lengkap, keyakinan sistem juga ikut menurun."

    else:
        headline = "Kondisi laut hari ini sudah terbaca secara umum."
        summary = (
            "Sistem merangkum indikator utama seperti gelombang, angin, suhu laut, chlorophyll, dan FGI untuk membaca kondisi wilayah."
        )
        recommendation = "Gunakan ringkasan ini sebagai pembacaan awal sebelum mengambil keputusan."
        caution = "Pembacaan terbaik tetap menggabungkan data sistem dan pengamatan lapangan."

    evidence = {
        "wave_m": today.get("wave_m"),
        "wind_ms": today.get("wind_ms"),
        "sst_c": today.get("sst_c"),
        "chl_mg_m3": today.get("chl_mg_m3"),
        "fgi_score": fgi.get("fgi_score"),
        "trend": trend.get("trend"),
    }

    return {
        "answer": {
            "headline": headline,
            "summary": summary,
            "recommendation": recommendation,
            "caution": caution,
        },
        "evidence": evidence,
        "scores": scores,
        "explanation": reasoning.get("explanation", []),
    }