from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.island_sampling import sample_island_metrics

router = APIRouter(prefix="/ecosystem", tags=["ecosystem"])


ISLAND_CONFIG: Dict[str, Dict[str, Any]] = {
    "sabang": {
        "name": "Sabang",
        "label": "Pulau Weh / Sabang",
        "ecosystem_sensitivity": "karang",
        "zone_type": "pulau kecil dengan terumbu karang",
    },
    "simeulue": {
        "name": "Simeulue",
        "label": "Pulau Simeulue",
        "ecosystem_sensitivity": "karang dan pesisir terbuka",
        "zone_type": "pulau besar-sedang dengan perairan terbuka",
    },
    "banyak": {
        "name": "Kepulauan Banyak",
        "label": "Kepulauan Banyak",
        "ecosystem_sensitivity": "karang, lamun, dan pesisir dangkal",
        "zone_type": "gugus pulau kecil dengan perairan dangkal sensitif",
    },
}


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _bleaching_status_from_sst(sst: Optional[float]) -> Dict[str, Any]:
    """
    MVP:
    status berbasis SST absolut harian.
    Catatan penting:
    - ini adalah thermal stress early warning
    - belum anomaly/climatology/DHW
    """
    if sst is None:
        return {
            "status": "unknown",
            "level": 0,
            "label": "data belum tersedia",
            "reason": "SST tidak tersedia untuk penilaian awal.",
        }

    if sst >= 31.0:
        return {
            "status": "alert",
            "level": 4,
            "label": "peringatan tinggi",
            "reason": "SST sangat tinggi dan berpotensi memberi tekanan panas kuat pada ekosistem karang dangkal.",
        }
    if sst >= 30.5:
        return {
            "status": "warning",
            "level": 3,
            "label": "peringatan",
            "reason": "SST berada pada level sangat hangat sehingga tekanan panas pada karang perlu diwaspadai.",
        }
    if sst >= 29.5:
        return {
            "status": "watch",
            "level": 2,
            "label": "siaga awal",
            "reason": "SST hangat dan layak dipantau sebagai sinyal awal tekanan termal.",
        }
    return {
        "status": "normal",
        "level": 1,
        "label": "normal",
        "reason": "SST belum menunjukkan sinyal tekanan panas yang kuat untuk penilaian awal.",
    }


def _build_actions(status: str, ecosystem_sensitivity: str) -> List[str]:
    actions: List[str] = []

    if status == "alert":
        actions.append("Kurangi aktivitas intensif di zona karang dangkal sampai ada observasi lapangan tambahan.")
        actions.append("Dorong pemantauan visual cepat oleh komunitas lokal, panglima laot, atau mitra konservasi.")
        actions.append("Hindari jangkar, injakan, dan gangguan fisik di area sensitif.")
    elif status == "warning":
        actions.append("Tingkatkan kewaspadaan pada area dengan ekosistem sensitif seperti " + ecosystem_sensitivity + ".")
        actions.append("Pertimbangkan imbauan kehati-hatian untuk aktivitas di perairan dangkal.")
    elif status == "watch":
        actions.append("Lanjutkan pemantauan suhu laut harian dan periksa tren 3–7 hari ke depan.")
        actions.append("Sosialisasikan kehati-hatian ringan pada area dangkal yang sensitif.")
    elif status == "normal":
        actions.append("Pertahankan pemantauan rutin dan dokumentasikan kondisi lapangan bila memungkinkan.")
    else:
        actions.append("Data belum cukup; lakukan pengecekan data dan verifikasi lapangan.")

    return actions


def _salinity_context(salinity: Optional[float]) -> Dict[str, Any]:
    """
    Salinitas = faktor konteks / modifier ringan.
    Tidak mengubah status utama bleaching pada MVP ini,
    tapi membantu menjelaskan apakah stres utama datang dari suhu saja
    atau ada tekanan tambahan dari salinitas.
    """
    if salinity is None:
        return {
            "value": None,
            "status": "unknown",
            "label": "data belum tersedia",
            "note": "Salinitas belum tersedia, sehingga perannya sebagai faktor stres tambahan belum dapat dinilai.",
        }

    # rentang kasar laut tropis normal
    if salinity < 30.0:
        return {
            "value": salinity,
            "status": "low",
            "label": "rendah",
            "note": "Salinitas lebih rendah dari kisaran laut tropis normal dan dapat menambah stres osmotik pada karang.",
        }

    if salinity < 32.0:
        return {
            "value": salinity,
            "status": "slightly_low",
            "label": "sedikit rendah",
            "note": "Salinitas sedikit lebih rendah dari kisaran normal. Ini belum tentu kritis, tetapi patut dipantau sebagai faktor stres tambahan.",
        }

    if salinity <= 35.0:
        return {
            "value": salinity,
            "status": "normal",
            "label": "normal",
            "note": "Salinitas masih berada dalam kisaran normal laut tropis, sehingga tekanan utama lebih mungkin berasal dari suhu laut.",
        }

    if salinity <= 37.0:
        return {
            "value": salinity,
            "status": "slightly_high",
            "label": "sedikit tinggi",
            "note": "Salinitas sedikit lebih tinggi dari kisaran normal dan dapat menambah tekanan fisiologis pada ekosistem sensitif.",
        }

    return {
        "value": salinity,
        "status": "high",
        "label": "tinggi",
        "note": "Salinitas cukup tinggi dan berpotensi menjadi faktor stres tambahan pada karang dan ekosistem dangkal.",
    }



def _build_confidence_note(sst: Optional[float]) -> str:
    if sst is None:
        return "Kepercayaan rendah karena SST tidak tersedia."
    return (
        "Kepercayaan menengah. Penilaian ini berbasis SST harian permukaan laut dan belum memasukkan anomaly historis, "
        "durasi stres panas, maupun validasi lapangan."
    )


