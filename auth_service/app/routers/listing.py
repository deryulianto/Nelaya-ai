from fastapi import APIRouter, HTTPException, Header
from auth_service.app.utils.security import verify_jwt
from auth_service.app.services.user_store import get_user_by_phone
from auth_service.app.services.listing_store import find_batch_by_id, create_listing, list_listings_by_batch
from auth_service.app.schemas.listing import ListingCreateIn, ListingOut, ListingListOut

router = APIRouter(prefix="/api/v1/nelayan", tags=["Nelayan Listing"])

def _get_phone_from_auth(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ValueError("missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_jwt(token)
    return str(payload.get("sub"))

@router.post("/batch/{batch_id}/listing", response_model=ListingOut)
def create_listing_route(
    batch_id: str,
    body: ListingCreateIn,
    authorization: str | None = Header(default=None),
):
    try:
        phone = _get_phone_from_auth(authorization)
        user = get_user_by_phone(phone)
        if not user:
            raise ValueError("user not found")

        batch = find_batch_by_id(batch_id)
        if not batch:
            raise ValueError("batch not found")

        if batch.get("user_phone") != phone:
            raise ValueError("batch bukan milik user ini")

        if float(body.available_weight_kg) > float(batch.get("weight_kg") or 0):
            raise ValueError("available_weight_kg melebihi berat batch")

        row = create_listing(batch, body.model_dump())
        return ListingOut(**row)

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/batch/{batch_id}/listing", response_model=ListingListOut)
def list_listing_route(
    batch_id: str,
    authorization: str | None = Header(default=None),
):
    try:
        phone = _get_phone_from_auth(authorization)
        user = get_user_by_phone(phone)
        if not user:
            raise ValueError("user not found")

        batch = find_batch_by_id(batch_id)
        if not batch:
            raise ValueError("batch not found")

        if batch.get("user_phone") != phone:
            raise ValueError("batch bukan milik user ini")

        rows = list_listings_by_batch(batch_id)
        return ListingListOut(items=[ListingOut(**r) for r in rows])

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
