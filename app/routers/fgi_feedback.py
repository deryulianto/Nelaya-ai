from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime
import json
from pathlib import Path

router = APIRouter(prefix="/api/v1/fgi", tags=["fgi-feedback"])

DATA_PATH = Path("data/fgi_feedback")
DATA_PATH.mkdir(parents=True, exist_ok=True)

class FGITripFeedback(BaseModel):
    date: str
    port_name: str
    lat: float
    lon: float
    distance_km: float

    trip_success: int  # 1 atau 0
    catch_kg: float | None = None
    fuel_used_l: float | None = None
    notes: str | None = None

@router.post("/feedback")
def save_feedback(payload: FGITripFeedback):
    filename = DATA_PATH / f"{payload.date}.json"

    data = []
    if filename.exists():
        data = json.loads(filename.read_text())

    data.append({
        **payload.dict(),
        "created_at": datetime.utcnow().isoformat()
    })

    filename.write_text(json.dumps(data, indent=2))

    return {"status": "ok", "message": "feedback tersimpan"}
