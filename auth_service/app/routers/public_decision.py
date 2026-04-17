from fastapi import APIRouter, HTTPException
from auth_service.app.services.decision_engine import build_decision_today

router = APIRouter(prefix="/api/v1/public", tags=["Decision Engine"])

@router.get("/decision/today")
def public_decision_today():
    try:
        return build_decision_today()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
