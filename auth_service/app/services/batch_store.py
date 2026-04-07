import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List
import uuid

TRIPS_BASE_DIR = Path("/home/coastalai/NELAYA-AI-LAB/data/trips")
BATCH_BASE_DIR = Path("/home/coastalai/NELAYA-AI-LAB/data/batches")

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _ensure_dirs() -> None:
    TRIPS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    BATCH_BASE_DIR.mkdir(parents=True, exist_ok=True)

def _trip_day_file(date_str: str) -> Path:
    _ensure_dirs()
    return TRIPS_BASE_DIR / f"{date_str}.json"

def _batch_day_file(date_str: str) -> Path:
    _ensure_dirs()
    return BATCH_BASE_DIR / f"{date_str}.json"

def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

def _write_json_list(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

def find_trip_by_id(trip_id: str) -> Dict[str, Any] | None:
    _ensure_dirs()
    for p in TRIPS_BASE_DIR.glob("*.json"):
        rows = _read_json_list(p)
        for r in rows:
            if r.get("trip_id") == trip_id:
                return r
    return None

def create_batch(trip: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    date_str = trip["date"]
    path = _batch_day_file(date_str)
    rows = _read_json_list(path)

    batch_id = f"BATCH-{date_str}-{uuid.uuid4().hex[:8].upper()}"

    row = {
        "batch_id": batch_id,
        "trip_id": trip["trip_id"],
        "user_phone": trip["user_phone"],
        "date": trip["date"],
        "landing_port": trip["landing_port"],
        "gear_subtype": trip["gear_subtype"],
        "species_group": payload["species_group"],
        "weight_kg": float(payload["weight_kg"]),
        "quality_grade": payload["quality_grade"],
        "notes": payload.get("notes"),
        "created_at": _utcnow_iso(),
    }

    rows.append(row)
    _write_json_list(path, rows)
    return row

def list_batches_by_trip(trip_id: str) -> List[Dict[str, Any]]:
    _ensure_dirs()
    out: List[Dict[str, Any]] = []
    for p in BATCH_BASE_DIR.glob("*.json"):
        rows = _read_json_list(p)
        for r in rows:
            if r.get("trip_id") == trip_id:
                out.append(r)
    return out
