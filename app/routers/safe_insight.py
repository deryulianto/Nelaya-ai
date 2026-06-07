from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json

from fastapi import APIRouter, HTTPException

from app.routers.guarded_insight import _build_guarded_insight
from app.services.safe_insight_pipeline_service import build_safe_insight_pipeline


router = APIRouter(
    prefix="/api/v1/ocean/safe-insight",
    tags=["ocean-safe-insight"],
)


def _write_cache(output: dict, name: str):
    out_path = Path("data/health") / name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")


def _build_safe_insight(snapshot_date: str) -> dict:
    guarded = _build_guarded_insight(snapshot_date)
    return build_safe_insight_pipeline(guarded)


@router.get("/date/{snapshot_date}")
def safe_insight_by_date(snapshot_date: str):
    try:
        datetime.strptime(snapshot_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Format tanggal harus YYYY-MM-DD, contoh: 2026-06-05",
        )

    return _build_safe_insight(snapshot_date)


@router.get("/today")
def safe_insight_today():
    snapshot_date = date.today().isoformat()
    output = _build_safe_insight(snapshot_date)

    _write_cache(output, "safe_insight_today.json")

    return output


@router.get("/latest")
def safe_insight_latest(lookback_days: int = 7, include_unavailable: bool = False):
    """
    Default:
    Cari snapshot terbaru yang masih readable sebagai ocean insight:
    high / medium / low.

    Jika include_unavailable=true:
    boleh berhenti pada unavailable notice.
    """

    if lookback_days < 1:
        lookback_days = 1

    if lookback_days > 30:
        lookback_days = 30

    today = date.today()
    candidates = []
    first_unavailable_notice = None

    readable_levels = ["high", "medium", "low"]

    for i in range(lookback_days):
        snapshot_date = (today - timedelta(days=i)).isoformat()
        output = _build_safe_insight(snapshot_date)

        readiness_level = output["final_insight"]["readiness_level"]
        publish_allowed = output["publish_decision"]["publish_allowed"]
        advisory_allowed = output["publish_decision"]["advisory_allowed"]
        publish_status = output["publish_decision"]["publish_status"]

        candidate = {
            "snapshot_date": snapshot_date,
            "readiness_level": readiness_level,
            "publish_allowed": publish_allowed,
            "advisory_allowed": advisory_allowed,
            "publish_status": publish_status,
        }
        candidates.append(candidate)

        if readiness_level == "unavailable" and publish_allowed and first_unavailable_notice is None:
            first_unavailable_notice = output
            first_unavailable_notice["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "message": "Snapshot terbaru hanya berupa notice data belum memadai.",
                "selection_mode": "unavailable_notice",
            }

        if publish_allowed and readiness_level in readable_levels:
            output["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "message": "Snapshot terbaru dengan readable safe insight ditemukan.",
                "selection_mode": "readable_ocean_insight",
            }

            _write_cache(output, "safe_insight_latest.json")

            return output

        if include_unavailable and publish_allowed:
            output["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "message": "Snapshot terbaru ditemukan termasuk unavailable notice.",
                "selection_mode": "include_unavailable",
            }

            _write_cache(output, "safe_insight_latest.json")

            return output

    if first_unavailable_notice is not None:
        first_unavailable_notice["candidates"] = candidates
        _write_cache(first_unavailable_notice, "safe_insight_latest_unavailable_notice.json")
        return first_unavailable_notice

    return {
        "module": "safe_insight_pipeline",
        "version": "0.1.0",
        "summary": {
            "overall_status": "unavailable",
            "message": f"Tidak ditemukan safe insight dalam {lookback_days} hari terakhir.",
        },
        "candidates": candidates,
    }
