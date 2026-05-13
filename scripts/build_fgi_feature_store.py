#!/usr/bin/env python3
"""
FGI Feature Store v0.1
NELAYA-AI

Tujuan:
- Mengumpulkan sinyal utama FGI harian dalam satu file bersih.
- Menjadi pondasi untuk confidence layer, explainable FGI,
  species-group FGI, validasi lapangan, dan kalibrasi.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]

SOURCE_FILES = {
    "earth_signals": "data/earth/earth_signals_today.json",
    "dynamic_physics": "data/physics/ocean_dynamic_physics_today.json",
    "temporal_memory": "data/physics/fgi_temporal_memory_today.json",
    "bathymetry_summary": "data/physics/bathymetry_features_summary.json",
    "upwelling_candidates": "data/upwelling/upwelling_candidates_today.json",
}


def now_jakarta() -> str:
    return datetime.now(ZoneInfo("Asia/Jakarta")).isoformat()


def read_json(rel_path: str) -> Optional[Dict[str, Any]]:
    path = ROOT / rel_path
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        return {
            "_read_error": True,
            "path": rel_path,
            "error": str(exc),
        }


def file_snapshot(rel_path: str) -> Dict[str, Any]:
    path = ROOT / rel_path
    if not path.exists():
        return {
            "path": rel_path,
            "available": False,
            "modified_at": None,
        }

    stat = path.stat()
    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone(
        ZoneInfo("Asia/Jakarta")
    )

    return {
        "path": rel_path,
        "available": True,
        "modified_at": modified_at.isoformat(),
        "size_bytes": stat.st_size,
    }


def get_path(data: Any, path: str, default: Any = None) -> Any:
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def pick(data: Any, paths: list[str], default: Any = None) -> Any:
    for p in paths:
        value = get_path(data, p, None)
        if value is not None:
            return value
    return default


def to_float(value: Any) -> Optional[float]:
    """
    Parser angka yang lebih tahan terhadap struktur nested.

    Bisa membaca:
    - angka langsung
    - string angka
    - dict seperti {"value": ...}, {"mean": ...}, {"score": ...}
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return None
        return x

    if isinstance(value, str):
        try:
            x = float(value)
            if math.isnan(x) or math.isinf(x):
                return None
            return x
        except Exception:
            return None

    if isinstance(value, dict):
        preferred_keys = [
            "value",
            "score",
            "index",
            "probability",
            "mean",
            "avg",
            "average",
            "median",
            "latest",
            "current",
            "sst_c",
            "chl_mg_m3",
            "ssh_cm",
            "sla_cm",
            "wave_m",
            "wind_ms",
            "current_ms",
            "mean_c",
            "mean_mg_m3",
            "mean_cm",
            "mean_ms",
        ]

        for k in preferred_keys:
            if k in value:
                x = to_float(value.get(k))
                if x is not None:
                    return x

        # fallback hati-hati: cari angka pertama dari dict
        ignored = {
            "lag_days",
            "valid_ratio",
            "size_bytes",
            "year",
            "month",
            "day",
            "hour",
            "minute",
            "second",
        }

        for k, v in value.items():
            if str(k) in ignored:
                continue
            x = to_float(v)
            if x is not None:
                return x

    if isinstance(value, list):
        for item in value:
            x = to_float(item)
            if x is not None:
                return x

    return None


def parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None

    s = str(value).strip()
    try:
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        pass

    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def days_lag(source_date: Any) -> Optional[int]:
    dt = parse_dt(source_date)
    if dt is None:
        return None

    today = datetime.now(timezone.utc).date()
    return max(0, (today - dt.date()).days)


def label_from_score(score: Optional[float]) -> str:
    if score is None:
        return "tidak_tersedia"
    if score >= 0.75:
        return "tinggi"
    if score >= 0.50:
        return "sedang"
    return "rendah"


def condition_available(value: Optional[float]) -> bool:
    return value is not None


