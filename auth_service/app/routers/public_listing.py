from fastapi import APIRouter, HTTPException, Query
from auth_service.app.services.listing_store import list_all_listings
from auth_service.app.services.trace_store import get_trace_by_listing_id
from auth_service.app.schemas.public_listing import (
    PublicListingOut,
    PublicListingListOut,
    PublicListingDetailOut,
)

router = APIRouter(prefix="/api/v1/public", tags=["Public Listings"])

@router.get("/listings", response_model=PublicListingListOut)
def public_listings(
    landing_port: str | None = Query(default=None),
    species_group: str | None = Query(default=None),
    quality_grade: str | None = Query(default=None),
):
    try:
        rows = list_all_listings()

        rows = [r for r in rows if str(r.get("status", "")).lower() == "available"]

        if landing_port:
            rows = [r for r in rows if r.get("landing_port") == landing_port]

        if species_group:
            rows = [r for r in rows if r.get("species_group") == species_group]

        if quality_grade:
            rows = [r for r in rows if r.get("quality_grade") == quality_grade]

        rows = sorted(rows, key=lambda x: x.get("created_at", ""), reverse=True)

        items = [
            PublicListingOut(
                listing_id=r["listing_id"],
                date=r["date"],
                landing_port=r["landing_port"],
                gear_subtype=r["gear_subtype"],
                species_group=r["species_group"],
                quality_grade=r["quality_grade"],
                price_offer_idr_per_kg=float(r["price_offer_idr_per_kg"]),
                available_weight_kg=float(r["available_weight_kg"]),
                location=r["location"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

        return PublicListingListOut(total=len(items), items=items)

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/listings/{listing_id}", response_model=PublicListingDetailOut)
def public_listing_detail(listing_id: str):
    try:
        data = get_trace_by_listing_id(listing_id)
        if not data:
            raise ValueError("listing not found")

        listing = data.get("listing") or {}
        batch = data.get("batch") or {}
        trip = data.get("trip") or {}

        if str(listing.get("status", "")).lower() != "available":
            raise ValueError("listing not available")

        return PublicListingDetailOut(
            listing={
                "listing_id": listing.get("listing_id"),
                "date": listing.get("date"),
                "landing_port": listing.get("landing_port"),
                "gear_subtype": listing.get("gear_subtype"),
                "species_group": listing.get("species_group"),
                "quality_grade": listing.get("quality_grade"),
                "price_offer_idr_per_kg": listing.get("price_offer_idr_per_kg"),
                "available_weight_kg": listing.get("available_weight_kg"),
                "location": listing.get("location"),
                "status": listing.get("status"),
                "notes": listing.get("notes"),
                "created_at": listing.get("created_at"),
            },
            batch={
                "batch_id": batch.get("batch_id"),
                "species_group": batch.get("species_group"),
                "weight_kg": batch.get("weight_kg"),
                "quality_grade": batch.get("quality_grade"),
                "notes": batch.get("notes"),
                "created_at": batch.get("created_at"),
            },
            trip={
                "trip_id": trip.get("trip_id"),
                "landing_port": trip.get("landing_port"),
                "gear_subtype": trip.get("gear_subtype"),
                "vessel_gt_class": trip.get("vessel_gt_class"),
                "grid_id": trip.get("grid_id"),
                "trip_hours": trip.get("trip_hours"),
                "catch_total_kg": trip.get("catch_total_kg"),
                "created_at": trip.get("created_at"),
            },
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))