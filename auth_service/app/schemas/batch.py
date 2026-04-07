from pydantic import BaseModel, Field
from typing import Optional

class BatchCreateIn(BaseModel):
    species_group: str = Field(..., description="mis. pelagis_campuran / demersal / campuran")
    weight_kg: float = Field(..., gt=0)
    quality_grade: str = Field(..., description="mis. A / B / C")
    notes: Optional[str] = None

class BatchOut(BaseModel):
    batch_id: str
    trip_id: str
    user_phone: str
    date: str
    landing_port: str
    gear_subtype: str
    species_group: str
    weight_kg: float
    quality_grade: str
    notes: Optional[str] = None
    created_at: str

class BatchListOut(BaseModel):
    ok: bool = True
    items: list[BatchOut]
