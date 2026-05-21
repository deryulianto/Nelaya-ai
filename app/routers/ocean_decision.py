from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(
    prefix="/api/v1/ocean-decision",
    tags=["ocean-decision"],
)

ROOT = Path(__file__).resolve().parents[2]

TODAY_FILE = ROOT / "data" / "decision" / "integrated_ocean_decision_today.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read JSON: {exc}")


@router.get("/health")
def health():
    exists = TODAY_FILE.exists()

    payload: dict[str, Any] = {
        "api": "ocean_decision_health",
        "ok": exists,
        "status": "ready" if exists else "missing",
        "file": str(TODAY_FILE),
        "file_exists": exists,
        "scientific_position": (
            "Integrated probabilistic ocean decision layer; "
            "not a deterministic prediction and not a fish-location claim."
        ),
    }

    if exists:
        data = read_json(TODAY_FILE)
        payload["version"] = data.get("version")
        payload["snapshot_date"] = data.get("snapshot_date")
        payload["confidence"] = data.get("confidence")
        payload["decision_score"] = (
            data.get("integrated_decision", {}).get("score")
        )
        payload["decision_level"] = (
            data.get("integrated_decision", {}).get("level")
        )

    return payload


@router.get("/today")
def today():
    data = read_json(TODAY_FILE)

    return JSONResponse(
        data,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )


@router.get("/summary")
def summary():
    data = read_json(TODAY_FILE)

    return JSONResponse(
        {
            "module": data.get("module"),
            "version": data.get("version"),
            "status": data.get("status"),
            "created_at": data.get("created_at"),
            "snapshot_date": data.get("snapshot_date"),
            "scientific_position": data.get("scientific_position"),
            "confidence": data.get("confidence"),
            "integrated_decision": data.get("integrated_decision"),
            "narrative": data.get("narrative"),
            "earth": data.get("earth"),
            "current_analysis": data.get("current_analysis"),
            "tuna_depth": data.get("tuna_depth"),
            "ns_diagnostics": data.get("ns_diagnostics"),
            "temporal_memory": data.get("temporal_memory"),
            "audience_cards": data.get("audience_cards"),
            "inputs": data.get("inputs"),
        },
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )


@router.get("/audiences")
def audiences():
    data = read_json(TODAY_FILE)

    return JSONResponse(
        {
            "version": data.get("version"),
            "snapshot_date": data.get("snapshot_date"),
            "confidence": data.get("confidence"),
            "integrated_decision": data.get("integrated_decision"),
            "audience_cards": data.get("audience_cards") or [],
        },
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )
