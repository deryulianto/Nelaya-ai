#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(".")
OUT_DIR = ROOT / "data" / "decision"
OUT_FILE = OUT_DIR / "integrated_ocean_decision_today.json"

INPUTS = {
    "earth_signals": ROOT / "data" / "earth" / "earth_signals_today.json",
    "current_analysis": ROOT / "data" / "physics" / "current_analysis_today.json",
    "tuna_depth": ROOT / "data" / "physics" / "tuna_depth_current_today.json",
    "ns_diagnostics": ROOT / "data" / "physics" / "ns_ocean_diagnostics_today.json",
    "fgi_temporal_memory": ROOT / "data" / "physics" / "fgi_temporal_memory_today.json",
}


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def safe_float(x: Any, default=None):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def clamp01(x: float | None) -> float | None:
    if x is None:
        return None
    return max(0.0, min(1.0, x))


def current_operational_score(current_ms: float | None) -> float | None:
    """
    Simple current suitability score:
    - too weak: low transport
    - moderate: supportive
    - too strong: operational risk
    """
    if current_ms is None:
        return None

    # optimum broad band for biological transport & manageable operation
    lo, hi = 0.05, 0.35
    shoulder = 0.20

    if lo <= current_ms <= hi:
        return 1.0

    if current_ms < lo:
        return clamp01(current_ms / lo)

    # ramp down above hi
    return clamp01(1.0 - ((current_ms - hi) / shoulder))


def score_label(score: float | None) -> dict[str, str | None]:
    if score is None:
        return {
            "level": "unknown",
            "label": "Belum tersedia",
        }

    if score >= 0.75:
        return {
            "level": "supportive",
            "label": "Mendukung",
        }
    if score >= 0.50:
        return {
            "level": "moderate",
            "label": "Cukup mendukung",
        }
    if score >= 0.30:
        return {
            "level": "watch",
            "label": "Perlu dicermati",
        }

    return {
        "level": "low",
        "label": "Dukungan rendah",
    }


def confidence_from_inputs(inputs: dict[str, Any]) -> float:
    weights = {
        "earth_signals": 0.20,
        "current_analysis": 0.20,
        "tuna_depth": 0.20,
        "ns_diagnostics": 0.25,
        "fgi_temporal_memory": 0.15,
    }

    score = 0.0
    for key, w in weights.items():
        if inputs.get(key) is not None:
            score += w

    return round(score, 3)


def extract_earth(inputs: dict[str, Any]) -> dict[str, Any]:
    earth = inputs.get("earth_signals") or {}
    metrics = earth.get("metrics") or {}

    return {
        "snapshot_date": (
            earth.get("snapshot_date")
            or earth.get("latest_available_date")
            or earth.get("date")
        ),
        "sst_c": metrics.get("sst_c"),
        "chl_mg_m3": metrics.get("chl_mg_m3"),
        "wind_ms": metrics.get("wind_ms"),
        "wave_m": metrics.get("wave_m"),
        "current_ms": metrics.get("current_ms"),
        "current_direction_label": metrics.get("current_direction_label"),
        "current_source_date": metrics.get("current_source_date"),
    }


def extract_current(inputs: dict[str, Any]) -> dict[str, Any]:
    cur = inputs.get("current_analysis") or {}

    speed_stats = cur.get("speed_stats") or {}
    hotspot = cur.get("hotspot") or {}

    current_ms = safe_float(speed_stats.get("mean"))
    current_score = current_operational_score(current_ms)

    return {
        "available": bool(cur),
        "snapshot_date": cur.get("snapshot_date"),
        "mean_speed_ms": current_ms,
        "max_speed_ms": speed_stats.get("max"),
        "p75_speed_ms": speed_stats.get("p75"),
        "dominant_direction_label": cur.get("dominant_direction_label"),
        "hotspot": hotspot,
        "operational_score": current_score,
        "status": score_label(current_score),
    }


def extract_tuna_depth(inputs: dict[str, Any]) -> dict[str, Any]:
    tuna = inputs.get("tuna_depth") or {}
    comp = tuna.get("composite") or {}

    rank_stats = comp.get("candidate_rank_score_stats") or comp.get("score_stats") or {}
    hotspot = comp.get("hotspot") or {}
    species = tuna.get("species") or {}

    mean_score = safe_float(rank_stats.get("mean"))
    max_score = safe_float(rank_stats.get("max"))

    return {
        "available": bool(tuna),
        "version": tuna.get("version"),
        "snapshot_date": tuna.get("snapshot_date"),
        "mean_rank_score": mean_score,
        "max_rank_score": max_score,
        "hotspot": hotspot,
        "status": score_label(mean_score),
        "species_coverage": {
            "cakalang_surface": (species.get("cakalang_surface") or {}).get(
                "coverage_optimal_fraction"
            ),
            "yellowfin": (species.get("yellowfin") or {}).get(
                "coverage_optimal_fraction"
            ),
            "bigeye_initial": (species.get("bigeye_initial") or {}).get(
                "coverage_optimal_fraction"
            ),
        },
    }


