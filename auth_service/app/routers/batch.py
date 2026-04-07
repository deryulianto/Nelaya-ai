from fastapi import APIRouter, HTTPException, Header
from auth_service.app.utils.security import verify_jwt
from auth_service.app.services.user_store import get_user_by_phone
from auth_service.app.services.batch_store import find_trip_by_id, create_batch, list_batches_by_trip
from auth_service.app.schemas.batch import BatchCreateIn, BatchOut, BatchListOut

router = APIRouter(prefix="/api/v1/nelayan", tags=["Nelayan Batch"])

def _get_phone_from_auth(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ValueError("missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_jwt(token)
    return str(payload.get("sub"))

@router.post("/trip/{trip_id}/batch", response_model=BatchOut)
def create_batch_route(
    trip_id: str,
    body: BatchCreateIn,
    authorization: str | None = Header(default=None),
):
    try:
        phone = _get_phone_from_auth(authorization)
        user = get_user_by_phone(phone)
        if not user:
            raise ValueError("user not found")

        trip = find_trip_by_id(trip_id)
        if not trip:
            raise ValueError("trip not found")

        if trip.get("user_phone") != phone:
            raise ValueError("trip bukan milik user ini")

        row = create_batch(trip, body.model_dump())
        return BatchOut(**row)

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/trip/{trip_id}/batch", response_model=BatchListOut)
def list_batch_route(
    trip_id: str,
    authorization: str | None = Header(default=None),
):
    try:
        phone = _get_phone_from_auth(authorization)
        user = get_user_by_phone(phone)
        if not user:
            raise ValueError("user not found")

        trip = find_trip_by_id(trip_id)
        if not trip:
            raise ValueError("trip not found")

        if trip.get("user_phone") != phone:
            raise ValueError("trip bukan milik user ini")

        rows = list_batches_by_trip(trip_id)
        return BatchListOut(items=[BatchOut(**r) for r in rows])

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
