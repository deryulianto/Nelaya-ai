from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix="/api/v1/fgi/lagrangian-aware",
    tags=["fgi", "lagrangian-front", "shadow-model"],
)


EARTH_PATH = Path("data/earth/earth_signals_today.json")
LFI_PATH = Path("data/physics/lagrangian_front_today.json")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"File not found: {path}",
                "hint": "Run LFI builder and integration script first.",
            },
        )

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Failed to read JSON file: {path}",
                "error": str(exc),
            },
        )


@router.get("/summary")
def get_fgi_lagrangian_aware_summary() -> Dict[str, Any]:
    """
    Lightweight summary for dashboard cards.

    This endpoint returns the experimental FGI Lagrangian-aware shadow metric.
    It does not replace operational FGI.
    """
    earth = read_json(EARTH_PATH)
    metrics = earth.get("metrics", {})

    fgi = metrics.get("fgi")
    fgi_current = metrics.get("fgi_current_aware")
    lfi_alpha = metrics.get("lfi_alpha")
    fgi_lagrangian = metrics.get("fgi_lagrangian_aware")

    if fgi_lagrangian is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "metrics.fgi_lagrangian_aware not found.",
                "hint": "Run scripts/integrate_lfi_to_earth_signals.py first.",
            },
        )

    inputs = fgi_lagrangian.get("inputs", {}) if isinstance(fgi_lagrangian, dict) else {}

    return {
        "version": "0.1-shadow",
        "product": "FGI Lagrangian-aware",
        "date": fgi_lagrangian.get("source_date"),
        "status": "experimental_shadow_model",
        "summary": {
            "fgi_value": fgi.get("value") if isinstance(fgi, dict) else fgi,
            "fgi_current_aware": fgi_current.get("value") if isinstance(fgi_current, dict) else fgi_current,
            "lfi_alpha": lfi_alpha.get("value") if isinstance(lfi_alpha, dict) else lfi_alpha,
            "fgi_lagrangian_aware": fgi_lagrangian.get("value"),
            "band": fgi_lagrangian.get("band"),
            "lfi_hotspot_shadow_value": inputs.get("hotspot_shadow_value"),
            "lfi_weight_alpha": inputs.get("lfi_weight_alpha"),
        },
        "interpretation": {
            "plain_language": (
                "FGI Lagrangian-aware membaca peluang habitat ikan dengan tambahan dukungan "
                "front dinamis permukaan. Nilai ini masih experimental dan belum menggantikan FGI utama."
            ),
            "scientific_caution": fgi_lagrangian.get("scientific_caution"),
        },
        "metrics": {
            "fgi": fgi,
            "fgi_current_aware": fgi_current,
            "lfi_alpha": lfi_alpha,
            "fgi_lagrangian_aware": fgi_lagrangian,
        },
    }


@router.get("/today")
def get_fgi_lagrangian_aware_today() -> Dict[str, Any]:
    """
    Full daily payload combining earth signal metrics and LFI top zones.
    """
    earth = read_json(EARTH_PATH)

    lfi = None
    if LFI_PATH.exists():
        lfi = read_json(LFI_PATH)

    metrics = earth.get("metrics", {})
    fgi_lagrangian = metrics.get("fgi_lagrangian_aware")

    if fgi_lagrangian is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "metrics.fgi_lagrangian_aware not found.",
                "hint": "Run scripts/integrate_lfi_to_earth_signals.py first.",
            },
        )

    return {
        "version": "0.1-shadow",
        "product": "FGI Lagrangian-aware",
        "status": "experimental_shadow_model",
        "earth_date": earth.get("date"),
        "source_date": fgi_lagrangian.get("source_date"),
        "metrics": {
            "fgi": metrics.get("fgi"),
            "fgi_current_aware": metrics.get("fgi_current_aware"),
            "lfi_alpha": metrics.get("lfi_alpha"),
            "fgi_lagrangian_aware": fgi_lagrangian,
        },
        "lagrangian_front": {
            "summary": (lfi or {}).get("summary"),
            "top_zones": (lfi or {}).get("top_zones", [])[:10],
            "method": (lfi or {}).get("method"),
            "scientific_caution": (lfi or {}).get("scientific_caution"),
        },
        "note": (
            "This endpoint is for FGI vNext evaluation. It should be compared with field validation "
            "and should not be presented as deterministic fish-location prediction."
        ),
    }