def extract_ns(inputs: dict[str, Any]) -> dict[str, Any]:
    ns = inputs.get("ns_diagnostics") or {}
    agg = ns.get("aggregate") or {}
    stats = agg.get("score_stats") or {}

    mean_score = safe_float(stats.get("mean"))
    max_score = safe_float(stats.get("max"))
    hotspot = agg.get("hotspot") or {}

    return {
        "available": bool(ns),
        "version": ns.get("version"),
        "snapshot_date": ns.get("snapshot_date"),
        "diagnostic_terms": ns.get("diagnostic_terms") or [],
        "mean_dynamics_score": mean_score,
        "max_dynamics_score": max_score,
        "hotspot": hotspot,
        "status": score_label(mean_score),
        "scientific_position": ns.get("scientific_position"),
    }


def extract_memory(inputs: dict[str, Any]) -> dict[str, Any]:
    mem = inputs.get("fgi_temporal_memory") or {}
    sm = mem.get("summary_metrics") or {}

    mean_memory = safe_float(sm.get("mean_temporal_memory_confidence_adjusted"))
    max_memory = safe_float(sm.get("max_temporal_memory_confidence_adjusted"))

    return {
        "available": bool(mem),
        "mean_temporal_memory_confidence_adjusted": mean_memory,
        "max_temporal_memory_confidence_adjusted": max_memory,
        "history_maturity_factor": sm.get("history_maturity_factor"),
        "movement_consistency": mem.get("movement_consistency"),
        "status": score_label(mean_memory),
    }


def integrated_score(
    current_score: float | None,
    tuna_score: float | None,
    ns_score: float | None,
    memory_score: float | None,
) -> float | None:
    parts = []

    if current_score is not None:
        parts.append((0.25, current_score))
    if tuna_score is not None:
        parts.append((0.35, tuna_score))
    if ns_score is not None:
        # NS score is often numerically lower and more selective,
        # so use a calibrated lift but keep it bounded.
        parts.append((0.25, clamp01(ns_score / 0.70)))
    if memory_score is not None:
        parts.append((0.15, memory_score))

    if not parts:
        return None

    wsum = sum(w for w, _ in parts)
    val = sum(w * s for w, s in parts) / wsum
    return round(clamp01(val), 3)


def decision_level(score: float | None) -> dict[str, str]:
    if score is None:
        return {
            "level": "unknown",
            "label": "Belum cukup data",
            "tone": "neutral",
        }

    if score >= 0.75:
        return {
            "level": "strong_watch",
            "label": "Sinyal kuat, layak dicermati",
            "tone": "supportive",
        }

    if score >= 0.55:
        return {
            "level": "moderate_watch",
            "label": "Sinyal sedang, perlu dibaca bersama data lain",
            "tone": "careful",
        }

    if score >= 0.35:
        return {
            "level": "limited_watch",
            "label": "Sinyal terbatas",
            "tone": "cautious",
        }

    return {
        "level": "low_signal",
        "label": "Sinyal rendah",
        "tone": "low",
    }


def build_audience_cards(
    score: float | None,
    current: dict[str, Any],
    tuna: dict[str, Any],
    ns: dict[str, Any],
    confidence: float,
) -> list[dict[str, Any]]:
    level = decision_level(score)

    hotspot_tuna = tuna.get("hotspot") or {}
    hotspot_ns = ns.get("hotspot") or {}

    cards = [
        {
            "audience": "nelayan",
            "title": "Baca sebagai peluang, bukan kepastian",
            "message": (
                "Sinyal laut hari ini perlu dibaca bersama pengalaman nelayan, "
                "cuaca aktual, BBM, jarak tempuh, dan keselamatan melaut."
            ),
            "decision_hint": level["label"],
            "candidate_area": {
                "tuna_depth_hotspot": hotspot_tuna,
                "dynamics_hotspot": hotspot_ns,
            },
        },
        {
            "audience": "pengelola",
            "title": "Pantau zona dinamika aktif",
            "message": (
                "Zona dengan dinamika tinggi dapat menjadi area prioritas "
                "pemantauan, edukasi keselamatan, dan validasi lapangan."
            ),
            "decision_hint": (
                "Gunakan bersama data pelabuhan, trip logger, regulasi ruang laut, "
                "dan informasi cuaca resmi."
            ),
        },
        {
            "audience": "riset",
            "title": "Kandidat untuk validasi model",
            "message": (
                "Layer v0.9 menggabungkan arus, tuna-depth, diagnostik dinamika, "
                "dan temporal memory sebagai kandidat pengujian hipotesis."
            ),
            "decision_hint": (
                "Prioritaskan validasi di area hotspot yang konsisten lintas layer."
            ),
        },
        {
            "audience": "publik",
            "title": "Laut berubah, data membantu membaca tanda",
            "message": (
                "NELAYA-AI membantu membaca dinamika laut Aceh secara probabilistik, "
                "bukan memastikan hasil tangkapan atau kondisi laut."
            ),
            "decision_hint": "Gunakan sebagai literasi laut harian.",
        },
    ]

    for card in cards:
        card["confidence"] = confidence

    return cards


