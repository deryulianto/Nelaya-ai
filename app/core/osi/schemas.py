from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


ZoneClass = Literal["coastal", "shelf", "offshore"]
OsiStatus = Literal["ok", "partial", "insufficient_data"]


class OsiFeatures(BaseModel):
    region: str = Field(..., description="Region or location label")
    date: str = Field(..., description="Date in YYYY-MM-DD format")

    sst_c: float
    chl_mg_m3: float
    wind_ms: float
    wave_hs_m: float

    thermocline_depth_m: float | None = None
    mld_m: float | None = None

    freshness_hours: float
    completeness_ratio: float = Field(..., ge=0.0, le=1.0)

    sst_anom_c: float | None = None
    sst_gradient: float | None = None
    chl_anom: float | None = None
    chl_persistence_3d: float | None = Field(default=None, ge=0.0, le=1.0)
    chl_gradient: float | None = None
    current_ms: float | None = None
    ssh_cm: float | None = None
    ssh_anom_cm: float | None = None
    delta_t_0_200: float | None = None
    stratification_index: float | None = None
    spatial_distance_km: float | None = None
    time_alignment_score: float | None = Field(default=None, ge=0.0, le=1.0)
    zone_class: ZoneClass = "shelf"

    @model_validator(mode="after")
    def validate_vertical_inputs(self) -> "OsiFeatures":
        if self.thermocline_depth_m is None and self.mld_m is None:
            raise ValueError("At least one of thermocline_depth_m or mld_m must be provided")
        return self


class OsiNarrative(BaseModel):
    summary: str
    positives: list[str]
    cautions: list[str]


class OsiComponents(BaseModel):
    thermal: float
    productivity: float
    dynamic: float
    vertical: float
    data_confidence: float


class OsiResponse(BaseModel):
    region: str
    date: str
    osi: float | None = None
    label: str | None = None
    confidence: float | None = None
    components: OsiComponents | None = None
    inputs: dict
    narrative: OsiNarrative | None = None
    version: str = "osi-v1.0"
    status: OsiStatus
    missing: list[str] = Field(default_factory=list)
