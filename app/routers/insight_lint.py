from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.routers.insight_guardrail import _build_guardrail
from app.services.insight_lint_service import lint_insight_text


router = APIRouter(
    prefix="/api/v1/ocean/insight-lint",
    tags=["ocean-insight-lint"],
)


class InsightLintRequest(BaseModel):
    text: str = Field(..., min_length=1)


@router.post("/date/{snapshot_date}")
def lint_insight_by_date(snapshot_date: str, payload: InsightLintRequest):
    try:
        datetime.strptime(snapshot_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Format tanggal harus YYYY-MM-DD, contoh: 2026-06-05",
        )

    guardrail = _build_guardrail(snapshot_date)
    return lint_insight_text(payload.text, guardrail)


@router.post("/today")
def lint_insight_today(payload: InsightLintRequest):
    snapshot_date = date.today().isoformat()
    guardrail = _build_guardrail(snapshot_date)
    return lint_insight_text(payload.text, guardrail)


@router.post("/latest")
def lint_insight_latest(payload: InsightLintRequest, lookback_days: int = 7):
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
        })

        if guardrail["guardrail"]["readiness_level"] in ["high", "medium", "low"]:
            result = lint_insight_text(payload.text, guardrail)
            result["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "message": "Snapshot terbaru dengan insight lint ditemukan.",
            }
            return result

    return {
        "module": "insight_lint",
        "version": "0.1.0",
        "summary": {
            "overall_status": "unavailable",
            "message": f"Tidak ditemukan guardrail untuk lint dalam {lookback_days} hari terakhir.",
        },
        "candidates": candidates,
    }