def component_quality(
    name: str,
    value: Optional[float],
    weight: float,
    source_date: Any = None,
) -> Dict[str, Any]:
    lag = days_lag(source_date)

    if value is None:
        availability_score = 0.0
        status = "missing"
        note = f"{name} belum tersedia."
    else:
        availability_score = 1.0
        status = "available"
        note = f"{name} tersedia."

    if value is not None and lag is not None:
        if lag <= 1:
            freshness_score = 1.0
            freshness_label = "fresh"
        elif lag <= 3:
            freshness_score = 0.75
            freshness_label = "slightly_lagged"
        elif lag <= 7:
            freshness_score = 0.55
            freshness_label = "lagged"
        else:
            freshness_score = 0.35
            freshness_label = "stale"
    elif value is not None:
        freshness_score = 0.80
        freshness_label = "unknown_date"
    else:
        freshness_score = 0.0
        freshness_label = "not_available"

    score = availability_score * freshness_score

    return {
        "status": status,
        "value": value,
        "weight": weight,
        "source_date": source_date,
        "lag_days": lag,
        "freshness_label": freshness_label,
        "component_score": round(score, 3),
        "weighted_score": round(score * weight, 3),
        "note": note,
    }


def classify_wave(wave_m: Optional[float]) -> str:
    if wave_m is None:
        return "tidak_tersedia"
    if wave_m < 0.75:
        return "relatif_tenang"
    if wave_m < 1.5:
        return "sedang"
    if wave_m < 2.5:
        return "perlu_waspada"
    return "berisiko_tinggi"


def classify_current(current_ms: Optional[float]) -> str:
    if current_ms is None:
        return "tidak_tersedia"
    if current_ms < 0.15:
        return "lemah"
    if current_ms < 0.50:
        return "sedang"
    if current_ms < 0.90:
        return "kuat"
    return "sangat_kuat"


def classify_sst(sst_c: Optional[float]) -> str:
    if sst_c is None:
        return "tidak_tersedia"
    if sst_c < 27.0:
        return "relatif_dingin"
    if sst_c <= 31.5:
        return "tropis_wajar"
    if sst_c <= 32.5:
        return "hangat_tinggi"
    return "sangat_panas"


def classify_chl(chl: Optional[float]) -> str:
    if chl is None:
        return "tidak_tersedia"
    if chl < 0.08:
        return "rendah"
    if chl < 0.25:
        return "sedang"
    if chl < 0.70:
        return "produktif"
    return "sangat_tinggi_perlu_dibaca_hati_hati"


