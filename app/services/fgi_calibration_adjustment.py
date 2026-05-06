from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

DATA_PATH = Path("data/fgi_trip")


def _load_bias_summary() -> Dict[str, Any]:
    trips = []
    for f in DATA_PATH.glob("trip-*.json"):
        try:
            trips.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue

    completed = [
        t for t in trips
        if t.get("status") == "completed"
        and t.get("end")
        and (t.get("fgi_context") or {}).get("from_plan") is True
    ]

    over = 0
    under = 0
    consistent = 0

    for t in completed:
        ctx = t.get("fgi_context") or {}
        end = t.get("end") or {}

        p = ctx.get("trip_success_probability")
        success = end.get("trip_success")

        if p is None or success is None:
            continue

        p = float(p)
        success = int(success)

        if success == 1 and p < 0.5:
            under += 1
        elif success == 0 and p > 0.65:
            over += 1
        else:
            consistent += 1

    total = max(len(completed), 1)

    return {
        "n_fgi_completed": len(completed),
        "overestimate_rate": over / total,
        "underestimate_rate": under / total,
        "consistent_rate": consistent / total,
    }


def trust_level(n_fgi_completed: int) -> str:
    if n_fgi_completed < 5:
        return "low"
    if n_fgi_completed < 20:
        return "medium"
    return "high"


def adjust_trip_probability(p: float) -> Dict[str, Any]:
    bias = _load_bias_summary()

    adjustment = 0.0
    reason = "Belum cukup data untuk koreksi kuat."

    if bias["n_fgi_completed"] >= 5:
        if bias["overestimate_rate"] > 0.3:
            adjustment -= 0.05
            reason = "FGI cenderung terlalu optimis pada data lapangan awal."
        elif bias["underestimate_rate"] > 0.3:
            adjustment += 0.05
            reason = "FGI cenderung terlalu pesimis pada data lapangan awal."
        else:
            reason = "FGI belum menunjukkan bias kuat pada data lapangan awal."

    adjusted = max(0.0, min(1.0, p + adjustment))

    return {
        "raw_probability": round(p, 4),
        "adjusted_probability": round(adjusted, 4),
        "adjustment": round(adjustment, 4),
        "trust_level": trust_level(bias["n_fgi_completed"]),
        "n_fgi_completed": bias["n_fgi_completed"],
        "reason": reason,
        "bias": {
            "overestimate_rate": round(bias["overestimate_rate"], 4),
            "underestimate_rate": round(bias["underestimate_rate"], 4),
            "consistent_rate": round(bias["consistent_rate"], 4),
        },
    }
