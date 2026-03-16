from __future__ import annotations

INTENT_KEYWORDS = {
    "safety_check": [
        "aman melaut",
        "aman tidak",
        "berbahaya",
        "gelombang berbahaya",
        "aman kah",
        "apakah aman",
    ],
    "ocean_condition_today": [
        "kondisi laut",
        "keadaan laut",
        "laut hari ini",
        "cuaca laut",
        "kondisi hari ini",
    ],
    "fishing_recommendation": [
        "bagus untuk melaut",
        "potensi ikan",
        "peluang ikan",
        "spot ikan",
        "hasil tangkap",
        "fgi",
    ],
    "metric_explanation": [
        "apa itu",
        "arti",
        "maksud",
        "definisi",
        "jelaskan",
    ],
    "trend_analysis": [
        "tren",
        "naik atau turun",
        "7 hari",
        "30 hari",
        "minggu ini",
        "bulan ini",
        "anomali",
    ],
    "regulation_lookup": [
        "aturan",
        "regulasi",
        "rumpon",
        "boleh",
        "diperkenankan",
        "kawasan konservasi",
        "larangan",
    ],
    "system_explanation": [
        "kenapa sistem",
        "kenapa rekomendasi",
        "data apa yang dipakai",
        "mengapa hasilnya",
        "why",
    ],
    "species_context": [
        "tongkol",
        "tuna",
        "demersal",
        "pelagis",
        "kerapu",
        "spesies",
        "ikan",
    ],
}

METRIC_TERMS = {
    "fgi": ["fgi", "fish ground index"],
    "sst": ["sst", "suhu laut", "sea surface temperature"],
    "chlorophyll": ["chlorophyll", "chlorofil", "chl"],
    "wave": ["gelombang", "wave"],
    "wind": ["angin", "wind"],
    "mpi": ["mpi", "marine protection index"],
}

REGION_ALIASES = {
    "banda aceh": "Banda Aceh",
    "aceh besar": "Aceh Besar",
    "simeulue": "Simeulue",
    "lampulo": "Banda Aceh",
    "ulee lheue": "Banda Aceh",
    "lhoknga": "Aceh Besar",
}
