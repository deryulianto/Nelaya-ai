# app/routers/surf_v1.py
from __future__ import annotations

from pathlib import Path
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/surf", tags=["Surf"])

ROOT = Path(__file__).resolve().parents[2]
DERIVED_DIR = ROOT / "data" / "derived" / "surf_snapshot"
LATEST = DERIVED_DIR / "surf_wave_snapshot_latest.json"
PAT = re.compile(r"surf_wave_snapshot_(\d{4}-\d{2}-\d{2})\.json$")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _no_store(data: Any, status: int = 200) -> JSONResponse:
    resp = JSONResponse(data, status_code=status)
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def _load_json(p: Path) -> Dict[str, Any]:
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"missing_file: {p}")
    try:
        return json.loads(p.read_text())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"bad_json: {p.name}: {e}")


@router.get("/spots/today")
def spots_today():
    raw = _load_json(LATEST)
    # return "as is" (spots dict), portal yang normalisasi jadi array
    payload = {"ok": True, "generated_at": _utc_now_z(), **raw}
    return _no_store(payload)


@router.get("/spots/history")
def spots_history(days: int = Query(7, ge=1, le=60)):
    # ambil snapshot harian terakhir N hari
    files: List[Tuple[str, Path]] = []
    for p in DERIVED_DIR.glob("surf_wave_snapshot_*.json"):
        m = PAT.search(p.name)
        if m:
            files.append((m.group(1), p))

    if not files:
        raise HTTPException(status_code=404, detail="no_history_files")

    files.sort(key=lambda x: x[0])
    take = files[-days:]

    # series per spot_id
    series: Dict[str, List[Dict[str, Any]]] = {}
    for day, p in take:
        raw = _load_json(p)
        spots = raw.get("spots") or {}
        if isinstance(spots, dict):
            for sid, s in spots.items():
                series.setdefault(sid, []).append(
                    {
                        "t": day,
                        "hs_m": s.get("hs_m"),
                        "tp_s": s.get("tp_s"),
                        "dir_deg": s.get("dir_deg"),
                    }
                )

    payload = {
        "ok": True,
        "days": days,
        "generated_at": _utc_now_z(),
        "series": series,
    }
    return _no_store(payload)
