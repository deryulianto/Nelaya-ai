from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class OceanAskRequest(BaseModel):
    question: str = Field(..., min_length=2)
    region: Optional[str] = None
    persona: str = "publik"
    mode: str = "ringkas"
    context: Optional[Dict[str, Any]] = None


class OceanAnswerBlock(BaseModel):
    headline: str
    summary: str
    recommendation: Optional[str] = None
    caution: Optional[str] = None


class OceanAskResponse(BaseModel):
    ok: bool = True
    question: str
    intent: str
    sub_intents: List[str] = Field(default_factory=list)
    region: Optional[str] = None
    persona: str
    mode: str
    answer: OceanAnswerBlock
    evidence: Dict[str, Any] = Field(default_factory=dict)
    scores: Dict[str, float] = Field(default_factory=dict)
    explanation: List[str] = Field(default_factory=list)
    data_status: Dict[str, Any] = Field(default_factory=dict)