def build_explanation(metrics: Dict[str, Any], derived: Dict[str, Any], confidence: Dict[str, Any]) -> Dict[str, Any]:
    positives = []
    cautions = []

    sst_c = metrics.get("sst_c")
    chl = metrics.get("chl_mg_m3")
    current_ms = metrics.get("current_ms")
    wave_m = metrics.get("wave_m")
    front_score = derived.get("front_score")
    temporal_memory_score = derived.get("temporal_memory_score")
    bathymetry_score = derived.get("bathymetry_score")

    if sst_c is not None:
        if 27.0 <= sst_c <= 31.5:
            positives.append("SST berada dalam rentang tropis yang masih wajar untuk banyak ikan pelagis.")
        elif sst_c > 31.5:
            cautions.append("SST cukup hangat; perlu dibaca bersama CHL, arus, dan kondisi angin/gelombang.")
        else:
            cautions.append("SST relatif dingin; perlu dilihat apakah terkait upwelling atau massa air tertentu.")

    if chl is not None:
        if chl >= 0.25:
            positives.append("CHL menunjukkan sinyal produktivitas yang cukup menarik.")
        elif chl >= 0.08:
            positives.append("CHL tersedia dan berada pada tingkat sedang.")
        else:
            cautions.append("CHL masih rendah sehingga sinyal produktivitas belum kuat.")

    if current_ms is not None:
        if current_ms < 0.5:
            positives.append("Arus tidak terlalu kuat sehingga lebih mendukung operasi kecil-menengah.")
        else:
            cautions.append("Arus cukup kuat; peluang habitat perlu dipisahkan dari risiko operasi.")

    if wave_m is not None:
        if wave_m < 1.5:
            positives.append("Gelombang masih dalam kisaran yang relatif dapat dikelola.")
        else:
            cautions.append("Gelombang perlu dipantau karena dapat menurunkan kelayakan operasi melaut.")

    if front_score is not None:
        if front_score >= 0.55:
            positives.append("Ada indikasi front/dinamika fisik yang dapat menjadi area konsentrasi kehidupan laut.")
        else:
            cautions.append("Sinyal front belum kuat.")

    if temporal_memory_score is not None:
        if temporal_memory_score >= 0.55:
            positives.append("Sinyal temporal mulai menunjukkan persistensi.")
        else:
            cautions.append("Temporal memory belum kuat; sinyal hari ini masih perlu dikonfirmasi beberapa hari.")

    if bathymetry_score is not None and bathymetry_score >= 0.55:
        positives.append("Faktor batimetri memberi dukungan terhadap struktur habitat.")

    if confidence.get("level") == "rendah":
        cautions.append("Confidence masih rendah karena sebagian fitur penting belum tersedia atau belum segar.")

    if not positives:
        positives.append("Feature store berhasil dibangun, tetapi driver positif utama belum cukup kuat atau belum tersedia.")

    headline = "FGI Feature Store v0.1 siap sebagai pondasi pembacaan peluang laut harian."

    if confidence.get("level") == "tinggi":
        headline = "Sinyal FGI hari ini cukup kuat dan data pendukung relatif lengkap."
    elif confidence.get("level") == "sedang":
        headline = "Sinyal FGI hari ini dapat dibaca, tetapi tetap perlu kehati-hatian."
    elif confidence.get("level") == "rendah":
        headline = "Sinyal FGI hari ini masih terbatas dan membutuhkan dukungan data tambahan."

    return {
        "headline": headline,
        "positive_drivers": positives,
        "cautions": cautions,
        "next_actions": [
            "Gunakan feature store ini sebagai input confidence layer.",
            "Bandingkan zona FGI dengan catatan trip lapangan.",
            "Tambahkan species-group FGI setelah struktur fitur stabil.",
        ],
    }


