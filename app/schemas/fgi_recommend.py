# app/schemas/fgi_recommend.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


class OriginIn(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    lat: float
    lon: float


class BoatIn(BaseModel):
    speed_kmh: float = Field(..., gt=0)
    burn_lph: float = Field(..., ge=0)
    fuel_price: float = Field(..., ge=0)


class ConstraintsIn(BaseModel):
    max_radius_km: float = Field(120, gt=0)
    fgi_min: float = Field(0.1, ge=0)
    top_n: int = Field(5, ge=1, le=50)
    min_separation_km: float = Field(0, ge=0)
    budget_rp: Optional[float] = Field(None, ge=0)


Mode = Literal["optimal", "budget"]


class OptimizeOriginRequest(BaseModel):
    # FE kamu kirim "date"
    date: Optional[str] = None

    # kompatibilitas kalau nanti ada client lama kirim "date_utc"
    date_utc: Optional[str] = None

    mode: Mode = "optimal"
    lock_origin: bool = True

    origin: OriginIn
    boat: BoatIn
    constraints: ConstraintsIn


class SpotOut(BaseModel):
    id: Optional[str] = None
    lat: float
    lon: float
    fgi: float
    band: Optional[str] = None
    date: Optional[str] = None

    distance_km: Optional[float] = None
    eta_min_oneway: Optional[float] = None
    fuel_l_roundtrip: Optional[float] = None
    fuel_cost_rp: Optional[float] = None

    # extra metrics (kalau ada di geojson)
    sst_c: Optional[float] = None
    sal_psu: Optional[float] = None
    chl_mg_m3: Optional[float] = None


class OptimizeOriginResponse(BaseModel):
    ok: bool = False
    message: Optional[str] = None
    date: Optional[str] = None
    generated_at: Optional[str] = None
    mode: Optional[str] = None
    constraints: Optional[Dict[str, Any]] = None

    chosen_origin: Optional[Dict[str, Any]] = None
    chosen_best: Optional[SpotOut] = None
    chosen_cheapest: Optional[SpotOut] = None
    chosen_best_fgi: Optional[SpotOut] = None

    ranks: Optional[List[SpotOut]] = None
    error: Optional[Any] = None
    detail: Optional[Any] = None