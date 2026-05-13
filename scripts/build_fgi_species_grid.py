#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT_DIR = ROOT / "data/fgi_map_grid"
OUT_GEOJSON = ROOT / "data/fgi/species_grid_today.geojson"
OUT_SUMMARY = ROOT / "data/fgi/species_grid_today.json"
FEATURE_STORE = ROOT / "data/fgi/feature_store_today.json"


def now_jakarta() -> str:
    return datetime.now(ZoneInfo("Asia/Jakarta")).isoformat()


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def clamp01(value: Optional[float]) -> Optional[float]:
    x = to_float(value)
    if x is None:
        return None
    return max(0.0, min(1.0, x))


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_latest_grid_file() -> Path:
    env_path = os.getenv("FGI_GRID_GEOJSON")
    if env_path:
      p = Path(env_path)
      if not p.is_absolute():
          p = ROOT / p
      if p.exists():
          return p

    files = sorted(DEFAULT_INPUT_DIR.glob("fgi_grid_*.geojson"))
    if not files:
        raise FileNotFoundError(f"Tidak ada fgi_grid_*.geojson di {DEFAULT_INPUT_DIR}")

    # Ambil file terbaru berdasarkan nama, fallback aman untuk pola YYYY-MM-DD.
    return files[-1]


def score_sst_for_pelagic(sst_c: Optional[float]) -> Optional[float]:
    if sst_c is None:
        return None
    if 27.0 <= sst_c <= 31.5:
        return 1.0
    if 31.5 < sst_c <= 32.5:
        return 0.70
    if 26.0 <= sst_c < 27.0:
        return 0.70
    if 25.0 <= sst_c < 26.0:
        return 0.50
    if 32.5 < sst_c <= 33.5:
        return 0.45
    return 0.30


def score_chl_productivity(chl_mg_m3: Optional[float]) -> Optional[float]:
    if chl_mg_m3 is None:
        return None
    chl = chl_mg_m3

    if chl < 0.05:
        return 0.20
    if chl < 0.08:
        return 0.35
    if chl < 0.25:
        return 0.70
    if chl < 0.70:
        return 0.90
    if chl < 1.50:
        return 0.70
    return 0.50


def score_current_support(current_ms: Optional[float]) -> Optional[float]:
    if current_ms is None:
        return None
    c = current_ms

    if c < 0.10:
        return 0.55
    if c < 0.50:
        return 0.90
    if c < 0.90:
        return 0.60
    return 0.35


def score_salinity_support(sal_psu: Optional[float]) -> Optional[float]:
    if sal_psu is None:
        return None

    # Rule awal tropis laut terbuka. Ini bukan model final spesies.
    if 32.0 <= sal_psu <= 35.0:
        return 1.0
    if 30.0 <= sal_psu < 32.0:
        return 0.70
    if 35.0 < sal_psu <= 36.5:
        return 0.70
    if 28.0 <= sal_psu < 30.0:
        return 0.45
    return 0.30


def weighted_score(items: list[tuple[str, Optional[float], float]]) -> dict[str, Any]:
    total_w = 0.0
    total = 0.0
    components = []

    for name, value, weight in items:
        x = clamp01(value)
        if x is None:
            components.append(
                {
                    "name": name,
                    "value": None,
                    "weight": weight,
                    "used": False,
                }
            )
            continue

        total_w += weight
        total += x * weight
        components.append(
            {
                "name": name,
                "value": round(x, 4),
                "weight": weight,
                "used": True,
                "weighted": round(x * weight, 4),
            }
        )

    if total_w <= 0:
        return {"score": None, "components": components, "effective_weight": 0.0}

    return {
        "score": round(total / total_w, 4),
        "components": components,
        "effective_weight": round(total_w, 4),
    }


def label_score(score: Optional[float]) -> str:
    if score is None:
        return "tidak_tersedia"
    if score >= 0.75:
        return "kuat_mendukung"
    if score >= 0.60:
        return "cukup_mendukung"
    if score >= 0.45:
        return "sedang"
    if score >= 0.30:
        return "lemah"
    return "tidak_mendukung"