def main() -> None:
    earth = read_json(SOURCE_FILES["earth_signals"]) or {}
    dynamic = read_json(SOURCE_FILES["dynamic_physics"]) or {}
    temporal = read_json(SOURCE_FILES["temporal_memory"]) or {}
    bathy = read_json(SOURCE_FILES["bathymetry_summary"]) or {}
    upwelling = read_json(SOURCE_FILES["upwelling_candidates"]) or {}

    m = earth.get("metrics", earth)

    sst_c = to_float(
        pick(
            earth,
            [
                "metrics.sst_c",
                "metrics.sst",
                "metrics.sst_mean_c",
                "sst_c",
                "sst",
                "sst_mean_c",
            ],
        )
    )

    chl_mg_m3 = to_float(
        pick(
            earth,
            [
                "metrics.chl_mg_m3",
                "metrics.chlorophyll_mg_m3",
                "metrics.chl",
                "chl_mg_m3",
                "chlorophyll_mg_m3",
                "chl",
            ],
        )
    )

    current_ms = to_float(
        pick(
            earth,
            [
                "metrics.current_ms",
                "metrics.current_speed_ms",
                "current_ms",
                "current_speed_ms",
            ],
        )
    )

    current_u_ms = to_float(
        pick(
            earth,
            [
                "metrics.current_u_ms",
                "metrics.uo",
                "current_u_ms",
                "uo",
            ],
        )
    )

    current_v_ms = to_float(
        pick(
            earth,
            [
                "metrics.current_v_ms",
                "metrics.vo",
                "current_v_ms",
                "vo",
            ],
        )
    )

    wave_m = to_float(
        pick(
            earth,
            [
                "metrics.wave_m",
                "metrics.wave_height_m",
                "metrics.hs_m",
                "wave_m",
                "wave_height_m",
                "hs_m",
            ],
        )
    )

    wind_ms = to_float(
        pick(
            earth,
            [
                "metrics.wind_ms",
                "metrics.wind_speed_ms",
                "wind_ms",
                "wind_speed_ms",
            ],
        )
    )

    ssh_cm = to_float(
        pick(
            earth,
            [
                "metrics.ssh_cm",
                "metrics.sla_cm",
                "metrics.ssh",
                "ssh_cm",
                "sla_cm",
                "ssh",
            ],
        )
    )

    fgi = to_float(
        pick(
            earth,
            [
                "metrics.fgi",
                "metrics.fgi_score",
                "fgi",
                "fgi_score",
            ],
        )
    )

    fgi_current_aware = to_float(
        pick(
            earth,
            [
                "metrics.fgi_current_aware.value",
                "metrics.fgi_current_aware",
                "fgi_current_aware.value",
                "fgi_current_aware",
            ],
        )
    )

    front_score = to_float(
        pick(
            dynamic,
            [
                "front_score",
                "stats.front_score.p95",
                "stats.front_score.mean",
                "dynamic_features.front_score",
                "metrics.front_score",
                "summary.front_score",
                "summary.mean_front_score",
                "summary.front_score_mean",
            ],
        )
    )

    dynamic_physics_score_mean = to_float(
        pick(
            dynamic,
            [
                "stats.dynamic_physics_score.mean",
                "summary.dynamic_physics_score_mean",
                "dynamic_physics_score_mean",
            ],
        )
    )

    dynamic_physics_score_p95 = to_float(
        pick(
            dynamic,
            [
                "stats.dynamic_physics_score.p95",
                "summary.dynamic_physics_score_p95",
                "dynamic_physics_score_p95",
            ],
        )
    )

    dynamic_physics_score_max = to_float(
        pick(
            dynamic,
            [
                "stats.dynamic_physics_score.max",
                "summary.dynamic_physics_score_max",
                "dynamic_physics_score_max",
                "top_cells.dynamic_physics_score.0.dynamic_physics_score",
            ],
        )
    )

    dynamic_physics_score = (
        dynamic_physics_score_p95
        or dynamic_physics_score_mean
        or dynamic_physics_score_max
    )

    temporal_memory_score_mean = to_float(
        pick(
            temporal,
            [
                "stats.temporal_memory_score.mean",
                "summary.mean_temporal_memory_score",
                "summary.temporal_memory_score_mean",
                "mean_temporal_memory_score",
            ],
        )
    )

    temporal_memory_score_p95 = to_float(
        pick(
            temporal,
            [
                "stats.temporal_memory_score.p95",
                "summary.temporal_memory_score_p95",
                "temporal_memory_score_p95",
            ],
        )
    )

    temporal_memory_score_max = to_float(
        pick(
            temporal,
            [
                "stats.temporal_memory_score.max",
                "summary.temporal_memory_score_max",
                "temporal_memory_score_max",
                "top_cells.temporal_memory_score.0.temporal_memory_score",
            ],
        )
    )

    temporal_memory_score = (
        temporal_memory_score_p95
        or temporal_memory_score_mean
        or temporal_memory_score_max
    )

    persistence_score = to_float(
        pick(
            temporal,
            [
                "stats.persistence_score.p95",
                "stats.persistence_score.mean",
                "summary.persistence_score",
                "summary.mean_persistence_score",
                "top_cells.temporal_memory_score.0.persistence_score",
                "persistence_score",
            ],
        )
    )

    stability_score = to_float(
        pick(
            temporal,
            [
                "stats.stability_score.p95",
                "stats.stability_score.mean",
                "summary.stability_score",
                "top_cells.temporal_memory_score.0.stability_score",
                "stability_score",
            ],
        )
    )

    temporal_confidence_mean = to_float(
        pick(
            temporal,
            [
                "stats.temporal_confidence.mean",
                "summary.temporal_confidence_mean",
                "temporal_confidence_mean",
            ],
        )
    )

    temporal_confidence_p95 = to_float(
        pick(
            temporal,
            [
                "stats.temporal_confidence.p95",
                "summary.temporal_confidence_p95",
                "temporal_confidence_p95",
            ],
        )
    )

    temporal_confidence_max = to_float(
        pick(
            temporal,
            [
                "stats.temporal_confidence.max",
                "summary.temporal_confidence_max",
                "temporal_confidence_max",
                "top_cells.temporal_memory_score.0.temporal_confidence",
            ],
        )
    )

    temporal_confidence = (
        temporal_confidence_mean
        or temporal_confidence_p95
        or temporal_confidence_max
    )

    bathymetry_score_mean = to_float(
        pick(
            bathy,
            [
                "stats.shelf_break_score.mean",
                "mean_shelf_break_score",
                "summary.mean_shelf_break_score",
                "stats.mean_shelf_break_score",
            ],
        )
    )

    bathymetry_score_p95 = to_float(
        pick(
            bathy,
            [
                "stats.shelf_break_score.p95",
                "summary.shelf_break_score_p95",
                "shelf_break_score_p95",
            ],
        )
    )

    bathymetry_score_max = to_float(
        pick(
            bathy,
            [
                "stats.shelf_break_score.max",
                "summary.shelf_break_score_max",
                "shelf_break_score_max",
                "top_cells.shelf_break_score.0.shelf_break_score",
            ],
        )
    )

    # Untuk Feature Store regional, p95 dibaca sebagai hotspot shelf-break support.
    bathymetry_score = (
        bathymetry_score_p95
        or bathymetry_score_mean
        or bathymetry_score_max
    )

    upwelling_score = to_float(
        pick(
            upwelling,
            [
                "summary.mean_upwelling_score",
                "summary.upwelling_score",
                "upwelling_score",
                "mean_upwelling_score",
            ],
        )
    )

    sst_source_date = pick(
        earth,
        [
            "metrics.sst_source_date",
            "data_quality.sst.source_date",
            "data_quality.sst.date",
            "sst_source_date",
        ],
    )

    chl_source_date = pick(
        earth,
        [
            "metrics.chl_source_date",
            "metrics.chlorophyll_source_date",
            "data_quality.chl.source_date",
            "data_quality.chlorophyll.source_date",
            "chl_source_date",
            "chlorophyll_source_date",
        ],
    )

    current_source_date = pick(
        earth,
        [
            "metrics.current_source_date",
            "data_quality.current.source_date",
            "current_source_date",
        ],
    )

    wave_source_date = pick(
        earth,
        [
            "metrics.wave_source_date",
            "data_quality.wave.source_date",
            "wave_source_date",
        ],
    )

    wind_source_date = pick(
        earth,
        [
            "metrics.wind_source_date",
            "data_quality.wind.source_date",
            "wind_source_date",
        ],
    )

    ssh_source_date = pick(
        earth,
        [
            "metrics.ssh_source_date",
            "metrics.sla_source_date",
            "data_quality.ssh.source_date",
            "ssh_source_date",
            "sla_source_date",
        ],
    )

    metrics = {
        "fgi": fgi,
        "fgi_current_aware": fgi_current_aware,
        "sst_c": sst_c,
        "chl_mg_m3": chl_mg_m3,
        "current_ms": current_ms,
        "current_u_ms": current_u_ms,
        "current_v_ms": current_v_ms,
        "wave_m": wave_m,
        "wind_ms": wind_ms,
        "ssh_cm": ssh_cm,
        "classes": {
            "sst": classify_sst(sst_c),
            "chl": classify_chl(chl_mg_m3),
            "current": classify_current(current_ms),
            "wave": classify_wave(wave_m),
        },
    }

    derived_features = {
        "front_score": front_score,
        "dynamic_physics_score": dynamic_physics_score,
        "dynamic_physics_score_mean": dynamic_physics_score_mean,
        "dynamic_physics_score_p95": dynamic_physics_score_p95,
        "dynamic_physics_score_max": dynamic_physics_score_max,
        "temporal_memory_score": temporal_memory_score,
        "temporal_memory_score_mean": temporal_memory_score_mean,
        "temporal_memory_score_p95": temporal_memory_score_p95,
        "temporal_memory_score_max": temporal_memory_score_max,
        "persistence_score": persistence_score,
        "stability_score": stability_score,
        "temporal_confidence": temporal_confidence,
        "temporal_confidence_mean": temporal_confidence_mean,
        "temporal_confidence_p95": temporal_confidence_p95,
        "temporal_confidence_max": temporal_confidence_max,
        "bathymetry_score": bathymetry_score,
        "bathymetry_score_mean": bathymetry_score_mean,
        "bathymetry_score_p95": bathymetry_score_p95,
        "bathymetry_score_max": bathymetry_score_max,
        "upwelling_score": upwelling_score,
    }

    components = {
        "sst": component_quality("SST", sst_c, 0.15, sst_source_date),
        "chl": component_quality("CHL", chl_mg_m3, 0.20, chl_source_date),
        "current": component_quality("Arus", current_ms, 0.15, current_source_date),
        "wave": component_quality("Gelombang", wave_m, 0.10, wave_source_date),
        "wind": component_quality("Angin", wind_ms, 0.05, wind_source_date),
        "ssh": component_quality("SSH/SLA", ssh_cm, 0.10, ssh_source_date),
        "dynamic_physics": component_quality("Dynamic physics", dynamic_physics_score or front_score, 0.10, None),
        "temporal_memory": component_quality("Temporal memory", temporal_memory_score, 0.10, None),
        "bathymetry": component_quality("Batimetri", bathymetry_score, 0.05, None),
    }

    confidence_score = round(sum(c["weighted_score"] for c in components.values()), 3)
    confidence_level = label_from_score(confidence_score)

    confidence_reasons = []
    confidence_cautions = []

    for key, comp in components.items():
        if comp["status"] == "available":
            confidence_reasons.append(comp["note"])
        else:
            confidence_cautions.append(comp["note"])

        if comp["lag_days"] is not None and comp["lag_days"] > 3:
            confidence_cautions.append(
                f"{key} memiliki lag {comp['lag_days']} hari sehingga perlu dibaca hati-hati."
            )

    confidence = {
        "score": confidence_score,
        "level": confidence_level,
        "components": components,
        "reasons": confidence_reasons,
        "cautions": confidence_cautions,
    }

    output = {
        "module": "fgi_feature_store",
        "version": "0.1.3",
        "region": pick(earth, ["region"], "Aceh"),
        "generated_at": now_jakarta(),
        "source_snapshot": {
            name: file_snapshot(path) for name, path in SOURCE_FILES.items()
        },
        "raw_dates": {
            "earth_date": pick(earth, ["date", "snapshot_date", "latest_available_date"], None),
            "generated_at_earth": pick(earth, ["generated_at"], None),
            "sst_source_date": sst_source_date,
            "chl_source_date": chl_source_date,
            "current_source_date": current_source_date,
            "wave_source_date": wave_source_date,
            "wind_source_date": wind_source_date,
            "ssh_source_date": ssh_source_date,
        },
        "metrics": metrics,
        "derived_features": derived_features,
        "data_quality": {
            "confidence_base": confidence_level,
            "raw_data_quality": pick(earth, ["data_quality", "metrics.data_quality"], {}),
        },
        "confidence": confidence,
        "explanation": build_explanation(metrics, derived_features, confidence),
        "notes": [
            "FGI Feature Store v0.1 adalah agregator fitur, bukan model final.",
            "Nilai confidence membaca ketersediaan dan kesegaran fitur, bukan jaminan keberadaan ikan.",
            "Kalibrasi akurasi membutuhkan data trip lapangan secara berulang.",
        ],
    }

    out_path = ROOT / "data/fgi/feature_store_today.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"OK: wrote {out_path}")


if __name__ == "__main__":
    main()
