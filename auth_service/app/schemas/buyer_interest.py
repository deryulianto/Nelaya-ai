from pydantic import BaseModel, Field
from typing import Optional

class BuyerInterestCreateIn(BaseModel):
    buyer_name: str = Field(..., min_length=2, max_length=120)
    buyer_phone: str = Field(..., min_length=8, max_length=30)
    buyer_note: Optional[str] = Field(default=None, max_length=1000)

class BuyerInterestOut(BaseModel):
    interest_id: str
    listing_id: str
    batch_id: str
    trip_id: str
    date: str
    landing_port: str
    species_group: str
    quality_grade: str
    price_offer_idr_per_kg: float
    available_weight_kg: float
    buyer_name: str
    buyer_phone: str
    buyer_note: Optional[str] = None
    created_at: str
