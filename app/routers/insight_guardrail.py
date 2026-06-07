from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json

from fastapi import APIRouter, HTTPException

from app.routers.ocean_readiness import _build_readiness
from app.services.insight_guardrail_service import build_insight_guardrail_from_readiness


router = APIRouter(
    prefix="/api/v1/ocean/insight-guardrail",
    tags=["ocean-insight-guardrail"],
)


def _write_cache(output: dict, name: str):
    out_path = Path("data/health") / name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")


def _build_guardrail(snapshot_date: str) -> dict:
    readiness = _build_readiness(snapshot_date)
    guardrail = build_insight_guardrail_from_readiness(readiness)
    return guardrail


@router.get("/date/{snapshot_date}")
def insight_guardrail_by_date(snapshot_date: str):
    try:
        datetime.strptime(snapshot_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Format tanggal harus YYYY-MM-DD, contoh: 2026-06-05",
        )

    return _build_guardrail(snapshot_date)


@router.get("/today")
def insight_guardrail_today():
    snapshot_date = date.today().isoformat()
    guardrail = _build_guardrail(snapshot_date)

    _write_cache(guardrail, "insight_guardrail_today.json")

    return guardrail


@router.get("/latest")
def insight_guardrail_latest(lookback_days: int = 7):
    if lookback_days < 1:
        lookback_days = 1

    if lookback_days > 30:
        lookback_days = 30

    today = date.today()
    candidates = []

    for i in range(lookback_days):
        snapshot_date = (today - timedelta(days=i)).isoformat()
        guardrail = _build_guardrail(snapshot_date)

        candidates.append({
            "snapshot_date": snapshot_date,
            "readiness_level": guardrail["guardrail"]["readiness_level"],
            "advisory_allowed": guardrail["guardrail"]["advisory_allowed"],
            "allowed_claim_level": guardrail["guardrail"]["allowed_claim_level"],
        })

        if guardrail["guardrail"]["readiness_level"] in ["high", "medium", "low"]:
            guardrail["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "message": "Snapshot terbaru dengan insight guardrail ditemukan.",
            }

            _write_cache(guardrail, "insight_guardrail_latest.json")

            return guardrail

    return {
        "module": "insight_guardrail",
        "version": "0.1.0",
        "summary": {
            "overall_status": "unavailable",
            "message": f"Tidak ditemukan guardrail yang dapat digunakan dalam {lookback_days} hari terakhir.",
        },
        "candidates": candidates,
    }
