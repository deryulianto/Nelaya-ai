from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

try:
    # Pydantic v2
    from pydantic import ConfigDict
except Exception:  # pragma: no cover
    ConfigDict = None


class _Base(BaseModel):
    # Allow extra keys so kita gak “ngetat” dulu (biar server jalan stabil)
    if ConfigDict is not None:
        model_config = ConfigDict(extra="allow", populate_by_name=True)
    else:
        class Config:
            extra = "allow"
            allow_population_by_field_name = True


class PortOrigin(_Base):
    id: Optional[str] = None
    name: Optional[str] = None
    region: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class SpotSummary(_Base):
    id: Optional[str] = None
    name: Optional[str] = None
    region: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

    fgi: Optional[float] = None
    band: Optional[str] = None

    distance_km: Optional[float] = None
    cost_rp: Optional[float] = None
    score: Optional[float] = None


class OriginRankItem(_Base):
    origin: Optional[PortOrigin] = None
    chosen_best: Optional[SpotSummary] = None
    chosen_cheapest: Optional[SpotSummary] = None
    chosen_best_fgi: Optional[SpotSummary] = None
    total_score: Optional[float] = None
    reasons: Optional[List[str]] = None


class OptimizeOriginRequest(_Base):
    # fleksibel dulu: kalau payload kamu punya fields lain, tetap diterima
    persona: Optional[str] = None
    mode: Optional[str] = None
    lock_origin: Optional[bool] = None

    # constraints opsional
    min_fgi: Optional[float] = None
    max_distance_km: Optional[float] = None
    max_cost_rp: Optional[float] = None

    # pilihan origin/ports (kalau kamu kirim dari client)
    origins: Optional[List[PortOrigin]] = None

    # weights / parameter lain
    weights: Optional[Dict[str, float]] = None
    meta: Optional[Dict[str, Any]] = None


class OptimizeOriginResponse(_Base):
    ok: bool = True
    message: Optional[str] = None
    date: Optional[str] = None
    generated_at: Optional[str] = None
    mode: Optional[str] = None

    constraints: Optional[Dict[str, Any]] = None

    chosen_origin: Optional[PortOrigin] = None
    chosen_best: Optional[SpotSummary] = None
    chosen_cheapest: Optional[SpotSummary] = None
    chosen_best_fgi: Optional[SpotSummary] = None

    ranks: Optional[List[OriginRankItem]] = None

    error: Optional[Any] = None
    detail: Optional[Any] = None
