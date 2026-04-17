from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


SpeciesType = Literal["large_pelagic", "medium_pelagic", "small_pelagic"]


class BehaviorFGIRequest(BaseModel):
    species: SpeciesType = "medium_pelagic"
    sst: List[List[float]]
    chl: List[List[float]]
    wind: List[List[float]]
    wave: List[List[float]]
    salinity: List[List[float]]
    ssh_cm: List[List[float]]
    dx: float = Field(default=1.0, gt=0.0)
    dy: float = Field(default=1.0, gt=0.0)
    hotspot_threshold: float = Field(default=0.65, ge=0.0, le=1.0)


class BehaviorFGIResponse(BaseModel):
    species: SpeciesType
    component_means: dict
    explanation: str
    hotspot_threshold: float
    hotspot_fraction: float
    behavior_score_grid: List[List[float]]
    hotspot_mask: List[List[bool]]
