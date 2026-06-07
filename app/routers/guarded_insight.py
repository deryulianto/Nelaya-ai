from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json

from fastapi import APIRouter, HTTPException

from app.routers.insight_guardrail import _build_guardrail
from app.services.guarded_insight_composer_service import build_guarded_insight_from_guardrail


router = APIRouter(
    prefix="/api/v1/ocean/guarded-insight",
    tags=["ocean-guarded-insight"],
)


def _write_cache(output: dict, name: str):
    out_path = Path("data/health") / name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")


def _build_guarded_insight(snapshot_date: str) -> dict:
    guardrail = _build_guardrail(snapshot_date)
    return build_guarded_insight_from_guardrail(guardrail)


@router.get("/date/{snapshot_date}")
def guarded_insight_by_date(snapshot_date: str):
    try:
        datetime.strptime(snapshot_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Format tanggal harus YYYY-MM-DD, contoh: 2026-06-05",
        )

    return _build_guarded_insight(snapshot_date)


@router.get("/today")
def guarded_insight_today():
    snapshot_date = date.today().isoformat()
    output = _build_guarded_insight(snapshot_date)

    _write_cache(output, "guarded_insight_today.json")

    return output


@router.get("/latest")
def guarded_insight_latest(lookback_days: int = 7):
    if lookback_days < 1:
        lookback_days = 1

    if lookback_days > 30:
        lookback_days = 30

    today = date.today()
    candidates = []

    for i in range(lookback_days):
        snapshot_date = (today - timedelta(days=i)).isoformat()
        output = _build_guarded_insight(snapshot_date)

        candidates.append({
            "snapshot_date": snapshot_date,
            "readiness_level": output["guarded_insight"]["readiness_level"],
            "advisory_allowed": output["guarded_insight"]["advisory_allowed"],
            "title": output["guarded_insight"]["title"],
        })

        if output["guarded_insight"]["readiness_level"] in ["high", "medium", "low"]:
            output["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "message": "Snapshot terbaru dengan guarded insight ditemukan.",
            }

            _write_cache(output, "guarded_insight_latest.json")

            return output

    return {
        "module": "guarded_insight_composer",
        "version": "0.1.0",
        "summary": {
            "overall_status": "unavailable",
            "message": f"Tidak ditemukan guarded insight dalam {lookback_days} hari terakhir.",
        },
        "candidates": candidates,
    }
