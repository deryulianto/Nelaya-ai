from pathlib import Path
import json

from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix="/api/v1/fgi/feature-store",
    tags=["FGI Feature Store"],
)

ROOT = Path(__file__).resolve().parents[2]
FEATURE_STORE_FILE = ROOT / "data/fgi/feature_store_today.json"


@router.get("/today")
def get_fgi_feature_store_today():
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