def _build_salinity_bleaching_note(
    sst: Optional[float],
    salinity_ctx: Dict[str, Any],
) -> str:
    sal_status = salinity_ctx.get("status")

    if sst is None:
        return "SST belum tersedia, sehingga hubungan antara suhu dan salinitas belum dapat dijelaskan."

    if sal_status == "normal":
        return (
            "Salinitas berada pada kisaran normal, sehingga tekanan utama pada ekosistem dalam pembacaan awal ini "
            "lebih mungkin dipicu oleh suhu laut."
        )

    if sal_status in {"slightly_low", "low"}:
        return (
            "Selain suhu laut, salinitas yang lebih rendah dari normal dapat menambah stres osmotik pada karang, "
            "sehingga kondisi lapangan perlu dipantau lebih cermat."
        )

    if sal_status in {"slightly_high", "high"}:
        return (
            "Selain suhu laut, salinitas yang lebih tinggi dari normal dapat menambah tekanan fisiologis pada ekosistem sensitif."
        )

    return "Peran salinitas sebagai faktor stres tambahan belum dapat dinilai dengan cukup kuat."



def _build_bleaching_item(island_key: str) -> Dict[str, Any]:
    if island_key not in ISLAND_CONFIG:
        raise ValueError(f"island_key tidak dikenal: {island_key}")

    config = ISLAND_CONFIG[island_key]
    sample_payload = sample_island_metrics(island_key)
    metrics = sample_payload.get("metrics", {})

    sst = _safe_float(metrics.get("sst_c"))
    salinity = _safe_float(metrics.get("salinity_psu"))

    # 🔥 CORE
    status_info = _bleaching_status_from_sst(sst)
    salinity_info = _salinity_context(salinity)
    actions = _build_actions(status_info["status"], config["ecosystem_sensitivity"])

    return {
        "key": island_key,
        "name": config["name"],
        "label": config["label"],
        "zone_type": config["zone_type"],
        "ecosystem_sensitivity": config["ecosystem_sensitivity"],

        # 🔥 METRICS
        "sst_c": sst,
        "salinity_psu": salinity,

        # 🔥 CORE ANALYSIS
        "bleaching_risk": status_info,
        "salinity_context": salinity_info,

        "summary": (
            f"Wilayah {config['name']} berada pada status {status_info['label']} untuk tekanan panas ekosistem. "
            f"{status_info['reason']}"
        ),

        # 🔥 PENJELAS ILMIAH TAMBAHAN
        "salinity_bleaching_note": _build_salinity_bleaching_note(sst, salinity_info),

        # 🔥 ACTION
        "recommended_actions": actions,

        # 🔥 CONFIDENCE
        "confidence_note": _build_confidence_note(sst),

        # 🔥 RAW DATA
        "sampling": sample_payload,
    }


def _build_regional_summary(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not items:
        return {
            "highest_risk_island": None,
            "summary": "Belum ada data pulau untuk diringkas.",
        }

    ranked = sorted(
        items,
        key=lambda x: (
            x.get("bleaching_risk", {}).get("level", 0),
            x.get("sst_c") if x.get("sst_c") is not None else -999,
        ),
        reverse=True,
    )

    top = ranked[0]
    return {
        "highest_risk_island": {
            "key": top["key"],
            "name": top["name"],
            "label": top["label"],
            "sst_c": top["sst_c"],
            "bleaching_risk": top["bleaching_risk"],
        },
        "summary": (
            f"Wilayah dengan tekanan panas tertinggi hari ini adalah {top['name']} "
            f"dengan status {top['bleaching_risk']['label']}."
        ),
        "ranking": [
            {
                "key": item["key"],
                "name": item["name"],
                "sst_c": item["sst_c"],
                "bleaching_risk": item["bleaching_risk"],
            }
            for item in ranked
        ],
    }


@router.get("/bleaching")
def get_bleaching_warning(
    island: Optional[str] = Query(
        default=None,
        description="Filter opsional: sabang | simeulue | banyak",
    )
) -> Dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()

    if island:
        island_key = island.strip().lower()
        if island_key not in ISLAND_CONFIG:
            raise HTTPException(
                status_code=400,
                detail="Parameter island tidak valid. Gunakan: sabang | simeulue | banyak",
            )

        item = _build_bleaching_item(island_key)

        return {
            "ok": True,
            "mode": "bleaching-early-warning-mvp",
            "generated_at": generated_at,
            "region": "Aceh, Indonesia",
            "count": 1,
            "item": item,
            "notes": [
                "Status ini adalah early thermal stress watch berbasis SST absolut harian.",
                "Belum menggunakan climatology, anomaly historis, atau Degree Heating Week (DHW).",
                "Perlu verifikasi lapangan untuk keputusan konservasi yang lebih tegas.",
            ],
        }

    items = [_build_bleaching_item(k) for k in ISLAND_CONFIG.keys()]
    regional_summary = _build_regional_summary(items)

    return {
        "ok": True,
        "mode": "bleaching-early-warning-mvp",
        "generated_at": generated_at,
        "region": "Aceh, Indonesia",
        "count": len(items),
        "items": items,
        "regional_summary": regional_summary,
        "notes": [
            "Status ini adalah early thermal stress watch berbasis SST absolut harian.",
            "Belum menggunakan climatology, anomaly historis, atau Degree Heating Week (DHW).",
            "Perlu verifikasi lapangan untuk keputusan konservasi yang lebih tegas.",
        ],
    }


@router.get("/bleaching/health")
def bleaching_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "bleaching-early-warning",
        "status": "healthy",
    }
