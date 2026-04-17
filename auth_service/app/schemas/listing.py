from pydantic import BaseModel, Field
from typing import Optional

class ListingCreateIn(BaseModel):
    price_offer_idr_per_kg: float = Field(..., gt=0)
    available_weight_kg: float = Field(..., gt=0)
    location: str = Field(..., description="mis. TPI Lampulo")
    status: str = Field(default="available", description="available / reserved / sold / closed")
    notes: Optional[str] = None

class ListingOut(BaseModel):
    listing_id: str
    batch_id: str
    trip_id: str
    user_phone: str
    date: str
    landing_port: str
    gear_subtype: str
    species_group: str
    quality_grade: str
    price_offer_idr_per_kg: float
    available_weight_kg: float
    location: str
    status: str
    notes: Optional[str] = None
    created_at: str

class ListingListOut(BaseModel):
    ok: bool = True
    items: list[ListingOut]
