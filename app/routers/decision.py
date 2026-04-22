from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.island_sampling import sample_all_islands, sample_island_metrics
from app.services.decision_engine import compute_decision, estimate_fgi_like_score

router = APIRouter(prefix="/decision", tags=["decision"])


ISLAND_CONFIG: Dict[str, Dict[str, Any]] = {
    "sabang": {
        "name": "Sabang",
        "label": "Pulau Weh / Sabang",
    },
    "simeulue": {
        "name": "Simeulue",
        "label": "Pulau Simeulue",
    },
    "banyak": {
        "name": "Kepulauan Banyak",
        "label": "Kepulauan Banyak",
    },
}


def _bleaching_status_from_sst(sst: Optional[float]) -> str:
    if sst is None:
        return "unknown"
    if sst >= 31.0:
        return "alert"
    if sst >= 30.5:
        return "warning"
    if sst >= 29.5:
        return "watch"
    return "normal"


def _ecosystem_pressure_from_metrics(
    sst: Optional[float],
    wave: Optional[float],
    wind: Optional[float],
) -> str:
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
        if wind >= 10:
            score += 2
        elif wind >= 6:
            score += 1

    if score >= 4:
        return "tinggi"
    if score >= 2:
        return "sedang"
    return "rendah"


def _build_decision_item(island_key: str, sample_payload: Dict[str, Any]) -> Dict[str, Any]:
    cfg = ISLAND_CONFIG[island_key]
    metrics = sample_payload.get("metrics", {})

    sst = metrics.get("sst_c")
    chl = metrics.get("chl_mg_m3")
    wind = metrics.get("wind_ms")
    wave = metrics.get("wave_m")
    salinity = metrics.get("salinity_psu")

    bleaching_status = _bleaching_status_from_sst(sst)
    ecosystem_pressure = _ecosystem_pressure_from_metrics(sst, wave, wind)
    fgi_like_score = estimate_fgi_like_score(chl, wave, wind, sst)

    decision = compute_decision(
        island_name=cfg["name"],
        fgi_score=fgi_like_score,
        wave_m=wave,
        wind_ms=wind,
        bleaching_status=bleaching_status,
        ecosystem_pressure=ecosystem_pressure,
    )

    return {
        "key": island_key,
        "name": cfg["name"],
        "label": cfg["label"],
        "decision": decision,
        "drivers": {
            "fgi_like_score": fgi_like_score,
            "bleaching_status": bleaching_status,
            "ecosystem_pressure": ecosystem_pressure,
        },
        "metrics": {
            "sst_c": sst,
            "chl_mg_m3": chl,
            "wind_ms": wind,
            "wave_m": wave,
            "salinity_psu": salinity,
        },
        "sampling": sample_payload,
    }


def _rank_decision(items: list[Dict[str, Any]]) -> Dict[str, Any]:
    priority_map = {"GO": 3, "CAUTION": 2, "NO_GO": 1}

    ranked = sorted(
        items,
        key=lambda x: (
            priority_map.get(x["decision"]["decision"], 0),
            x["drivers"]["fgi_like_score"],
        ),
        reverse=True,
    )

    best = ranked[0] if ranked else None
    return {
        "best": best,
        "ranking": ranked,
        "summary": (
            f"Keputusan awal terbaik hari ini mengarah ke {best['name']} "
            f"dengan status {best['decision']['label']}."
            if best
            else "Belum ada keputusan yang dapat diringkas."
        ),
    }


@router.get("")
def get_decision(island: Optional[str] = Query(default=None, description="sabang | simeulue | banyak")):
    generated_at = datetime.now(timezone.utc).isoformat()

    if island:
        island_key = island.strip().lower()
        if island_key not in ISLAND_CONFIG:
            raise HTTPException(
                status_code=400,
                detail="Parameter island tidak valid. Gunakan: sabang | simeulue | banyak",
            )

        sample_payload = sample_island_metrics(island_key)
        item = _build_decision_item(island_key, sample_payload)

        return {
            "ok": True,
            "mode": "decision-engine-v1",
            "generated_at": generated_at,
            "count": 1,
            "item": item,
            "notes": [
                "FGI masih memakai skor pendekatan sementara berbasis dinamika laut.",
                "Versi berikutnya dapat disambungkan ke FGI real.",
            ],
        }

    sampled = sample_all_islands()
    items = [_build_decision_item(k, sampled[k]) for k in ISLAND_CONFIG.keys()]
    ranking = _rank_decision(items)

    return {
        "ok": True,
        "mode": "decision-engine-v1",
        "generated_at": generated_at,
        "count": len(items),
        "items": items,
        "decision_today": ranking,
        "notes": [
            "FGI masih memakai skor pendekatan sementara berbasis dinamika laut.",
            "Versi berikutnya dapat disambungkan ke FGI real.",
        ],
    }


@router.get("/health")
def decision_health():
    return {
        "ok": True,
        "service": "decision-engine",
        "status": "healthy",
    }
