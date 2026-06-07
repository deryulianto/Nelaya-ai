from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json

from fastapi import APIRouter, HTTPException

from app.routers.ocean_health import _build_health
from app.services.ocean_confidence_service import build_confidence_from_health
from app.services.ocean_readiness_service import build_readiness_from_confidence


router = APIRouter(
    prefix="/api/v1/ocean/readiness",
    tags=["ocean-readiness"],
)


def _write_cache(output: dict, name: str):
    out_path = Path("data/health") / name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")


def _build_readiness(snapshot_date: str) -> dict:
    health = _build_health(snapshot_date)
    confidence = build_confidence_from_health(health)
    readiness = build_readiness_from_confidence(confidence)
    return readiness


@router.get("/date/{snapshot_date}")
def ocean_readiness_by_date(snapshot_date: str):
    try:
        datetime.strptime(snapshot_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Format tanggal harus YYYY-MM-DD, contoh: 2026-06-05",
        )

    return _build_readiness(snapshot_date)


@router.get("/today")
def ocean_readiness_today():
    snapshot_date = date.today().isoformat()
    readiness = _build_readiness(snapshot_date)

    _write_cache(readiness, "ocean_readiness_today.json")

    return readiness


@router.get("/latest")
def ocean_readiness_latest(lookback_days: int = 7):
    if lookback_days < 1:
        lookback_days = 1

    if lookback_days > 30:
        lookback_days = 30

    today = date.today()
    candidates = []

    for i in range(lookback_days):
        snapshot_date = (today - timedelta(days=i)).isoformat()
        readiness = _build_readiness(snapshot_date)

        candidates.append({
            "snapshot_date": snapshot_date,
            "level": readiness["readiness"]["level"],
            "public_status": readiness["readiness"]["public_status"],
            "advisory_allowed": readiness["readiness"]["advisory_allowed"],
        })

        if readiness["readiness"]["level"] in ["high", "medium", "low"]:
            readiness["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "message": "Snapshot terbaru dengan readiness yang dapat dibaca ditemukan.",
            }

            _write_cache(readiness, "ocean_readiness_latest.json")

            return readiness

    return {
        "module": "ocean_readiness",
        "version": "0.1.0",
        "summary": {
            "overall_status": "unavailable",
            "message": f"Tidak ditemukan snapshot yang dapat dibaca dalam {lookback_days} hari terakhir.",
        },
        "candidates": candidates,
    }
