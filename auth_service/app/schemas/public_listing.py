from pydantic import BaseModel
from typing import Optional

class PublicListingOut(BaseModel):
    listing_id: str
    date: str
    landing_port: str
    gear_subtype: str
    species_group: str
    quality_grade: str
    price_offer_idr_per_kg: float
    available_weight_kg: float
    location: str
    status: str
    created_at: str

class PublicListingListOut(BaseModel):
    ok: bool = True
    total: int
    items: list[PublicListingOut]

class PublicListingDetailOut(BaseModel):
    ok: bool = True
    listing: dict
    batch: dict
    trip: dict