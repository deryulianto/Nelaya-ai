from __future__ import annotations

from pathlib import Path
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1/earth", tags=["Earth"])

ROOT = Path(__file__).resolve().parents[2]

CANDIDATES = [
    ROOT / "data" / "earth_signals_today.json",
    ROOT / "data" / "earth" / "earth_signals_today.json",
    ROOT / "data" / "signals_today.json",
]

def _pick_file() -> Path:
    for p in CANDIDATES:
        if p.exists():
            return p
    return CANDIDATES[0]

@router.get("/ping")
def ping():
    return {"ok": True, "service": "earth"}

@router.get("/today")
def today(trace: str | None = Query(default=None)):
    fp = _pick_file()
    if not fp.exists():
        raise HTTPException(status_code=404, detail=f"Missing earth signals file: {fp}")
    payload = json.loads(fp.read_text(encoding="utf-8"))
    payload.setdefault("meta", {})
    payload["meta"].setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    if trace:
        payload["meta"]["trace"] = trace
    return payload
