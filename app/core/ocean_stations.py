from __future__ import annotations

from typing import Any

STATIONS: dict[str, dict[str, Any]] = {
    "malaka": {
        "id": "malaka",
        "label": "Selat Malaka",
        "short_label": "Malaka",
        "basin": "Malacca Strait",
        "lat": 5.300753,
        "lon": 96.420167,
        "sampling": "window_mean_3x3_wet_cells",
    },
    "andaman": {
        "id": "andaman",
        "label": "Laut Utara Aceh (Andaman)",
        "short_label": "Andaman",
        "basin": "Andaman Sea",
        "lat": 5.896967,
        "lon": 94.946861,
        "sampling": "window_mean_3x3_wet_cells",
    },
    "hindia": {
        "id": "hindia",
        "label": "Samudra Hindia",
        "short_label": "Hindia",
        "basin": "Indian Ocean",
        "lat": 5.153900,
        "lon": 94.648253,
        "sampling": "window_mean_3x3_wet_cells",
    },
}


def get_station(station_id: str) -> dict[str, Any] | None:
    key = (station_id or "").strip().lower()
    return STATIONS.get(key)


def list_stations() -> list[dict[str, Any]]:
    order = ["malaka", "andaman", "hindia"]
    return [STATIONS[k] for k in order if k in STATIONS]