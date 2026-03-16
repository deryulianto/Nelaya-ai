from fastapi import APIRouter
from pathlib import Path
import json

router = APIRouter(prefix="/api/v1/rumpon", tags=["rumpon"])

ROOT = Path(__file__).resolve().parents[2]


@router.get("/geojson")
def rumpon_geojson():
    candidates = [
        ROOT / "data" / "rumpon" / "rumpon_wpp571.geojson",
        ROOT / "data" / "rumpon" / "rumpon_571_572.geojson",
    ]

    path = next((p for p in candidates if p.exists()), None)

    if path is None:
        return {"type": "FeatureCollection", "features": []}

    fc = json.loads(path.read_text(encoding="utf-8"))
    return fc


@router.get("/meta")
def rumpon_meta():
    candidates = [
        ROOT / "data" / "rumpon" / "rumpon_wpp571.geojson",
        ROOT / "data" / "rumpon" / "rumpon_571_572.geojson",
    ]

    path = next((p for p in candidates if p.exists()), None)

    if path is None:
        return {"ok": False, "count": 0, "source": None}

    fc = json.loads(path.read_text(encoding="utf-8"))
    return {
        "ok": True,
        "count": len(fc.get("features", [])),
        "source": path.name,
    }