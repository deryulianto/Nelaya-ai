import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List
import uuid

BATCH_BASE_DIR = Path("/home/coastalai/NELAYA-AI-LAB/data/batches")
LISTING_BASE_DIR = Path("/home/coastalai/NELAYA-AI-LAB/data/listings")

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _ensure_dirs() -> None:
    BATCH_BASE_DIR.mkdir(parents=True, exist_ok=True)
    LISTING_BASE_DIR.mkdir(parents=True, exist_ok=True)

def _listing_day_file(date_str: str) -> Path:
    _ensure_dirs()
    return LISTING_BASE_DIR / f"{date_str}.json"

def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

def _write_json_list(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

def find_batch_by_id(batch_id: str) -> Dict[str, Any] | None:
    _ensure_dirs()
    for p in BATCH_BASE_DIR.glob("*.json"):
        rows = _read_json_list(p)
        for r in rows:
            if r.get("batch_id") == batch_id:
                return r
    return None

def create_listing(batch: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    date_str = batch["date"]
    path = _listing_day_file(date_str)
    rows = _read_json_list(path)

    listing_id = f"LIST-{date_str}-{uuid.uuid4().hex[:8].upper()}"

    row = {
        "listing_id": listing_id,
        "batch_id": batch["batch_id"],
        "trip_id": batch["trip_id"],
        "user_phone": batch["user_phone"],
        "date": batch["date"],
        "landing_port": batch["landing_port"],
        "gear_subtype": batch["gear_subtype"],
        "species_group": batch["species_group"],
        "quality_grade": batch["quality_grade"],
        "price_offer_idr_per_kg": float(payload["price_offer_idr_per_kg"]),
        "available_weight_kg": float(payload["available_weight_kg"]),
        "location": payload["location"],
        "status": payload.get("status") or "available",
        "notes": payload.get("notes"),
        "created_at": _utcnow_iso(),
    }

    rows.append(row)
    _write_json_list(path, rows)
    return row

def list_listings_by_batch(batch_id: str) -> List[Dict[str, Any]]:
    _ensure_dirs()
    out: List[Dict[str, Any]] = []
    for p in LISTING_BASE_DIR.glob("*.json"):
        rows = _read_json_list(p)
        for r in rows:
            if r.get("batch_id") == batch_id:
                out.append(r)
    return out

def list_all_listings() -> List[Dict[str, Any]]:
    _ensure_dirs()
    out: List[Dict[str, Any]] = []
    for p in LISTING_BASE_DIR.glob("*.json"):
        rows = _read_json_list(p)
        out.extend(rows)
    return out
