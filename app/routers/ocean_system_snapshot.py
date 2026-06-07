from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json

from fastapi import APIRouter, HTTPException

from app.routers.ocean_health import _build_health
from app.services.ocean_confidence_service import build_confidence_from_health
from app.services.ocean_readiness_service import build_readiness_from_confidence
from app.routers.safe_insight import _build_safe_insight


router = APIRouter(
    prefix="/api/v1/ocean/system-snapshot",
    tags=["ocean-system-snapshot"],
)


def _write_cache(output: dict, name: str):
    out_path = Path("data/health") / name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")


def _layer_status_from_health(health: dict) -> list[dict]:
    rows = []

    for c in health.get("checks", []):
        rows.append({
            "kind": c.get("kind"),
            "status": c.get("status"),
            "internal_latest_date": c.get("internal_latest_date"),
            "date_match": c.get("date_match"),
            "valid_ratio": c.get("valid_ratio"),
            "nan_ratio": c.get("nan_ratio"),
            "message": c.get("message"),
        })

    return rows


def _build_system_snapshot(snapshot_date: str) -> dict:
    health = _build_health(snapshot_date)
    confidence = build_confidence_from_health(health)
    readiness = build_readiness_from_confidence(confidence)
    safe_insight = _build_safe_insight(snapshot_date)

    publish_decision = safe_insight.get("publish_decision", {})
    final_insight = safe_insight.get("final_insight", {})
    conf = confidence.get("confidence", {})
    ready = readiness.get("readiness", {})

    system_status = "unknown"

    if publish_decision.get("publish_allowed") and publish_decision.get("advisory_allowed"):
        system_status = "publishable_advisory_ready"
    elif publish_decision.get("publish_allowed"):
        system_status = "publishable_limited_insight"
    elif health.get("summary", {}).get("overall_status") == "unavailable":
        system_status = "data_unavailable"
    else:
        system_status = "needs_review"

    return {
        "module": "ocean_system_snapshot",
        "version": "0.1.0",
        "snapshot_date": snapshot_date,
        "system_status": system_status,
        "summary": {
            "health_status": health.get("summary", {}).get("overall_status"),
            "confidence_level": conf.get("level"),
            "readiness_level": ready.get("level"),
            "public_status": ready.get("public_status"),
            "publish_allowed": publish_decision.get("publish_allowed"),
            "advisory_allowed": publish_decision.get("advisory_allowed"),
            "content_role": publish_decision.get("content_role"),
        },
        "data_health": health.get("summary", {}),
        "confidence": {
            "level": conf.get("level"),
            "label": conf.get("label"),
            "operational_status": conf.get("operational_status"),
            "completeness_score": conf.get("completeness_score"),
            "available_layers": conf.get("available_layers", []),
            "stale_layers": conf.get("stale_layers", []),
            "missing_layers": conf.get("missing_layers", []),
            "invalid_layers": conf.get("invalid_layers", []),
            "warnings": conf.get("warnings", []),
        },
        "readiness": {
            "level": ready.get("level"),
            "readiness_label": ready.get("readiness_label"),
            "public_status": ready.get("public_status"),
            "insight_mode": ready.get("insight_mode"),
            "advisory_allowed": ready.get("advisory_allowed"),
            "message": ready.get("message"),
            "warnings": ready.get("warnings", []),
        },
        "publish_decision": publish_decision,
        "safe_insight": {
            "title": final_insight.get("title"),
            "subtitle": final_insight.get("subtitle"),
            "readiness_level": final_insight.get("readiness_level"),
            "advisory_allowed": final_insight.get("advisory_allowed"),
            "data_status": final_insight.get("data_status"),
            "safety_note": final_insight.get("safety_note"),
            "full_text": final_insight.get("full_text"),
        },
        "layer_status": _layer_status_from_health(health),
    }


@router.get("/date/{snapshot_date}")
def system_snapshot_by_date(snapshot_date: str):
    try:
        datetime.strptime(snapshot_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Format tanggal harus YYYY-MM-DD, contoh: 2026-06-06",
        )

    return _build_system_snapshot(snapshot_date)


@router.get("/today")
def system_snapshot_today():
    snapshot_date = date.today().isoformat()
    output = _build_system_snapshot(snapshot_date)

    _write_cache(output, "ocean_system_snapshot_today.json")

    return output


@router.get("/latest")
def system_snapshot_latest(lookback_days: int = 7, include_unavailable: bool = False):
    if lookback_days < 1:
        lookback_days = 1

    if lookback_days > 30:
        lookback_days = 30

    today = date.today()
    candidates = []
    first_unavailable = None

    readable_levels = ["high", "medium", "low"]

    for i in range(lookback_days):
        snapshot_date = (today - timedelta(days=i)).isoformat()
        output = _build_system_snapshot(snapshot_date)

        readiness_level = output.get("summary", {}).get("readiness_level")
        publish_allowed = output.get("summary", {}).get("publish_allowed")
        advisory_allowed = output.get("summary", {}).get("advisory_allowed")

        candidates.append({
            "snapshot_date": snapshot_date,
            "system_status": output.get("system_status"),
            "readiness_level": readiness_level,
            "publish_allowed": publish_allowed,
            "advisory_allowed": advisory_allowed,
        })

        if readiness_level == "unavailable" and first_unavailable is None:
            first_unavailable = output
            first_unavailable["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "selection_mode": "unavailable_notice",
                "message": "Snapshot terbaru hanya berupa notice data belum memadai.",
            }

        if publish_allowed and readiness_level in readable_levels:
            output["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "selection_mode": "readable_ocean_system_snapshot",
                "message": "Snapshot sistem terbaru yang masih dapat dibaca ditemukan.",
            }

            _write_cache(output, "ocean_system_snapshot_latest.json")

            return output

        if include_unavailable and publish_allowed:
            output["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "selection_mode": "include_unavailable",
                "message": "Snapshot terbaru ditemukan termasuk unavailable notice.",
            }

            _write_cache(output, "ocean_system_snapshot_latest.json")

            return output

    if first_unavailable is not None:
        first_unavailable["candidates"] = candidates
        _write_cache(first_unavailable, "ocean_system_snapshot_latest_unavailable_notice.json")
        return first_unavailable

    return {
        "module": "ocean_system_snapshot",
        "version": "0.1.0",
        "summary": {
            "overall_status": "unavailable",
            "message": f"Tidak ditemukan system snapshot dalam {lookback_days} hari terakhir.",
        },
        "candidates": candidates,
    }
