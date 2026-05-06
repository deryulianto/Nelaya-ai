from typing import List, Optional, Literal
from pydantic import BaseModel, Field

PriorityType = Literal["seimbang", "aman", "hemat", "peluang"]
VesselType = Literal["perahu_kecil", "perahu_sedang"]
RegulationStatus = Literal["aman", "terbatas", "terlarang"]
DecisionLabel = Literal["layak", "hati_hati", "tidak_dianjurkan"]


class BoatProfile(BaseModel):
    speed_kmh: float = Field(..., gt=0)
    burn_lph: float = Field(..., gt=0)
    fuel_price: float = Field(..., gt=0)


class Constraints(BaseModel):
    max_radius_km: float = Field(60.0, gt=0)
    fgi_min: float = Field(0.4, ge=0, le=1)
    trip_n: int = Field(5, ge=1, le=20)
    max_wave_m: Optional[float] = None
    max_wind_ms: Optional[float] = None


class FGIPlanRequest(BaseModel):
    date: str
    port_name: str
    vessel_type: VesselType
    priority: PriorityType
    budget_idr: Optional[float] = None
    boat: BoatProfile
    constraints: Constraints


class ScoreBreakdown(BaseModel):
    ocean: float
    safety: float
    economy: float
    regulation: float
    confidence: float
    final: float


class ProbabilityBreakdown(BaseModel):
    trip_success: float
    high_cpue: Optional[float] = None
    operational_feasible: Optional[float] = None


class RegulationResult(BaseModel):
    status: RegulationStatus
    matched_zone_ids: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)


class CandidatePoint(BaseModel):
    rank: int
    lat: float
    lon: float
    distance_km: float
    eta_hours: float
    scores: ScoreBreakdown
    probabilities: ProbabilityBreakdown
    regulation: RegulationResult
    drivers_positive: List[str] = Field(default_factory=list)
    drivers_negative: List[str] = Field(default_factory=list)


class PlanSummary(BaseModel):
    decision: DecisionLabel
    decision_note: str


class ModelMeta(BaseModel):
    version: str
    generated_at: str
    calibration: Optional[str] = None
    mode: str = "alpha"

class CalibrationAdjustment(BaseModel):
    raw_probability: float
    adjusted_probability: float
    adjustment: float
    trust_level: str
    n_fgi_completed: int
    reason: str
    bias: dict

class FGIPlanResponse(BaseModel):
    date: str
    port_name: str
    vessel_type: str
    priority: str
    summary: PlanSummary
    top_scores: Optional[ScoreBreakdown] = None
    top_probabilities: Optional[ProbabilityBreakdown] = None
    calibration_adjustment: Optional[CalibrationAdjustment] = None
    candidates: List[CandidatePoint] = Field(default_factory=list)
    model: ModelMeta
    

