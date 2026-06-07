from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter

from app.routers.ocean_system_snapshot import _build_system_snapshot


router = APIRouter(
    prefix="/api/v1/ocean/system-card",
    tags=["ocean-system-card"],
)


def _build_card_from_snapshot(snapshot: dict) -> dict:
    summary = snapshot.get("summary", {})
    confidence = snapshot.get("confidence", {})
    readiness = snapshot.get("readiness", {})
    publish_decision = snapshot.get("publish_decision", {})
    safe_insight = snapshot.get("safe_insight", {})

    available_layers = confidence.get("available_layers", [])
    stale_layers = confidence.get("stale_layers", [])
    missing_layers = confidence.get("missing_layers", [])
    invalid_layers = confidence.get("invalid_layers", [])

    readiness_level = summary.get("readiness_level")
    public_status = summary.get("public_status")
    publish_allowed = summary.get("publish_allowed")
    advisory_allowed = summary.get("advisory_allowed")

    if advisory_allowed:
        badge = "Advisory Ready"
        badge_status = "advisory_ready"
    elif readiness_level == "high":
        badge = "Insight Kuat"
        badge_status = "high_confidence_insight"
    elif readiness_level == "medium":
        badge = "Indikasi Awal"
        badge_status = "medium_confidence_insight"
    elif readiness_level == "low":
        badge = "Insight Terbatas"
        badge_status = "limited_insight"
    elif readiness_level == "unavailable" or public_status == "data_belum_memadai":
        badge = "Data Belum Memadai"
        badge_status = "data_unavailable"
    elif publish_allowed:
        badge = "Insight Publik"
        badge_status = "public_insight"
    else:
        badge = "Perlu Review"
        badge_status = "needs_review"

    return {
        "module": "ocean_system_card",
        "version": "0.1.1",
        "snapshot_date": snapshot.get("snapshot_date"),
        "system_status": snapshot.get("system_status"),
        "card": {
            "title": "Ocean Reading Status",
            "badge": badge,
            "badge_status": badge_status,
            "health_status": summary.get("health_status"),
            "confidence_level": summary.get("confidence_level"),
            "readiness_level": readiness_level,
            "public_status": public_status,
            "publish_allowed": publish_allowed,
            "advisory_allowed": advisory_allowed,
            "content_role": summary.get("content_role"),
            "message": readiness.get("message"),
            "safe_title": safe_insight.get("title"),
            "safe_subtitle": safe_insight.get("subtitle"),
        },
        "layers": {
            "available": available_layers,
            "stale": stale_layers,
            "missing": missing_layers,
            "invalid": invalid_layers,
        },
        "warnings": readiness.get("warnings", []),
        "publish_decision": publish_decision,
        "latest_search": snapshot.get("latest_search"),
    }


@router.get("/date/{snapshot_date}")
def system_card_by_date(snapshot_date: str):
    snapshot = _build_system_snapshot(snapshot_date)
    return _build_card_from_snapshot(snapshot)


@router.get("/today")
def system_card_today():
    snapshot_date = date.today().isoformat()
    snapshot = _build_system_snapshot(snapshot_date)
    return _build_card_from_snapshot(snapshot)


@router.get("/latest")
def system_card_latest(lookback_days: int = 7, include_unavailable: bool = False):
    """
    Default:
    Cari card terbaru yang masih readable sebagai ocean insight:
    high / medium / low.

    Jika include_unavailable=true:
    boleh menampilkan notice hari ini walau data belum memadai.
    """

    if lookback_days < 1:
        lookback_days = 1

    if lookback_days > 30:
        lookback_days = 30

    today = date.today()
    readable_levels = ["high", "medium", "low"]

    first_unavailable = None
    candidates = []

    for i in range(lookback_days):
        snapshot_date = (today - timedelta(days=i)).isoformat()
        snapshot = _build_system_snapshot(snapshot_date)

        summary = snapshot.get("summary", {})
        readiness_level = summary.get("readiness_level")
        publish_allowed = summary.get("publish_allowed")
        advisory_allowed = summary.get("advisory_allowed")

        candidates.append({
            "snapshot_date": snapshot_date,
            "readiness_level": readiness_level,
            "publish_allowed": publish_allowed,
            "advisory_allowed": advisory_allowed,
            "system_status": snapshot.get("system_status"),
        })

        if readiness_level == "unavailable" and first_unavailable is None:
            first_unavailable = snapshot
            first_unavailable["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "selection_mode": "unavailable_notice",
                "message": "Snapshot terbaru hanya berupa notice data belum memadai.",
            }

        if publish_allowed and readiness_level in readable_levels:
            snapshot["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "selection_mode": "readable_ocean_system_card",
                "message": "System card terbaru yang masih dapat dibaca ditemukan.",
            }

            card = _build_card_from_snapshot(snapshot)
            card["candidates"] = candidates
            return card

        if include_unavailable and publish_allowed:
            snapshot["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "days_behind_today": i,
                "selection_mode": "include_unavailable",
                "message": "System card terbaru ditemukan termasuk unavailable notice.",
            }

            card = _build_card_from_snapshot(snapshot)
            card["candidates"] = candidates
            return card

    if first_unavailable is not None:
        card = _build_card_from_snapshot(first_unavailable)
        card["candidates"] = candidates
        return card

    return {
        "module": "ocean_system_card",
        "version": "0.1.1",
        "summary": {
            "overall_status": "unavailable",
            "message": f"Tidak ditemukan system card dalam {lookback_days} hari terakhir.",
        },
        "candidates": candidates,
    }
