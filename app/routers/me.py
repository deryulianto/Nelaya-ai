# app/routers/me.py
from fastapi import APIRouter, HTTPException, Header
from app.utils.security import verify_jwt
from app.services.user_store import get_user_by_phone, upsert_user
from app.schemas.user import MeOut, MeUpdateIn

router = APIRouter(prefix="/api/v1", tags=["Me"])

def _get_phone_from_auth(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ValueError("missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_jwt(token)
    return str(payload.get("sub"))

@router.get("/me", response_model=MeOut)
def me(authorization: str | None = Header(default=None)):
    try:
        phone = _get_phone_from_auth(authorization)
        user = get_user_by_phone(phone)
        if not user:
            raise ValueError("user not found")
        return MeOut(**user)
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/me", response_model=MeOut)
def update_me(body: MeUpdateIn, authorization: str | None = Header(default=None)):
    try:
        phone = _get_phone_from_auth(authorization)
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        user = upsert_user(phone, updates)
        return MeOut(**user)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
