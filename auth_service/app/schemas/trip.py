from pydantic import BaseModel, Field
from typing import Optional

class TripCreateIn(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD, tanggal pendaratan")
    grid_id: str = Field(..., description="Grid lokasi tangkap")
    departure_time: Optional[str] = Field(default=None, description="ISO datetime atau HH:MM")
    landing_time: Optional[str] = Field(default=None, description="ISO datetime atau HH:MM")
    trip_hours: Optional[float] = Field(default=None, ge=0, le=72)
    catch_total_kg: float = Field(..., ge=0)
    notes: Optional[str] = None

class TripOut(BaseModel):
    trip_id: str
    user_phone: str
    date: str
    landing_port: str
    gear_subtype: str
    vessel_gt_class: str
    grid_id: str
    departure_time: Optional[str] = None
    landing_time: Optional[str] = None
    trip_hours: Optional[float] = None
    catch_total_kg: float
    notes: Optional[str] = None
    created_at: str

class TripListOut(BaseModel):
    ok: bool = True
    items: list[TripOut]
