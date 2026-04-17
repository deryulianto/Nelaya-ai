from fastapi import APIRouter, HTTPException
from auth_service.app.services.listing_store import list_all_listings
from auth_service.app.services.buyer_interest_store import list_all_buyer_interests

router = APIRouter(prefix="/api/v1/public", tags=["Public Marketplace"])

@router.get("/marketplace/summary")
def public_marketplace_summary():
    try:
        listings = list_all_listings()
        active_listings = [
            r for r in listings if str(r.get("status", "")).lower() == "available"
        ]

        interests = list_all_buyer_interests()

        return {
            "ok": True,
            "active_listings": len(active_listings),
            "buyer_interests": len(interests),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
