from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.osi import OsiFeatures, compute_osi

router = APIRouter(prefix="/api/v1/osi", tags=["osi-v1"])


def _freshness_status(date_utc: str | None) -> str:
    if not date_utc:
        return "unknown"
    try:
        ref = datetime.now(timezone.utc).date()
        target = datetime.strptime(str(date_utc)[:10], "%Y-%m-%d").date()
        delta = (ref - target).days
        if delta <= 0:
            return "fresh"
        if delta <= 2:
            return "recent"
        return "stale"
    except Exception:
        return "unknown"


def _build_meta(payload: OsiFeatures, result: Any) -> dict[str, Any]:
    date_utc = str(getattr(payload, "date", None) or "")[:10] or None
    summary = None
    if isinstance(result, dict):
        maybe = result.get("score") or result.get("osi") or result.get("value")
        if maybe is not None:
            summary = f"OSI compute menghasilkan skor indikatif {maybe}."
    return {
        "trust": {
            "source": "OSI compute core",
            "date_utc": date_utc,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "freshness_status": _freshness_status(date_utc),
            "confidence": "high",
            "basis_type": "derived_ocean_state_index",
            "mode": "compute-core",
            "caveat": "OSI compute core menghitung indeks dari payload fitur yang diberikan; kualitas hasil bergantung pada kualitas fitur input.",
        },
        "explain": {
            "input_summary": {
                "region": getattr(payload, "region", None),
                "date": getattr(payload, "date", None),
                "sst_c": getattr(payload, "sst_c", None),
                "chl_mg_m3": getattr(payload, "chl_mg_m3", None),
                "wind_ms": getattr(payload, "wind_ms", None),
                "wave_hs_m": getattr(payload, "wave_hs_m", None),
                "ssh_anom_cm": getattr(payload, "ssh_anom_cm", None),
            },
            "score_summary": summary or "OSI compute core menjalankan formula inti berdasarkan fitur yang dikirim.",
            "model_note": "Endpoint ini adalah compute core; gunakan /api/v1/osi/today atau /api/v1/osi/map untuk konteks harian dan spasial.",
        },
    }


@router.get("/health")
def osi_health():
    return {
        "ok": True,
        "service": "osi-v1",
        "trust": {
            "source": "OSI compute core",
            "date_utc": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "freshness_status": "unknown",
            "confidence": "high",
            "basis_type": "service_health",
            "mode": "health",
            "caveat": "Health check hanya memeriksa ketersediaan service, bukan validitas input atau kualitas hasil indeks.",
        },
    }


@router.post("/compute")
def compute_osi_endpoint(payload: OsiFeatures, with_meta: bool = False):
    try:
        result = compute_osi(payload)
        if not with_meta:
            return result
        meta = _build_meta(payload, result)
        return {"osi": result, **meta}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OSI compute failed: {e}") from e