def apply_fgi_consistency_penalty(
    species_score: Optional[float],
    fgi_dynamic: Optional[float],
    group: str,
) -> Optional[float]:
    """
    v0.5.1
    Menjaga agar skor species tidak terlalu optimis ketika FGI dinamis rendah.
    Ini penting agar peta species tidak bertentangan dengan peta FGI utama.
    """
    if species_score is None:
        return None

    if fgi_dynamic is None:
        return round(min(species_score, 0.58), 4)

    if fgi_dynamic < 0.30:
        cap = 0.55 if group == "medium_pelagic" else 0.58
        return round(min(species_score, cap), 4)

    if fgi_dynamic < 0.45:
        cap = 0.60 if group == "medium_pelagic" else 0.62
        return round(min(species_score, cap), 4)

    if fgi_dynamic < 0.60:
        cap = 0.70 if group == "medium_pelagic" else 0.72
        return round(min(species_score, cap), 4)

    return round(species_score, 4)


def driver_text(
    fgi_dynamic: Optional[float],
    sst_score: Optional[float],
    chl_score: Optional[float],
    current_score: Optional[float],
    upwelling_score: Optional[float],
) -> list[str]:
    drivers = []

    if fgi_dynamic is not None and fgi_dynamic >= 0.55:
        drivers.append("FGI dinamis mendukung")
    if chl_score is not None and chl_score >= 0.65:
        drivers.append("CHL mendukung produktivitas")
    if sst_score is not None and sst_score >= 0.70:
        drivers.append("SST sesuai untuk pelagis tropis")
    if current_score is not None and current_score >= 0.70:
        drivers.append("Arus berada pada kisaran mendukung")
    if upwelling_score is not None and upwelling_score >= 0.45:
        drivers.append("Upwelling memberi dukungan produktivitas")

    if not drivers:
        drivers.append("Sinyal habitat terbaca, tetapi belum ada driver dominan kuat")

    return drivers


def caution_text(
    fgi_dynamic: Optional[float],
    chl_score: Optional[float],
    current_score: Optional[float],
    upwelling_score: Optional[float],
) -> list[str]:
    cautions = []

    if fgi_dynamic is None:
        cautions.append("FGI grid belum tersedia pada titik ini")
    elif fgi_dynamic < 0.45:
        cautions.append("FGI dinamis masih rendah pada titik ini")

    if chl_score is not None and chl_score < 0.45:
        cautions.append("CHL masih lemah")

    if current_score is not None and current_score < 0.50:
        cautions.append("Arus kurang ideal atau berpotensi membatasi operasi")

    if upwelling_score is None:
        cautions.append("Upwelling belum tersedia sebagai sinyal spasial")
    elif upwelling_score < 0.45:
        cautions.append("Upwelling masih lemah dan bukan driver utama")

    cautions.append("Belum dikalibrasi dengan data tangkapan lapangan per-grid")

    return cautions


def confidence_score(props: dict[str, Any], global_confidence: Optional[float]) -> float:
    fields = [
        "score_current_aware",
        "score",
        "sst_c",
        "chl_mg_m3",
        "sal_psu",
        "current_ms",
    ]

    available = sum(1 for f in fields if to_float(props.get(f)) is not None)
    local = available / len(fields)

    if global_confidence is None:
        return round(local, 4)

    return round((0.75 * local) + (0.25 * clamp01(global_confidence)), 4)


def confidence_label(score: float) -> str:
    if score >= 0.75:
        return "tinggi"
    if score >= 0.50:
        return "sedang"
    return "rendah"


def dominant_group(small: Optional[float], medium: Optional[float]) -> tuple[str, str]:
    if small is None and medium is None:
        return "unknown", "Belum dapat dibaca"

    if small is not None and medium is not None:
        gap = small - medium
        if gap >= 0.04:
            return "small_pelagic", "Pelagis kecil lebih terbaca"
        if gap <= -0.04:
            return "medium_pelagic", "Pelagis sedang lebih terbaca"
        return "balanced_pelagic", "Pelagis kecil dan sedang relatif berimbang"

    if small is not None:
        return "small_pelagic", "Pelagis kecil lebih terbaca"

    return "medium_pelagic", "Pelagis sedang lebih terbaca"



