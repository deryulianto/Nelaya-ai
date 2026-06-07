from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json

from fastapi import APIRouter, HTTPException

from app.routers.ocean_health import _build_health
from app.services.ocean_confidence_service import build_confidence_from_health


router = APIRouter(
    prefix="/api/v1/ocean/confidence",
    tags=["ocean-confidence"],
)


def _write_cache(output: dict, name: str):
    out_path = Path("data/health") / name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")


@router.get("/date/{snapshot_date}")
def ocean_confidence_by_date(snapshot_date: str):
    try:
        datetime.strptime(snapshot_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Format tanggal harus YYYY-MM-DD, contoh: 2026-06-05",
        )

    health = _build_health(snapshot_date)
    return build_confidence_from_health(health)


@router.get("/today")
def ocean_confidence_today():
    snapshot_date = date.today().isoformat()

    health = _build_health(snapshot_date)
    confidence = build_confidence_from_health(health)

    _write_cache(confidence, "ocean_confidence_today.json")

    return confidence


@router.get("/latest")
def ocean_confidence_latest(lookback_days: int = 7):
    if lookback_days < 1:
        lookback_days = 1

    if lookback_days > 30:
        lookback_days = 30

    today = date.today()
    candidates = []

    for i in range(lookback_days):
        snapshot_date = (today - timedelta(days=i)).isoformat()

        health = _build_health(snapshot_date)
        confidence = build_confidence_from_health(health)

        candidates.append({
            "snapshot_date": snapshot_date,
            "confidence_level": confidence["confidence"]["level"],
            "operational_status": confidence["confidence"]["operational_status"],
            "available_layers": confidence["confidence"]["available_layers"],
            "stale_layers": confidence["confidence"]["stale_layers"],
            "missing_layers": confidence["confidence"]["missing_layers"],
            "invalid_layers": confidence["confidence"]["invalid_layers"],
        })

        if confidence["confidence"]["level"] in ["high", "medium", "low"]:
            confidence["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "message": "Snapshot terbaru dengan confidence yang dapat dibaca ditemukan.",
            }

            _write_cache(confidence, "ocean_confidence_latest.json")

            return confidence

    return {
        "module": "ocean_confidence",
        "version": "0.1.0",
        "summary": {
            "overall_status": "unavailable",
            "message": f"Tidak ditemukan snapshot yang dapat dibaca dalam {lookback_days} hari terakhir.",
        },
        "candidates": candidates,
    }
