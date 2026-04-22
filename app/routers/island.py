from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

import json

from fastapi import APIRouter, HTTPException, Query
from app.services.island_sampling import sample_island_metrics, sample_all_islands

router = APIRouter(prefix="/api/v1/island", tags=["island"])


# ============================================================
# File candidates: mengikuti pola existing NELAYA-AI
# ============================================================
EARTH_SIGNAL_CANDIDATES = [
    Path("data/earth_signals_today.json"),
    Path("data/earth/earth_signals_today.json"),
    Path("data/signals_today.json"),
]


# ============================================================
# Konfigurasi zona awal pulau kecil Aceh
# Catatan:
# - Versi MVP ini memakai "regional interpretation"
# - Belum sampling raster/grid per zona
# - Fokus: cepat hidup dan aman
# ============================================================
ISLAND_CONFIG: Dict[str, Dict[str, Any]] = {
    "sabang": {
        "name": "Sabang",
        "label": "Pulau Weh / Sabang",
        "region_note": "Perairan sekitar Pulau Weh dan Sabang",
        "ecosystem_sensitivity": "karang",
        "fishing_style": "pelagis-kecil dan nelayan pesisir",
    },
    "simeulue": {
        "name": "Simeulue",
        "label": "Pulau Simeulue",
        "region_note": "Perairan sekitar Pulau Simeulue",
        "ecosystem_sensitivity": "karang dan pesisir terbuka",
        "fishing_style": "nelayan pulau dan perairan terbuka",
    },
    "banyak": {
        "name": "Kepulauan Banyak",
        "label": "Kepulauan Banyak",
        "region_note": "Perairan sekitar gugus Kepulauan Banyak",
        "ecosystem_sensitivity": "karang, lamun, dan pesisir dangkal",
        "fishing_style": "nelayan pulau kecil dan pesisir dangkal",
    },
}


# ============================================================
# Utilities
# ============================================================
def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_earth_signal_file() -> Path:
    for path in EARTH_SIGNAL_CANDIDATES:
        if path.exists():
            return path
    raise HTTPException(
        status_code=404,
        detail="earth_signals_today.json tidak ditemukan pada lokasi kandidat.",
    )


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal membaca file JSON: {path} ({exc})",
        ) from exc


def _classify_sst(sst: Optional[float]) -> str:
    if sst is None:
        return "tidak tersedia"
    if sst >= 30.5:
        return "sangat hangat"
    if sst >= 29.0:
        return "hangat"
    if sst >= 27.5:
        return "normal"
    return "sejuk"


def _classify_chl(chl: Optional[float]) -> str:
    if chl is None:
        return "tidak tersedia"
    if chl >= 0.5:
        return "tinggi"
    if chl >= 0.15:
        return "sedang"
    return "rendah"


def _classify_wind(wind: Optional[float]) -> str:
    if wind is None:
        return "tidak tersedia"
    if wind >= 10.0:
        return "sangat kencang"
    if wind >= 6.0:
        return "kencang"
    if wind >= 3.0:
        return "sedang"
    return "lemah"


def _classify_wave(wave: Optional[float]) -> str:
    if wave is None:
        return "tidak tersedia"
    if wave >= 2.5:
        return "sangat tinggi"
    if wave >= 1.5:
        return "tinggi"
    if wave >= 0.5:
        return "sedang"
    return "rendah"


