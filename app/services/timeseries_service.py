from __future__ import annotations

from typing import Any, Dict, Optional


def get_trend_summary(region: Optional[str], metric: Optional[str]) -> Dict[str, Any]:
    metric = metric or "sst"

    # placeholder aman untuk v1
    # nanti bisa dihubungkan ke CSV/JSON time-series real milik NELAYA-AI
    if metric == "sst":
        return {
            "metric": "sst",
            "today": 29.4,
            "avg_7d": 29.1,
            "avg_30d": 28.8,
            "anomaly": 0.6,
            "trend": "naik",
        }
    if metric == "chlorophyll":
        return {
            "metric": "chlorophyll",
            "today": 0.43,
            "avg_7d": 0.40,
            "avg_30d": 0.45,
            "anomaly": -0.02,
            "trend": "stabil",
        }
    if metric == "wave":
        return {
            "metric": "wave",
            "today": 0.8,
            "avg_7d": 0.9,
            "avg_30d": 1.1,
            "anomaly": -0.3,
            "trend": "turun",
        }

    return {
        "metric": metric,
        "today": None,
        "avg_7d": None,
        "avg_30d": None,
        "anomaly": None,
        "trend": "unknown",
    }
