import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List
import uuid

TRIPS_BASE_DIR = Path("/home/coastalai/NELAYA-AI-LAB/data/trips")

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _ensure_dir() -> None:
    TRIPS_BASE_DIR.mkdir(parents=True, exist_ok=True)

def _day_file(date_str: str) -> Path:
    _ensure_dir()
    return TRIPS_BASE_DIR / f"{date_str}.json"

def _read_day(date_str: str) -> List[Dict[str, Any]]:
    path = _day_file(date_str)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

def _write_day(date_str: str, rows: List[Dict[str, Any]]) -> None:
    path = _day_file(date_str)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

def create_trip(payload: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    date_str = payload["date"]

    trip_id = f"TRIP-{date_str}-{uuid.uuid4().hex[:8].upper()}"

    row = {
        "trip_id": trip_id,
        "user_phone": user["phone_e164"],
        "date": date_str,
        "landing_port": user.get("landing_port"),
        "gear_subtype": user.get("gear_subtype"),
        "vessel_gt_class": user.get("vessel_gt_class") or "GT_5_10",
        "grid_id": payload["grid_id"],
        "departure_time": payload.get("departure_time"),
        "landing_time": payload.get("landing_time"),
        "trip_hours": payload.get("trip_hours"),
        "catch_total_kg": float(payload["catch_total_kg"]),
        "notes": payload.get("notes"),
        "created_at": _utcnow_iso(),
    }

    rows = _read_day(date_str)
    rows.append(row)
    _write_day(date_str, rows)
    return row

def list_trips_by_user(phone_e164: str, date_str: str) -> List[Dict[str, Any]]:
    rows = _read_day(date_str)
    return [r for r in rows if r.get("user_phone") == phone_e164]
