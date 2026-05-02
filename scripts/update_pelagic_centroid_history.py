from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path("/home/coastalai/NELAYA-AI-LAB")
HISTORY_PATH = ROOT / "data" / "fgi_movement" / "pelagic_centroid_history.json"


def fetch_json(url: str) -> Dict[str, Any]:
    with urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def load_history() -> Dict[str, Any]:
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "version": "0.3",
        "updated_at": None,
        "species": {},
    }


def save_history(data: Dict[str, Any]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    HISTORY_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_record(payload: Dict[str, Any], endpoint: str, species: str) -> Dict[str, Any]:
    primary = payload.get("primary_zone") or {}
    zones = payload.get("zones") or []

    if not primary and zones:
        primary = zones[0]

    if not primary:
        raise RuntimeError("Payload tidak memiliki primary_zone atau zones[0].")

    lat = primary.get("center_lat")
    lon = primary.get("center_lon")

    if lat is None or lon is None:
        raise RuntimeError("primary_zone tidak memiliki center_lat/center_lon.")

    return {
        "date": payload.get("date"),
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "species": payload.get("species") or species,
        "lat": float(lat),
        "lon": float(lon),
        "radius_km": primary.get("radius_km"),
        "point_count": primary.get("point_count"),
        "mean_score": primary.get("mean_score"),
        "max_score": primary.get("max_score"),
        "confidence_score": primary.get("confidence_score"),
        "risk_level": primary.get("risk_level"),
        "zone_type": primary.get("zone_type"),
        "direction_hint": primary.get("direction_hint"),
        "best_time_window": primary.get("best_time_window"),
        "drivers": primary.get("drivers", []),
        "source": "fgi_behavior_decision_primary_zone",
        "endpoint": endpoint,
    }


def update_species(history: Dict[str, Any], species: str, record: Dict[str, Any]) -> None:
    history.setdefault("species", {})
    arr = history["species"].setdefault(species, [])

    # Replace tanggal yang sama supaya tidak menumpuk duplikat.
    rec_date = record.get("date")
    arr = [x for x in arr if x.get("date") != rec_date]
    arr.append(record)

    arr.sort(key=lambda x: (str(x.get("date", "")), str(x.get("snapshot_at", ""))))
    history["species"][species] = arr[-60:]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8001")
    ap.add_argument("--species", default="medium_pelagic")
    ap.add_argument("--hotspot-threshold", type=float, default=0.55)
    ap.add_argument("--top-k", type=int, default=20)
    args = ap.parse_args()

    query = urlencode(
        {
            "species": args.species,
            "hotspot_threshold": args.hotspot_threshold,
            "top_k": args.top_k,
        }
    )

    endpoint = f"{args.base_url.rstrip('/')}/api/v1/fgi/behavior/decision?{query}"

    payload = fetch_json(endpoint)
    record = build_record(payload, endpoint, args.species)

    history = load_history()
    update_species(history, args.species, record)
    save_history(history)

    print("✅ Pelagic centroid history updated")
    print("species    :", args.species)
    print("date       :", record.get("date"))
    print("lat/lon    :", record.get("lat"), record.get("lon"))
    print("mean_score :", record.get("mean_score"))
    print("confidence :", record.get("confidence_score"))
    print("risk_level :", record.get("risk_level"))
    print("history    :", HISTORY_PATH)


if __name__ == "__main__":
    main()