def narrative(
    score: float | None,
    level: dict[str, str],
    current: dict[str, Any],
    tuna: dict[str, Any],
    ns: dict[str, Any],
    confidence: float,
) -> dict[str, Any]:
    return {
        "short": (
            f"Integrated Ocean Decision v0.9-alpha membaca sinyal gabungan dengan skor {score:.3f}. "
            f"Status: {level['label']}."
            if score is not None
            else "Integrated Ocean Decision v0.9-alpha belum memiliki data lengkap."
        ),
        "interpretation": [
            (
                f"Arus harian memiliki skor operasional {current.get('operational_score'):.3f}."
                if current.get("operational_score") is not None
                else "Skor arus harian belum tersedia."
            ),
            (
                f"Tuna Depth Layer menunjukkan skor ranking rata-rata {tuna.get('mean_rank_score'):.3f}."
                if tuna.get("mean_rank_score") is not None
                else "Tuna Depth Layer belum tersedia."
            ),
            (
                f"Diagnostik dinamika laut v0.8 menunjukkan skor rata-rata {ns.get('mean_dynamics_score'):.3f} dan maksimum {ns.get('max_dynamics_score'):.3f}."
                if ns.get("mean_dynamics_score") is not None
                else "Diagnostik dinamika laut belum tersedia."
            ),
            f"Confidence data gabungan saat ini {confidence:.3f}.",
        ],
        "ethical_note": "Laut tidak memberi janji; NELAYA-AI membaca probabilitas.",
        "scientific_caution": (
            "Sinyal ini bukan prediksi pasti lokasi ikan, bukan jaminan hasil tangkapan, "
            "dan bukan pengganti informasi keselamatan laut resmi."
        ),
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    inputs = {k: read_json(p) for k, p in INPUTS.items()}

    earth = extract_earth(inputs)
    current = extract_current(inputs)
    tuna = extract_tuna_depth(inputs)
    ns = extract_ns(inputs)
    memory = extract_memory(inputs)

    confidence = confidence_from_inputs(inputs)

    score = integrated_score(
        current.get("operational_score"),
        tuna.get("mean_rank_score"),
        ns.get("mean_dynamics_score"),
        memory.get("mean_temporal_memory_confidence_adjusted"),
    )

    level = decision_level(score)

    payload = {
        "module": "nelaya_ai_integrated_ocean_decision",
        "version": "0.9-alpha",
        "status": "ready" if score is not None else "partial",
        "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "snapshot_date": (
            earth.get("snapshot_date")
            or tuna.get("snapshot_date")
            or ns.get("snapshot_date")
            or current.get("snapshot_date")
        ),
        "scientific_position": (
            "Integrated probabilistic ocean decision layer; not a deterministic prediction "
            "and not a fish-location claim."
        ),
        "inputs": {
            k: {
                "path": str(path),
                "available": inputs.get(k) is not None,
            }
            for k, path in INPUTS.items()
        },
        "confidence": confidence,
        "earth": earth,
        "current_analysis": current,
        "tuna_depth": tuna,
        "ns_diagnostics": ns,
        "temporal_memory": memory,
        "integrated_decision": {
            "score": score,
            "level": level,
            "weights": {
                "current_analysis": 0.25,
                "tuna_depth": 0.35,
                "ns_diagnostics": 0.25,
                "temporal_memory": 0.15,
            },
        },
        "audience_cards": build_audience_cards(score, current, tuna, ns, confidence),
    }

    payload["narrative"] = narrative(score, level, current, tuna, ns, confidence)

    OUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 78)
    print("NELAYA-AI v0.9-alpha Integrated Ocean Decision Intelligence")
    print("=" * 78)
    print(f"OUTPUT: {OUT_FILE}")
    print(
        json.dumps(
            {
                "version": payload["version"],
                "snapshot_date": payload["snapshot_date"],
                "confidence": payload["confidence"],
                "integrated_decision": payload["integrated_decision"],
                "narrative": payload["narrative"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print("=" * 78)


if __name__ == "__main__":
    main()
