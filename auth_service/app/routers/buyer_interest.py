from fastapi import APIRouter, HTTPException
from auth_service.app.schemas.buyer_interest import BuyerInterestCreateIn, BuyerInterestOut
from auth_service.app.services.buyer_interest_store import create_buyer_interest

router = APIRouter(prefix="/api/v1/public", tags=["Buyer Interest"])

@router.post("/listings/{listing_id}/interest", response_model=BuyerInterestOut)
def create_buyer_interest_route(listing_id: str, body: BuyerInterestCreateIn):
    try:
        row = create_buyer_interest(listing_id, body.model_dump())
        return BuyerInterestOut(**row)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
