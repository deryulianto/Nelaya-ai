import json
from pathlib import Path
from typing import Dict, Any, List, Optional

TRIPS_BASE_DIR = Path("/home/coastalai/NELAYA-AI-LAB/data/trips")
BATCH_BASE_DIR = Path("/home/coastalai/NELAYA-AI-LAB/data/batches")
LISTING_BASE_DIR = Path("/home/coastalai/NELAYA-AI-LAB/data/listings")

def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

def find_listing_by_id(listing_id: str) -> Optional[Dict[str, Any]]:
    for p in LISTING_BASE_DIR.glob("*.json"):
        rows = _read_json_list(p)
        for r in rows:
            if r.get("listing_id") == listing_id:
                return r
    return None

def find_batch_by_id(batch_id: str) -> Optional[Dict[str, Any]]:
    for p in BATCH_BASE_DIR.glob("*.json"):
        rows = _read_json_list(p)
        for r in rows:
            if r.get("batch_id") == batch_id:
                return r
    return None

def find_trip_by_id(trip_id: str) -> Optional[Dict[str, Any]]:
    for p in TRIPS_BASE_DIR.glob("*.json"):
        rows = _read_json_list(p)
        for r in rows:
            if r.get("trip_id") == trip_id:
                return r
    return None

def get_trace_by_listing_id(listing_id: str) -> Optional[Dict[str, Any]]:
    listing = find_listing_by_id(listing_id)
    if not listing:
        return None

    batch = find_batch_by_id(listing.get("batch_id"))
    trip = find_trip_by_id(listing.get("trip_id"))

    return {
        "listing": listing,
        "batch": batch,
        "trip": trip,
    }
