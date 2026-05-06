from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/api/v1/current-analysis", tags=["current-analysis"])

ROOT = Path(__file__).resolve().parents[2]

CURRENT_MAP_PNG = ROOT / "data" / "physics" / "current_surface_map_today.png"
SUMMARY_FILE = ROOT / "data" / "physics" / "current_analysis_today.json"
DASHBOARD_PNG = ROOT / "data" / "physics" / "current_analysis_dashboard_today.png"
GEOJSON_FILE = ROOT / "data" / "physics" / "current_analysis_latest.geojson"
HISTORY_INDEX = ROOT / "data" / "physics" / "history_current" / "index.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read JSON: {exc}")


@router.get("/health")
def health():
    summary_exists = SUMMARY_FILE.exists()
    png_exists = DASHBOARD_PNG.exists()
    geojson_exists = GEOJSON_FILE.exists()

    status = "ready" if summary_exists else "missing"

    payload: dict[str, Any] = {
        "api": "current_analysis_health",
        "ok": summary_exists,
        "status": status,
        "summary_file": str(SUMMARY_FILE),
        "summary_file_exists": summary_exists,
        "dashboard_png": str(DASHBOARD_PNG),
        "dashboard_png_exists": png_exists,
        "geojson_file": str(GEOJSON_FILE),
        "geojson_file_exists": geojson_exists,
    }

    if summary_exists:
        data = read_json(SUMMARY_FILE)
        payload["snapshot_date"] = data.get("snapshot_date")
        payload["dominant_direction_label"] = data.get("dominant_direction_label")
        payload["mean_speed_ms"] = data.get("speed_stats", {}).get("mean")
        payload["max_speed_ms"] = data.get("speed_stats", {}).get("max")

    return payload


@router.get("/today")
def today():
    data = read_json(SUMMARY_FILE)
    return JSONResponse(
        data,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )


@router.get("/summary")
def summary():
    data = read_json(SUMMARY_FILE)

    return {
        "module": data.get("module"),
        "version": data.get("version"),
        "status": data.get("status"),
        "snapshot_date": data.get("snapshot_date"),
        "source": data.get("source"),
        "domain": data.get("domain"),
        "depth_m": data.get("depth_m"),
        "speed_stats": data.get("speed_stats"),
        "vector_mean": data.get("vector_mean"),
        "dominant_direction_deg": data.get("dominant_direction_deg"),
        "dominant_direction_label": data.get("dominant_direction_label"),
        "classification": data.get("classification"),
        "hotspot": data.get("hotspot"),
        "narrative": data.get("narrative"),
        "outputs": data.get("outputs"),
    }


@router.get("/geojson")
def geojson():
    data = read_json(GEOJSON_FILE)
    return JSONResponse(
        data,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )

@router.head("/dashboard.png")
@router.get("/dashboard.png")
def dashboard_png():
    if not DASHBOARD_PNG.exists():
        raise HTTPException(status_code=404, detail=f"Dashboard PNG not found: {DASHBOARD_PNG}")

    return FileResponse(
        DASHBOARD_PNG,
        media_type="image/png",
        filename="current_analysis_dashboard_today.png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )
@router.head("/map.png")
@router.get("/map.png")
def current_map_png():
    if not CURRENT_MAP_PNG.exists():
        raise HTTPException(status_code=404, detail=f"Current map PNG not found: {CURRENT_MAP_PNG}")

    return FileResponse(
        CURRENT_MAP_PNG,
        media_type="image/png",
        filename="current_surface_map_today.png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )

@router.get("/history")
def history():
    if not HISTORY_INDEX.exists():
        return {
            "module": "nelaya_ai_current_analysis_history_index",
            "count": 0,
            "entries": [],
        }

    return read_json(HISTORY_INDEX)


@router.head("/dashboard/{date}.png")
@router.get("/dashboard/{date}.png")
def by_date(date: str):
    # date format: YYYY-MM-DD
    parts = date.split("-")
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")

    y, m, d = parts
    path = (
        ROOT
        / "data"
        / "physics"
        / "history_current"
        / y
        / m
        / d
        / f"current_analysis_{date}.json"
    )

    return read_json(path)


@router.get("/dashboard/{date}.png")
def dashboard_by_date(date: str):
    parts = date.split("-")
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")

    y, m, d = parts
    path = (
        ROOT
        / "data"
        / "physics"
        / "history_current"
        / y
        / m
        / d
        / f"current_dashboard_{date}.png"
    )

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Dashboard PNG not found for {date}")

    return FileResponse(
        path,
        media_type="image/png",
        filename=f"current_dashboard_{date}.png",
        headers={
            "Cache-Control": "no-store",
        },
    )
