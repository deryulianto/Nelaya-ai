from fastapi import APIRouter, HTTPException, Header, Query
from auth_service.app.utils.security import verify_jwt
from auth_service.app.services.user_store import get_user_by_phone
from auth_service.app.services.trip_store import create_trip, list_trips_by_user
from auth_service.app.schemas.trip import TripCreateIn, TripOut, TripListOut

router = APIRouter(prefix="/api/v1/nelayan", tags=["Nelayan Trip"])

def _get_phone_from_auth(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ValueError("missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_jwt(token)
    return str(payload.get("sub"))

@router.post("/trip", response_model=TripOut)
def create_trip_route(body: TripCreateIn, authorization: str | None = Header(default=None)):
    try:
        phone = _get_phone_from_auth(authorization)
        user = get_user_by_phone(phone)
        if not user:
            raise ValueError("user not found")

        if not user.get("landing_port") or not user.get("gear_subtype"):
            raise ValueError("profil belum lengkap: isi pelabuhan pendaratan dan alat tangkap utama")

        row = create_trip(body.model_dump(), user)
        return TripOut(**row)

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/trip", response_model=TripListOut)
def list_my_trips(
    date: str = Query(..., description="YYYY-MM-DD"),
    authorization: str | None = Header(default=None)
):
    try:
        phone = _get_phone_from_auth(authorization)
        user = get_user_by_phone(phone)
        if not user:
            raise ValueError("user not found")

        rows = list_trips_by_user(phone, date)
        return TripListOut(items=[TripOut(**r) for r in rows])

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
