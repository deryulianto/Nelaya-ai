from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OsiWeights:
    thermal: float = 0.23
    productivity: float = 0.20
    dynamic: float = 0.19
    vertical: float = 0.23
    confidence: float = 0.15


OSI_WEIGHTS = OsiWeights()

OSI_LABELS = [
    (0.0, 20.0, "Very Weak"),
    (20.0, 40.0, "Weak"),
    (40.0, 58.0, "Moderate"),
    (58.0, 76.0, "Strong"),
    (76.0, 100.0, "Very Strong"),
]

ZONE_CLASSES = {"coastal", "shelf", "offshore"}

DEFAULT_SCORES = {
    "sst_anom": 64.0,
    "sst_grad": 55.0,
    "thermal_balance": 60.0,
    "chl_anom": 62.0,
    "chl_persistence": 52.0,
    "chl_grad": 48.0,
    "current": 52.0,
    "ssh": 58.0,
    "mld": 60.0,
    "strat": 56.0,
    "profile_shape": 52.0,
    "spatial": 78.0,
    "time_align": 72.0,
}

DOMAIN_CEILINGS = {
    "thermal": 86.0,
    "productivity": 72.0,
    "dynamic": 78.0,
    "vertical": 84.0,
    "data_confidence": 92.0,
}

NARRATIVE_POSITIVE_MAP = {
    "thermal": "Struktur termal laut berada pada kisaran yang cukup seimbang.",
    "productivity": "Produktivitas biologis permukaan menunjukkan sinyal yang relatif baik.",
    "dynamic": "Gelombang, angin, dan dinamika permukaan berada pada kisaran yang cukup seimbang.",
    "vertical": "Struktur kolom air tropis masih terbaca cukup sehat.",
    "data_confidence": "Kualitas dan keterbaruan data cukup baik untuk dibaca.",
}

NARRATIVE_CAUTION_MAP = {
    "thermal": "Suhu permukaan atau struktur termal belum berada pada kondisi paling ideal.",
    "productivity": "Produktivitas biologis permukaan belum menguat.",
    "dynamic": "Dinamika permukaan laut belum cukup kuat atau kurang seimbang.",
    "vertical": "Struktur kolom air menunjukkan keterbatasan untuk dinamika vertikal.",
    "data_confidence": "Kualitas atau sinkronisasi data masih perlu diperhatikan.",
}