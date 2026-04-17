from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


SpeciesType = Literal["large_pelagic", "medium_pelagic", "small_pelagic"]


class BehaviorHotspotPoint(BaseModel):
    lat: float
    lon: float
    score: float


class BehaviorHotspotsResponse(BaseModel):
    date: str
    species: SpeciesType
    threshold: float
    count: int
    points: list[BehaviorHotspotPoint]
    component_means: dict
    explanation: str
    meta: dict
