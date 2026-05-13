from pathlib import Path
import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix="/api/v1/fgi/species",
    tags=["FGI Species"],
)

ROOT = Path(__file__).resolve().parents[2]
FEATURE_STORE_FILE = ROOT / "data/fgi/feature_store_today.json"


def read_feature_store() -> Dict[str, Any]:
    if not FEATURE_STORE_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "message": "FGI Feature Store belum tersedia.",
                "hint": "Jalankan: python scripts/build_fgi_feature_store.py",
                "path": str(FEATURE_STORE_FILE),
            },
        )

    try:
        with FEATURE_STORE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Gagal membaca FGI Feature Store.",
                "error": str(exc),
            },
        )


@router.get("/today")
def get_fgi_species_today():
    data = read_feature_store()

    species_groups = data.get("species_groups")
    species_summary = data.get("species_summary")

    if not species_groups or not species_summary:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Species group belum tersedia di FGI Feature Store.",
                "hint": "Pastikan script build_fgi_feature_store.py sudah versi 0.4 dan jalankan ulang builder.",
            },
        )

    return {
        "module": "fgi_species",
        "version": "0.4.1",
        "source_module": data.get("module"),
        "source_version": data.get("version"),
        "region": data.get("region"),
        "generated_at": data.get("generated_at"),
        "confidence": data.get("confidence", {}),
        "metrics": {
            "fgi": data.get("metrics", {}).get("fgi"),
            "fgi_current_aware": data.get("metrics", {}).get("fgi_current_aware"),
            "sst_c": data.get("metrics", {}).get("sst_c"),
            "chl_mg_m3": data.get("metrics", {}).get("chl_mg_m3"),
            "current_ms": data.get("metrics", {}).get("current_ms"),
            "wave_m": data.get("metrics", {}).get("wave_m"),
        },
        "drivers": {
            "front_score": data.get("derived_features", {}).get("front_score"),
            "dynamic_physics_score": data.get("derived_features", {}).get("dynamic_physics_score"),
            "temporal_memory_score": data.get("derived_features", {}).get("temporal_memory_score"),
            "bathymetry_score": data.get("derived_features", {}).get("bathymetry_score"),
            "upwelling_score": data.get("derived_features", {}).get("upwelling_score"),
        },
        "species_groups": species_groups,
        "species_summary": species_summary,
    }


@router.get("/cards/today")
def get_fgi_species_cards_today():
    data = read_feature_store()

    species_summary = data.get("species_summary") or {}
    cards = species_summary.get("cards")

    if not cards:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Species cards belum tersedia.",
                "hint": "Pastikan Feature Store sudah dibangun dengan Explainable Species Card v0.4.",
            },
        )

    return {
        "module": "fgi_species_cards",
        "version": "0.4.1",
        "region": data.get("region"),
        "generated_at": data.get("generated_at"),
        "confidence": data.get("confidence", {}),
        "headline": species_summary.get("headline"),
        "main_message": species_summary.get("main_message"),
        "scientific_note": species_summary.get("scientific_note"),
        "operational_note": species_summary.get("operational_note"),
        "cards": cards,
        "limitations": species_summary.get("limitations", []),
    }