def _extract_metrics(payload: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """
    Toleran terhadap beberapa bentuk payload existing.
    """
    metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics"), dict) else {}

    # Coba dari metrics dulu
    sst = _safe_float(
        metrics.get("sst_c")
        or metrics.get("sst")
        or metrics.get("sea_surface_temperature")
    )
    chl = _safe_float(
        metrics.get("chl_mg_m3")
        or metrics.get("chlorophyll")
        or metrics.get("chl")
    )
    wind = _safe_float(
        metrics.get("wind_ms")
        or metrics.get("wind_speed")
        or metrics.get("wind")
    )
    wave = _safe_float(
        metrics.get("wave_m")
        or metrics.get("wave_height")
        or metrics.get("hs")
    )
    ssh = _safe_float(
        metrics.get("ssh_cm")
        or metrics.get("ssh")
        or metrics.get("sea_surface_height")
    )
    sal = _safe_float(
        metrics.get("salinity_psu")
        or metrics.get("salinity")
        or metrics.get("sss")
    )

    # Fallback: coba root level jika belum ketemu
    if sst is None:
        sst = _safe_float(payload.get("sst_c") or payload.get("sst"))
    if chl is None:
        chl = _safe_float(payload.get("chl_mg_m3") or payload.get("chl"))
    if wind is None:
        wind = _safe_float(payload.get("wind_ms") or payload.get("wind"))
    if wave is None:
        wave = _safe_float(payload.get("wave_m") or payload.get("wave"))
    if ssh is None:
        ssh = _safe_float(payload.get("ssh_cm") or payload.get("ssh"))
    if sal is None:
        sal = _safe_float(payload.get("salinity_psu") or payload.get("salinity"))

    return {
        "sst_c": sst,
        "chl_mg_m3": chl,
        "wind_ms": wind,
        "wave_m": wave,
        "ssh_cm": ssh,
        "salinity_psu": sal,
    }


def _compute_ecosystem_pressure(sst: Optional[float], wave: Optional[float], wind: Optional[float]) -> str:
    """
    Skor sederhana versi MVP:
    - tekanan panas dominan
    - gelombang/angin sebagai stress tambahan
    """
    score = 0

    if sst is not None:
        if sst >= 30.5:
            score += 2
        elif sst >= 29.5:
            score += 1

    if wave is not None:
        if wave >= 2.5:
            score += 2
        elif wave >= 1.5:
            score += 1

    if wind is not None:
        if wind >= 10.0:
            score += 2
        elif wind >= 6.0:
            score += 1

    if score >= 4:
        return "tinggi"
    if score >= 2:
        return "sedang"
    return "rendah"


def _compute_fishing_signal(chl: Optional[float], wave: Optional[float], wind: Optional[float]) -> str:
    """
    Logika ringkas:
    - CHL membantu peluang biologis
    - gelombang/angin mengurangi kenyamanan operasional
    """
    score = 0

    if chl is not None:
        if chl >= 0.5:
            score += 2
        elif chl >= 0.15:
            score += 1

    if wave is not None:
        if wave >= 2.5:
            score -= 2
        elif wave >= 1.5:
            score -= 1

    if wind is not None:
        if wind >= 10:
            score -= 2
        elif wind >= 6:
            score -= 1

    if score >= 2:
        return "cukup baik"
    if score >= 0:
        return "moderat"
    return "terbatas"


def _build_summary(
    island_name: str,
    ecosystem_sensitivity: str,
    fishing_style: str,
    sst: Optional[float],
    chl: Optional[float],
    wind: Optional[float],
    wave: Optional[float],
    pressure: str,
    fishing_signal: str,
) -> str:
    sst_label = _classify_sst(sst)
    chl_label = _classify_chl(chl)
    wind_label = _classify_wind(wind)
    wave_label = _classify_wave(wave)

    parts: List[str] = []

    parts.append(
        f"Kondisi laut di sekitar {island_name} saat ini menunjukkan suhu permukaan laut {sst_label}, "
        f"klorofil-a {chl_label}, angin {wind_label}, dan gelombang {wave_label}."
    )

    if fishing_signal == "cukup baik":
        parts.append(
            f"Secara operasional, sinyal awal untuk aktivitas {fishing_style} tergolong cukup baik, "
            "meski tetap perlu memperhatikan kondisi setempat saat berangkat."
        )
    elif fishing_signal == "moderat":
        parts.append(
            f"Sinyal awal untuk aktivitas {fishing_style} berada pada level moderat; "
            "peluang tetap ada, tetapi efisiensi trip perlu dijaga."
        )
    else:
        parts.append(
            f"Sinyal awal untuk aktivitas {fishing_style} masih terbatas, "
            "terutama bila kondisi lapangan lebih kasar dari rerata data harian."
        )

    if pressure == "tinggi":
        parts.append(
            f"Ekosistem sensitif seperti {ecosystem_sensitivity} perlu diwaspadai karena tekanan oseanografi berada pada level tinggi."
        )
    elif pressure == "sedang":
        parts.append(
            f"Ekosistem sensitif seperti {ecosystem_sensitivity} berada dalam tekanan sedang sehingga aktivitas di perairan dangkal perlu lebih hati-hati."
        )
    else:
        parts.append(
            f"Tekanan terhadap ekosistem sensitif seperti {ecosystem_sensitivity} relatif rendah dalam pembacaan awal hari ini."
        )

    return " ".join(parts)


def _build_actions(
    pressure: str,
    fishing_signal: str,
    wave: Optional[float],
) -> List[str]:
    actions: List[str] = []

    if fishing_signal == "cukup baik":
        actions.append("Prioritaskan area perairan terbuka yang tetap aman dijangkau dari titik berangkat.")
    elif fishing_signal == "moderat":
        actions.append("Jaga efisiensi trip dan hindari pencarian terlalu luas tanpa dasar sinyal tambahan.")
    else:
        actions.append("Pertimbangkan pengurangan radius operasi bila kondisi lapangan tidak mendukung.")

    if pressure in {"sedang", "tinggi"}:
        actions.append("Kurangi tekanan aktivitas di zona dangkal dan area yang sensitif secara ekologi.")
    if pressure == "tinggi":
        actions.append("Pertimbangkan observasi lapangan tambahan atau imbauan kehati-hatian lokal.")
    if wave is not None and wave >= 1.5:
        actions.append("Periksa ulang keselamatan pelayaran karena gelombang berada pada level menengah-ke-atas.")

    if not actions:
        actions.append("Lanjutkan pemantauan rutin dan verifikasi kondisi nyata di lapangan.")

    return actions


def _build_island_payload(
    island_key: str,
    config: Dict[str, Any],
    base_metrics: Dict[str, Optional[float]],
) -> Dict[str, Any]:
    sst = base_metrics.get("sst_c")
    chl = base_metrics.get("chl_mg_m3")
    wind = base_metrics.get("wind_ms")
    wave = base_metrics.get("wave_m")
    ssh = base_metrics.get("ssh_cm")
    sal = base_metrics.get("salinity_psu")

    pressure = _compute_ecosystem_pressure(sst, wave, wind)
    fishing_signal = _compute_fishing_signal(chl, wave, wind)

    summary = _build_summary(
        island_name=config["name"],
        ecosystem_sensitivity=config["ecosystem_sensitivity"],
        fishing_style=config["fishing_style"],
        sst=sst,
        chl=chl,
        wind=wind,
        wave=wave,
        pressure=pressure,
        fishing_signal=fishing_signal,
    )

    actions = _build_actions(
        pressure=pressure,
        fishing_signal=fishing_signal,
        wave=wave,
    )

    return {
        "key": island_key,
        "name": config["name"],
        "label": config["label"],
        "region_note": config["region_note"],
        "ecosystem_sensitivity": config["ecosystem_sensitivity"],
        "fishing_style": config["fishing_style"],
        "metrics": {
            "sst_c": sst,
            "chl_mg_m3": chl,
            "wind_ms": wind,
            "wave_m": wave,
            "ssh_cm": ssh,
            "salinity_psu": sal,
        },
        "classification": {
            "sst": _classify_sst(sst),
            "chl": _classify_chl(chl),
            "wind": _classify_wind(wind),
            "wave": _classify_wave(wave),
            "ecosystem_pressure": pressure,
            "fishing_signal": fishing_signal,
        },
        "summary": summary,
        "recommended_actions": actions,
    }

def _merge_metrics_from_sampling(sample_payload: Dict[str, Any]) -> Dict[str, Optional[float]]:
    metrics = sample_payload.get("metrics", {})
    return {
        "sst_c": _safe_float(metrics.get("sst_c")),
        "chl_mg_m3": _safe_float(metrics.get("chl_mg_m3")),
        "wind_ms": _safe_float(metrics.get("wind_ms")),
        "wave_m": _safe_float(metrics.get("wave_m")),
        "ssh_cm": _safe_float(metrics.get("ssh_cm")),
        "salinity_psu": _safe_float(metrics.get("salinity_psu")),
    }






# ============================================================
# Routes
# ============================================================
@router.get("/intelligence")
def get_island_intelligence(
    island: Optional[str] = Query(
        default=None,
        description="Filter opsional: sabang | simeulue | banyak",
    )
) -> Dict[str, Any]:
    # tetap baca earth file sebagai fallback metadata umum
    source_file = None
    payload: Dict[str, Any] = {}
    generated_at = datetime.now(timezone.utc).isoformat()

    try:
        source_file = _find_earth_signal_file()
        payload = _load_json(source_file)
        generated_at = (
            payload.get("generated_at")
            or payload.get("updated_at")
            or generated_at
        )
    except Exception:
        # tidak apa-apa, kita tetap bisa jalan dari raw NetCDF
        pass

    if island:
        island_key = island.strip().lower()
        if island_key not in ISLAND_CONFIG:
            raise HTTPException(
                status_code=400,
                detail="Parameter island tidak valid. Gunakan: sabang | simeulue | banyak",
            )

        sample_payload = sample_island_metrics(island_key)
        sampled_metrics = _merge_metrics_from_sampling(sample_payload)

        # fallback ke earth_signals jika sebagian metric kosong
        fallback_metrics = _extract_metrics(payload) if payload else {}
        merged_metrics = {
            k: sampled_metrics.get(k) if sampled_metrics.get(k) is not None else fallback_metrics.get(k)
            for k in ["sst_c", "chl_mg_m3", "wind_ms", "wave_m", "ssh_cm", "salinity_psu"]
        }

        item = _build_island_payload(
            island_key=island_key,
            config=ISLAND_CONFIG[island_key],
            base_metrics=merged_metrics,
        )
      
        item["daily_rank_score"] = _compute_best_island_score(item["metrics"])
        item["sampling"] = sample_payload

        return {
            "ok": True,
            "mode": "island-intelligence-bbox",
            "source": str(source_file) if source_file else None,
            "generated_at": generated_at,
            "region": "Aceh, Indonesia",
            "count": 1,
            "item": item,
            "notes": [
                "Metric diupayakan berasal dari sampling bbox per pulau dari raw NetCDF.",
                "Jika sebagian metric belum tersedia, sistem fallback ke earth_signals_today.json.",
            ],
        }

    sampled_all = sample_all_islands()
    fallback_metrics = _extract_metrics(payload) if payload else {}

    items = []
    for key, config in ISLAND_CONFIG.items():
        sample_payload = sampled_all[key]
        sampled_metrics = _merge_metrics_from_sampling(sample_payload)

        merged_metrics = {
            k: sampled_metrics.get(k) if sampled_metrics.get(k) is not None else fallback_metrics.get(k)
            for k in ["sst_c", "chl_mg_m3", "wind_ms", "wave_m", "ssh_cm", "salinity_psu"]
        }

        item = _build_island_payload(
            island_key=key,
            config=config,
            base_metrics=merged_metrics,
        )
        item["sampling"] = sample_payload
        items.append(item)
        best_island_today = _build_best_island_today(items)

    return {
         "ok": True,
         "mode": "island-intelligence-bbox",
         "source": str(source_file) if source_file else None,
         "generated_at": generated_at,
         "region": "Aceh, Indonesia",
         "count": len(items),
         "items": items,
         "best_island_today": best_island_today,
         "notes": [
             "Metric diupayakan berasal dari sampling bbox per pulau dari raw NetCDF.",
             "Jika sebagian metric belum tersedia, sistem fallback ke earth_signals_today.json.",
             "BBox masih versi awal dan dapat disempurnakan lagi sesuai kebutuhan ilmiah dan operasional.",
    ],
}

def _compute_best_island_score(metrics: Dict[str, Optional[float]]) -> Dict[str, Any]:
    """
    Skor sederhana versi operasional harian.
    Lebih tinggi = lebih baik untuk peluang trip harian.
    """
    sst = metrics.get("sst_c")
    chl = metrics.get("chl_mg_m3")
    wind = metrics.get("wind_ms")
    wave = metrics.get("wave_m")

    score = 0.0
    reasons: List[str] = []

    # CHL = driver utama peluang biologis
    if chl is not None:
        if chl >= 1.0:
            score += 4.0
            reasons.append("klorofil-a sangat tinggi")
        elif chl >= 0.5:
            score += 3.0
            reasons.append("klorofil-a tinggi")
        elif chl >= 0.15:
            score += 1.5
            reasons.append("klorofil-a sedang")
        else:
            score += 0.5
            reasons.append("klorofil-a rendah")

    # Wave = penalti operasional
    if wave is not None:
        if wave >= 2.5:
            score -= 3.0
            reasons.append("gelombang sangat tinggi")
        elif wave >= 1.5:
            score -= 1.5
            reasons.append("gelombang tinggi")
        elif wave >= 0.5:
            score -= 0.5
            reasons.append("gelombang sedang")
        else:
            score += 0.5
            reasons.append("gelombang rendah")

    # Wind = penalti operasional
    if wind is not None:
        if wind >= 10.0:
            score -= 3.0
            reasons.append("angin sangat kencang")
        elif wind >= 6.0:
            score -= 1.5
            reasons.append("angin kencang")
        elif wind >= 3.0:
            score -= 0.5
            reasons.append("angin sedang")
        else:
            score += 0.5
            reasons.append("angin lemah")

    # SST = bonus kecil / penalti kecil
    if sst is not None:
        if 28.0 <= sst <= 30.5:
            score += 1.0
            reasons.append("suhu masih mendukung")
        elif sst > 30.5:
            score -= 0.5
            reasons.append("suhu sangat hangat")
        else:
            score += 0.2
            reasons.append("suhu relatif sejuk")

    label = "moderat"
    if score >= 4:
        label = "sangat menarik"
    elif score >= 2:
        label = "menarik"
    elif score < 0:
        label = "terbatas"

    return {
        "score": round(score, 2),
        "label": label,
        "reasons": reasons,
    }


def _build_best_island_today(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not items:
        return None

    ranked: List[Dict[str, Any]] = []

    for item in items:
        metrics = item.get("metrics", {})
        score_info = _compute_best_island_score(metrics)

        ranked.append({
            "key": item.get("key"),
            "name": item.get("name"),
            "label": item.get("label"),
            "score": score_info["score"],
            "score_label": score_info["label"],
            "reasons": score_info["reasons"],
            "classification": item.get("classification", {}),
            "metrics": metrics,
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)

    best = ranked[0]
    return {
        "best": best,
        "ranking": ranked,
        "summary": (
            f"Pulau terbaik hari ini: {best['name']} "
            f"dengan skor {best['score']} ({best['score_label']})."
        ),
    }

@router.get("/health")
def island_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "island-intelligence",
        "status": "healthy",
    }