def daily_priority_score(
    final_score: Optional[float],
    raw_score: Optional[float],
    fgi_dynamic: Optional[float],
    confidence: Optional[float],
) -> Optional[float]:
    """
    v0.5.3
    Skor khusus untuk ranking relatif harian.

    final_score tetap konservatif untuk label habitat.
    raw_score membantu membedakan titik yang sama-sama terkena cap.
    fgi_dynamic tetap menjadi pagar utama agar ranking tidak terlalu optimis.
    """
    fs = clamp01(final_score)
    rs = clamp01(raw_score)
    fg = clamp01(fgi_dynamic)
    cf = clamp01(confidence)

    parts = []
    weights = []

    if fs is not None:
        parts.append(fs)
        weights.append(0.40)

    if rs is not None:
        parts.append(rs)
        weights.append(0.25)

    if fg is not None:
        parts.append(fg)
        weights.append(0.25)

    if cf is not None:
        parts.append(cf)
        weights.append(0.10)

    if not parts:
        return None

    total_w = sum(weights)
    score = sum(v * w for v, w in zip(parts, weights)) / total_w
    return round(score, 4)


def relative_label_for_rank(
    rank: int,
    percentile: float,
    habitat_score: Optional[float],
    fgi_dynamic: Optional[float],
) -> str:
    """
    Ranking harian harus tetap dibaca bersama FGI dynamic.
    Jika FGI dynamic rendah, jangan sebut 'prioritas' tanpa catatan.
    """
    hs = clamp01(habitat_score)
    fg = clamp01(fgi_dynamic)

    if hs is None:
        return "tidak_tersedia"

    if hs < 0.45:
        return "rendah"

    if fg is not None and fg < 0.30:
        if rank <= 10:
            return "prioritas_observasi_hati_hati"
        if percentile >= 0.75:
            return "menarik_dipantau_hati_hati"
        return "indikatif_hati_hati"

    if rank <= 10:
        return "prioritas_observasi_harian"
    if percentile >= 0.75:
        return "menarik_dipantau"
    if percentile >= 0.50:
        return "sedang_dipantau"
    return "indikatif_rendah"


