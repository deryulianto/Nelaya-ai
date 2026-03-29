from __future__ import annotations

from typing import Dict, List

# Intent resmi Tanya NELAYA-AI
INTENT_OCEAN_CONDITION = "ocean_condition"
INTENT_METRIC_EXPLAINER = "metric_explainer"
INTENT_SAFETY_CHECK = "safety_check"
INTENT_TREND_ANALYSIS = "trend_analysis"
INTENT_FGI_INDICATOR = "fgi_indicator"
INTENT_FGI_COMPARE = "fgi_compare"
INTENT_RELATIVE_OPPORTUNITY = "relative_opportunity"
INTENT_OPERATIONAL_PLAN = "operational_plan"
INTENT_KNOWLEDGE_ADAT = "knowledge_adat"
INTENT_REGULATION_QUERY = "regulation_query"
INTENT_REFERENCE_DATA_QUERY = "reference_data_query"
INTENT_FALLBACK = "fallback"

ALL_INTENTS: List[str] = [
    INTENT_OCEAN_CONDITION,
    INTENT_METRIC_EXPLAINER,
    INTENT_SAFETY_CHECK,
    INTENT_TREND_ANALYSIS,
    INTENT_FGI_INDICATOR,
    INTENT_FGI_COMPARE,
    INTENT_RELATIVE_OPPORTUNITY,
    INTENT_OPERATIONAL_PLAN,
    INTENT_KNOWLEDGE_ADAT,
    INTENT_REGULATION_QUERY,
    INTENT_REFERENCE_DATA_QUERY,
    INTENT_FALLBACK,
]

# Prioritas penting agar query tidak salah lari
INTENT_PRIORITY: List[str] = [
    INTENT_REGULATION_QUERY,
    INTENT_KNOWLEDGE_ADAT,
    INTENT_REFERENCE_DATA_QUERY,
    INTENT_FGI_COMPARE,
    INTENT_OPERATIONAL_PLAN,
    INTENT_RELATIVE_OPPORTUNITY,
    INTENT_SAFETY_CHECK,
    INTENT_TREND_ANALYSIS,
    INTENT_FGI_INDICATOR,
    INTENT_METRIC_EXPLAINER,
    INTENT_OCEAN_CONDITION,
    INTENT_FALLBACK,
]

# Keyword sederhana dulu: rule-based
INTENT_KEYWORDS: Dict[str, List[str]] = {
    INTENT_REGULATION_QUERY: [
        "qanun", "peraturan", "regulasi", "pasal", "ayat", "izin",
        "dilarang", "boleh", "tidak boleh", "rumpon", "alat tangkap",
        "jalur penangkapan", "zona penangkapan", "konservasi", "rzwp", "rzwp3k",
        "permen", "pp ", "uu ", "undang-undang", "sipr",
        "apa itu qanun", "apa itu rumpon", "aturan rumpon", "apa aturan rumpon",
        "pasal tentang rumpon",
    ],
    INTENT_KNOWLEDGE_ADAT: [
        "panglima laot", "panglima laot lhok", "adat laut",
        "masyarakat hukum adat laut", "apa itu panglima laot",
        "fungsi panglima laot", "apa itu adat laut",
    ],
    INTENT_REFERENCE_DATA_QUERY: [
        "pelabuhan terdekat", "port terdekat", "jumlah pulau", "pulau kecil",
        "daftar pelabuhan", "surf spot terdekat", "lokasi surfing terdekat",
        "berapa jumlah pelabuhan", "berapa jumlah pulau kecil",
    ],
    INTENT_FGI_COMPARE: [
        "apa beda fgi", "beda fgi env", "beda fgi-r",
        "perbedaan fgi env dan fgi-r", "apa beda fgi env dan fgi-r",
        "kapan pakai fgi env dan fgi-r",
    ],
    INTENT_OPERATIONAL_PLAN: [
        "budget", "hemat bbm", "dari mana paling masuk akal", "origin",
        "biaya", "optimalkan", "optimize", "pelabuhan asal",
    ],
    INTENT_RELATIVE_OPPORTUNITY: [
        "area lebih menjanjikan", "hotspot", "potensi ikan di mana",
        "mana area", "lebih baik di mana", "relatif lebih menjanjikan",
        "mana lokasi yang lebih baik", "spot mana yang lebih menjanjikan",
    ],
    INTENT_SAFETY_CHECK: [
        "aman melaut", "ombak aman", "gelombang aman", "aman untuk kapal kecil",
        "aman hari ini", "waspada ombak", "aman atau tidak",
        "apakah aman melaut hari ini", "apakah ombak hari ini aman",
        "ombak hari ini aman atau tidak", "gelombang hari ini aman atau tidak",
        "aman untuk kapal kecil hari ini",
    ],
    INTENT_TREND_ANALYSIS: [
        "tren", "trend", "minggu ini", "kemarin", "minggu lalu", "riwayat",
        "history", "naik turun", "dibanding kemarin", "dibanding minggu lalu",
    ],
    INTENT_FGI_INDICATOR: [
        "fgi rendah", "arti fgi", "mengapa fgi", "skor fgi", "fgi hari ini",
        "fish ground index", "apa itu fgi", "apa arti fgi",
        "mengapa peluang ikan rendah",
    ],
    INTENT_METRIC_EXPLAINER: [
        "apa itu sst", "apa arti sst", "apa itu ssh", "apa arti ssh",
        "mengapa klorofil", "apa itu klorofil", "apa itu chlorophyll",
        "mengapa suhu laut", "apa arti gelombang", "apa arti angin",
    ],
    INTENT_OCEAN_CONDITION: [
        "laut aceh hari ini", "laut hari ini", "kondisi laut", "bagaimana laut",
        "apa yang berubah", "kondisi aceh hari ini",
        "gelombang hari ini", "ombak hari ini",
        "bagaimana gelombang hari ini", "bagaimana ombak hari ini",
        "bagaimana ketinggian gelombang hari ini",
        "berapa tinggi gelombang hari ini", "ketinggian gelombang hari ini",
        "tinggi gelombang hari ini", "berapa tinggi ombak hari ini",
        "ketinggian ombak hari ini", "tinggi ombak hari ini",
        "kondisi gelombang hari ini", "kondisi ombak hari ini",
    ],
}

METRIC_KEYWORDS = {
    "wave": [
        "gelombang", "ombak", "wave", "surf",
        "tinggi gelombang", "ketinggian gelombang",
        "tinggi ombak", "ketinggian ombak",
    ],
    "wind": ["angin", "wind"],
    "sst": ["sst", "suhu laut", "sea surface temperature"],
    "chl": ["klorofil", "chlorophyll", "chl", "chlorophyll-a", "klorofil-a"],
    "ssh": ["ssh", "sea surface height", "muka laut"],
    "fgi": ["fgi", "fish ground index"],
    "osi": ["osi", "ocean state index"],
    "current": ["arus", "current"],
}
