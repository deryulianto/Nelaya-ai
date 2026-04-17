import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/public", tags=["Marketplace Insight Archive"])

BASE_DIR = Path("/home/coastalai/NELAYA-AI-LAB/data/marketplace_insights")

def read_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    return json.loads(path.read_text(encoding="utf-8"))

@router.get("/marketplace/insight/latest")
def marketplace_insight_latest():
    try:
        return read_json(BASE_DIR / "latest.json")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/marketplace/insight/{date_str}")
def marketplace_insight_by_date(date_str: str):
    try:
        return read_json(BASE_DIR / f"{date_str}.json")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
