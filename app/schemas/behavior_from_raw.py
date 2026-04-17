from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


SpeciesType = Literal["large_pelagic", "medium_pelagic", "small_pelagic"]


class BehaviorFromRawResponse(BaseModel):
    date: str
    species: SpeciesType
    component_means: dict
    explanation: str
    lat: list[float]
    lon: list[float]
    behavior_score_grid: list[list[float | None]]
    hotspot_mask: list[list[bool]]
    meta: dict


class BehaviorFromRawSummaryResponse(BaseModel):
    date: str
    species: SpeciesType
    component_means: dict
    explanation: str
    hotspot_fraction: float
    meta: dict