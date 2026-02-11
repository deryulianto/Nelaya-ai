from fastapi import APIRouter, HTTPException
from auth_service.app.schemas.auth import RequestOtpIn, VerifyOtpIn, AuthOut
from auth_service.app.utils.phone import normalize_phone_e164
from auth_service.app.services.otp_service import request_otp, verify_otp
from auth_service.app.services.user_store import get_user_by_phone, upsert_user
from auth_service.app.utils.security import sign_jwt

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

@router.post("/request-otp", response_model=AuthOut)
def request_otp_route(body: RequestOtpIn):
    try:
        phone = normalize_phone_e164(body.phone)
        request_otp(phone)
        return AuthOut(ok=True, message="OTP dikirim lewat WhatsApp")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/verify-otp", response_model=AuthOut)
def verify_otp_route(body: VerifyOtpIn):
    try:
        phone = normalize_phone_e164(body.phone)
        verify_otp(phone, body.otp)

        user = get_user_by_phone(phone)
        is_new = user is None
        if is_new:
            upsert_user(phone, {"vessel_gt_class": "GT_5_10"})

        token = sign_jwt({"sub": phone})
        return AuthOut(ok=True, token=token, is_new_user=is_new)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