def main() -> None:
    input_file = find_latest_grid_file()
    geo = read_json(input_file)

    feature_store = read_json(FEATURE_STORE) if FEATURE_STORE.exists() else {}
    derived = feature_store.get("derived_features", {})
    metrics = feature_store.get("metrics", {})

    global_upwelling = clamp01(derived.get("upwelling_score"))
    global_confidence = clamp01((feature_store.get("confidence") or {}).get("score"))
    global_wave_m = to_float(metrics.get("wave_m"))

    features = geo.get("features") or []
    out_features = []

    for idx, feat in enumerate(features):
        props = dict(feat.get("properties") or {})

        fgi_dynamic = clamp01(
            props.get("score_current_aware")
            if props.get("score_current_aware") is not None
            else props.get("score")
        )
        fgi_baseline = clamp01(props.get("score_baseline"))
        sst_c = to_float(props.get("sst_c"))
        chl = to_float(props.get("chl_mg_m3"))
        current_ms = to_float(props.get("current_ms"))
        sal_psu = to_float(props.get("sal_psu"))

        sst_score = score_sst_for_pelagic(sst_c)
        chl_score = score_chl_productivity(chl)
        current_score = score_current_support(current_ms)
        sal_score = score_salinity_support(sal_psu)

        small_result = weighted_score(
            [
                ("chl_productivity", chl_score, 0.32),
                ("sst_suitability", sst_score, 0.20),
                ("fgi_dynamic", fgi_dynamic, 0.25),
                ("current_support", current_score, 0.12),
                ("salinity_support", sal_score, 0.06),
                ("regional_upwelling", global_upwelling, 0.05),
            ]
        )

        medium_result = weighted_score(
            [
                ("fgi_dynamic", fgi_dynamic, 0.38),
                ("current_support", current_score, 0.22),
                ("sst_suitability", sst_score, 0.15),
                ("chl_productivity", chl_score, 0.12),
                ("salinity_support", sal_score, 0.08),
                ("regional_upwelling", global_upwelling, 0.05),
            ]
        )

        small_score_raw = small_result["score"]
        medium_score_raw = medium_result["score"]

        small_score = apply_fgi_consistency_penalty(
            small_score_raw,
            fgi_dynamic,
            "small_pelagic",
        )

        medium_score = apply_fgi_consistency_penalty(
           medium_score_raw,
           fgi_dynamic,
           "medium_pelagic",
        )

        dom, dom_label = dominant_group(small_score, medium_score)

        conf = confidence_score(props, global_confidence)

        drivers = driver_text(
            fgi_dynamic=fgi_dynamic,
            sst_score=sst_score,
            chl_score=chl_score,
            current_score=current_score,
            upwelling_score=global_upwelling,
        )

        cautions = caution_text(
            fgi_dynamic=fgi_dynamic,
            chl_score=chl_score,
            current_score=current_score,
            upwelling_score=global_upwelling,
        )

        new_props = {
            **props,
            "species_grid_version": "0.5.3",
            "fgi_dynamic": fgi_dynamic,
            "fgi_baseline": fgi_baseline,
            "small_pelagic_score_raw": small_score_raw,
            "small_pelagic_score": small_score,
            "small_pelagic_priority_score": daily_priority_score(
                small_score,
                small_score_raw,
                fgi_dynamic,
                conf,
            ),
            "small_pelagic_label": label_score(small_score),
            "medium_pelagic_score_raw": medium_score_raw,
            "medium_pelagic_score": medium_score,
            "medium_pelagic_priority_score": daily_priority_score(
                medium_score,
                medium_score_raw,
                fgi_dynamic,
                conf,
            ),
            "medium_pelagic_label": label_score(medium_score),
            "dominant_group": dom,
            "dominant_label": dom_label,
            "species_confidence": conf,
            "species_confidence_label": confidence_label(conf),
            "drivers": drivers,
            "cautions": cautions,
            "regional_upwelling_score": global_upwelling,
            "regional_wave_m": global_wave_m,
            "note": "Species Grid v0.5 adalah interpretasi habitat per-grid berbasis fitur yang tersedia, bukan prediksi pasti keberadaan ikan.",
        }

        out_feat = {
            **feat,
            "properties": new_props,
        }

        out_features.append(out_feat)

    # ------------------------------------------------------------------
    # v0.5.2: Relative daily ranking
    # ------------------------------------------------------------------
    # Skor absolut tetap dijaga konservatif oleh habitat consistency penalty.
    # Ranking ini membantu peta menunjukkan zona relatif terbaik pada hari itu,
    # tanpa mengklaim bahwa zona tersebut pasti kuat atau pasti ada ikan.
    def add_relative_ranking(score_key: str, prefix: str) -> None:
        priority_key = f"{prefix}_priority_score"

        ranked = [
            f for f in out_features
            if to_float((f.get("properties") or {}).get(score_key)) is not None
        ]

        ranked.sort(
            key=lambda f: (
                to_float((f.get("properties") or {}).get(priority_key)) or -1,
                to_float((f.get("properties") or {}).get(score_key)) or -1,
                to_float((f.get("properties") or {}).get(f"{prefix}_score_raw")) or -1,
                to_float((f.get("properties") or {}).get("fgi_dynamic")) or -1,
            ),
            reverse=True,
        )

        n = len(ranked)

        for rank, feat in enumerate(ranked, start=1):
            props = feat.get("properties") or {}
            score = to_float(props.get(score_key))
            priority = to_float(props.get(priority_key))
            fgi_dynamic = to_float(props.get("fgi_dynamic"))

            if n <= 1:
                percentile = 1.0
            else:
                percentile = 1.0 - ((rank - 1) / (n - 1))

            props[f"{prefix}_rank_today"] = rank
            props[f"{prefix}_percentile_today"] = round(percentile, 4)
            props[f"{prefix}_priority_score_today"] = priority
            props[f"is_top_{prefix}_today"] = rank <= 10
            props[f"{prefix}_relative_label"] = relative_label_for_rank(
                rank=rank,
                percentile=percentile,
                habitat_score=score,
                fgi_dynamic=fgi_dynamic,
            )

            feat["properties"] = props

    add_relative_ranking("small_pelagic_score", "small_pelagic")
    add_relative_ranking("medium_pelagic_score", "medium_pelagic")

    out_geo = {
        "type": "FeatureCollection",
        "module": "fgi_species_grid",
        "version": "0.5.3",
        "generated_at": now_jakarta(),
        "source_file": str(input_file.relative_to(ROOT)),
        "feature_count": len(out_features),
        "method": "weighted_expert_rules_spatial_v0",
        "limitations": [
            "Belum menggunakan front, bathymetry, dan temporal memory per-cell.",
            "Upwelling masih dipakai sebagai sinyal regional, bukan spasial per-cell.",
            "Belum dikalibrasi dengan data tangkapan lapangan per-grid.",
            "Gunakan sebagai peta peluang habitat, bukan jaminan lokasi ikan.",
        ],
        "features": out_features,
    }

    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)

    with OUT_GEOJSON.open("w", encoding="utf-8") as f:
        json.dump(out_geo, f, ensure_ascii=False, indent=2)

    small_scores = [
        to_float(f["properties"].get("small_pelagic_score"))
        for f in out_features
        if to_float(f["properties"].get("small_pelagic_score")) is not None
    ]
    medium_scores = [
        to_float(f["properties"].get("medium_pelagic_score"))
        for f in out_features
        if to_float(f["properties"].get("medium_pelagic_score")) is not None
    ]

    def stats(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"count": 0, "mean": None, "min": None, "max": None}
        return {
            "count": len(values),
            "mean": round(sum(values) / len(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }

    top_small = sorted(
        out_features,
        key=lambda f: to_float(f["properties"].get("small_pelagic_score")) or -1,
        reverse=True,
    )[:10]

    top_medium = sorted(
        out_features,
        key=lambda f: to_float(f["properties"].get("medium_pelagic_score")) or -1,
        reverse=True,
    )[:10]

    def compact_top(feat: dict[str, Any], key: str) -> dict[str, Any]:
        coords = (feat.get("geometry") or {}).get("coordinates") or [None, None]
        props = feat.get("properties") or {}
        return {
            "lon": coords[0],
            "lat": coords[1],
            "score": props.get(key),
            "dominant_group": props.get("dominant_group"),
            "confidence": props.get("species_confidence"),
            "drivers": props.get("drivers"),
            "cautions": props.get("cautions"),
        }

    summary = {
        "module": "fgi_species_grid_summary",
        "version": "0.5.3",
        "generated_at": out_geo["generated_at"],
        "source_file": out_geo["source_file"],
        "output_geojson": str(OUT_GEOJSON.relative_to(ROOT)),
        "feature_count": len(out_features),
        "stats": {
            "small_pelagic_score": stats(small_scores),
            "medium_pelagic_score": stats(medium_scores),
        },
        "top_cells": {
            "small_pelagic": [compact_top(f, "small_pelagic_score") for f in top_small],
            "medium_pelagic": [compact_top(f, "medium_pelagic_score") for f in top_medium],
        },
        "global_context": {
            "upwelling_score": global_upwelling,
            "feature_store_confidence": global_confidence,
            "wave_m": global_wave_m,
        },
        "limitations": out_geo["limitations"],
    }

    with OUT_SUMMARY.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"OK: wrote {OUT_GEOJSON}")
    print(f"OK: wrote {OUT_SUMMARY}")
    print(f"INFO: source={input_file}")


if __name__ == "__main__":
    main()
