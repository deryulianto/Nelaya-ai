from fastapi import APIRouter, HTTPException

from app.schemas.fgi_plan import FGIPlanRequest, FGIPlanResponse
from app.services.fgi_engine import FGIPlanEngine

router = APIRouter(
    prefix="/api/v1/fgi/recommendations",
    tags=["FGI Plan"],
)


@router.post("/plan", response_model=FGIPlanResponse)
def plan_recommendation(req: FGIPlanRequest):
    try:
        engine = FGIPlanEngine()
        return engine.generate_plan(req)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal membangun rencana FGI: {e}")