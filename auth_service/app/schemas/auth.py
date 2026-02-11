from pydantic import BaseModel, Field

class RequestOtpIn(BaseModel):
    phone: str = Field(..., description="0812... / 62812... / +62812...")

class VerifyOtpIn(BaseModel):
    phone: str
    otp: str = Field(..., min_length=6, max_length=6)

class AuthOut(BaseModel):
    ok: bool = True
    message: str | None = None
    token: str | None = None
    is_new_user: bool | None = None
