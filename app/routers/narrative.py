from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.signal_interpreter import generate_narrative

router = APIRouter(prefix="/api/v1/narrative", tags=["narrative"])


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _load_today_payload() -> Dict[str, Any]:
    candidate_paths = [
        Path("data/earth_signals_today.json"),
        Path("data/earth/earth_signals_today.json"),
        Path("data/signals_today.json"),
    ]

    for p in candidate_paths:
        payload = _read_json(p)
        if payload:
            return payload

    raise HTTPException(
        status_code=404,
        detail="Data sinyal harian belum ditemukan. Pastikan earth_signals_today.json sudah tersedia.",
    )


@router.get("/today")
def get_narrative_today(
    mode: str = Query("reflective", description="operational | education | reflective"),
    region_name: str = Query("Aceh, Indonesia"),
):
    payload = _load_today_payload()
    return generate_narrative(
        payload=payload,
        mode=mode,
        region_name=region_name,
    )