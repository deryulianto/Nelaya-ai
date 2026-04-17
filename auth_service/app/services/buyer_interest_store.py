import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List

from auth_service.app.services.trace_store import find_listing_by_id

BUYER_INTEREST_DIR = Path("/home/coastalai/NELAYA-AI-LAB/data/buyer_interest")

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()

def _ensure_dir() -> None:
    BUYER_INTEREST_DIR.mkdir(parents=True, exist_ok=True)

def _day_file(date_str: str) -> Path:
    _ensure_dir()
    return BUYER_INTEREST_DIR / f"{date_str}.json"

def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

def _write_json_list(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

def create_buyer_interest(listing_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    listing = find_listing_by_id(listing_id)
    if not listing:
        raise ValueError("listing not found")

    if str(listing.get("status", "")).lower() != "available":
        raise ValueError("listing not available")

    date_str = _today_str()
    path = _day_file(date_str)
    rows = _read_json_list(path)

    row = {
        "interest_id": f"INQ-{date_str}-{uuid.uuid4().hex[:8].upper()}",
        "listing_id": listing["listing_id"],
        "batch_id": listing["batch_id"],
        "trip_id": listing["trip_id"],
        "date": listing["date"],
        "landing_port": listing["landing_port"],
        "species_group": listing["species_group"],
        "quality_grade": listing["quality_grade"],
        "price_offer_idr_per_kg": float(listing["price_offer_idr_per_kg"]),
        "available_weight_kg": float(listing["available_weight_kg"]),
        "buyer_name": payload["buyer_name"],
        "buyer_phone": payload["buyer_phone"],
        "buyer_note": payload.get("buyer_note"),
        "created_at": _utcnow_iso(),
    }

    rows.append(row)
    _write_json_list(path, rows)
    return row

def list_all_buyer_interests() -> List[Dict[str, Any]]:
    _ensure_dir()
    out: List[Dict[str, Any]] = []
    for p in BUYER_INTEREST_DIR.glob("*.json"):
        rows = _read_json_list(p)
        out.extend(rows)
    return out