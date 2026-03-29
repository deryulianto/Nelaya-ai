from __future__ import annotations

from typing import Any, Dict, Optional

from app.schemas.ocean_ask import OceanAskRequest


ALLOWED_PERSONAS = {"publik", "nelayan", "lab", "kebijakan"}
ALLOWED_MODES = {"ringkas", "detail"}


def normalize_persona(persona: Optional[str]) -> str:
    p = (persona or "publik").strip().lower()
    if p not in ALLOWED_PERSONAS:
        return "publik"
    return p


def normalize_mode(mode: Optional[str]) -> str:
    m = (mode or "ringkas").strip().lower()
    if m not in ALLOWED_MODES:
        return "ringkas"
    return m


def resolve_region(region: Optional[str]) -> str:
    r = (region or "").strip()
    return r if r else "Aceh"


def build_context(req: OceanAskRequest, routing: Dict[str, Any]) -> Dict[str, Any]:
    region = resolve_region(req.region)
    persona = normalize_persona(req.persona)
    mode = normalize_mode(req.mode)
    metric = routing.get("metric")

    return {
        "region": region,
        "persona": persona,
        "mode": mode,
        "metric": metric,
        "query_type": routing.get("query_type", "ocean"),
        "topics": routing.get("topics", []),
        "normalized_question": routing.get("normalized_question", ""),
    }
