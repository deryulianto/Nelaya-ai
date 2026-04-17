from fastapi import APIRouter, HTTPException
from auth_service.app.services.trace_store import get_trace_by_listing_id

router = APIRouter(prefix="/api/v1/trace", tags=["Traceability"])

@router.get("/listing/{listing_id}")
def trace_listing(listing_id: str):
    try:
        data = get_trace_by_listing_id(listing_id)
        if not data:
            raise ValueError("listing not found")

        listing = data.get("listing") or {}
        batch = data.get("batch") or {}
        trip = data.get("trip") or {}

        return {
            "ok": True,
            "trace": {
                "listing": {
                    "listing_id": listing.get("listing_id"),
                    "location": listing.get("location"),
                    "status": listing.get("status"),
                    "price_offer_idr_per_kg": listing.get("price_offer_idr_per_kg"),
                    "available_weight_kg": listing.get("available_weight_kg"),
                    "created_at": listing.get("created_at"),
                },
                "batch": {
                    "batch_id": batch.get("batch_id"),
                    "species_group": batch.get("species_group"),
                    "weight_kg": batch.get("weight_kg"),
                    "quality_grade": batch.get("quality_grade"),
                    "notes": batch.get("notes"),
                    "created_at": batch.get("created_at"),
                },
                "trip": {
                    "trip_id": trip.get("trip_id"),
                    "landing_port": trip.get("landing_port"),
                    "gear_subtype": trip.get("gear_subtype"),
                    "vessel_gt_class": trip.get("vessel_gt_class"),
                    "grid_id": trip.get("grid_id"),
                    "trip_hours": trip.get("trip_hours"),
                    "catch_total_kg": trip.get("catch_total_kg"),
                    "departure_time": trip.get("departure_time"),
                    "landing_time": trip.get("landing_time"),
                    "notes": trip.get("notes"),
                    "created_at": trip.get("created_at"),
                }
            }
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
