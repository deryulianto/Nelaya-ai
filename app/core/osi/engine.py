from __future__ import annotations

from .config import OSI_WEIGHTS
from .domains import (
    compute_confidence_score,
    compute_dynamic_score,
    compute_productivity_score,
    compute_thermal_score,
    compute_vertical_score,
)
from .narrative import build_narrative, osi_label
from .schemas import OsiComponents, OsiFeatures, OsiNarrative, OsiResponse
from .scoring import clamp


def _detect_missing(features: OsiFeatures) -> list[str]:
    missing: list[str] = []

    optional_fields = [
        "sst_anom_c",
        "sst_gradient",
        "chl_anom",
        "chl_persistence_3d",
        "chl_gradient",
        "current_ms",
        "ssh_anom_cm",
        "delta_t_0_200",
        "stratification_index",
        "spatial_distance_km",
        "time_alignment_score",
    ]

    for name in optional_fields:
        if getattr(features, name, None) is None:
            missing.append(name)

    return missing


def compute_osi(features: OsiFeatures) -> OsiResponse:
    missing = _detect_missing(features)

    s_thermal = compute_thermal_score(features)
    s_productivity = compute_productivity_score(features)
    s_dynamic = compute_dynamic_score(features)
    s_vertical = compute_vertical_score(features)
    s_confidence = compute_confidence_score(features)

    osi_raw = (
        OSI_WEIGHTS.thermal * s_thermal
        + OSI_WEIGHTS.productivity * s_productivity
        + OSI_WEIGHTS.dynamic * s_dynamic
        + OSI_WEIGHTS.vertical * s_vertical
        + OSI_WEIGHTS.confidence * s_confidence
    )
    osi = round(clamp(osi_raw), 2)
    label = osi_label(osi)

    components = {
        "thermal": round(s_thermal, 2),
        "productivity": round(s_productivity, 2),
        "dynamic": round(s_dynamic, 2),
        "vertical": round(s_vertical, 2),
        "data_confidence": round(s_confidence, 2),
    }

    narrative_dict = build_narrative(label, components)
    status = "partial" if missing else "ok"

    return OsiResponse(
        region=features.region,
        date=features.date,
        osi=osi,
        label=label,
        confidence=round(s_confidence, 2),
        components=OsiComponents(**components),
        inputs=features.model_dump(),
        narrative=OsiNarrative(**narrative_dict),
        status=status,
        missing=missing,
    )
