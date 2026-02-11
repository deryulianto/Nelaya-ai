from pydantic import BaseModel, Field

class MeOut(BaseModel):
    phone_e164: str
    name: str | None = None
    landing_port: str | None = None
    gear_subtype: str | None = None
    vessel_gt_class: str | None = "GT_5_10"
    trip_hours_default: float | None = None

class MeUpdateIn(BaseModel):
    name: str | None = None
    landing_port: str | None = None
    gear_subtype: str | None = None
    trip_hours_default: float | None = Field(default=None, ge=1, le=24)
    vessel_gt_class: str | None = None
