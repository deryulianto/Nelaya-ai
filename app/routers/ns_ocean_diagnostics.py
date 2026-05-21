from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(
    prefix="/api/v1/ns-ocean-diagnostics",
    tags=["ns-ocean-diagnostics"],
)

ROOT = Path(__file__).resolve().parents[2]

SUMMARY_FILE = ROOT / "data" / "physics" / "ns_ocean_diagnostics_today.json"
DASHBOARD_PNG = ROOT / "data" / "physics" / "ns_ocean_diagnostics_dashboard_today.png"
GEOJSON_FILE = ROOT / "data" / "physics" / "ns_ocean_diagnostics_latest.geojson"
HISTORY_DIR = ROOT / "data" / "physics" / "history_ns_ocean_diagnostics"


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

    payload: dict[str, Any] = {
        "api": "ns_ocean_diagnostics_health",
        "ok": summary_exists,
        "status": "ready" if summary_exists else "missing",
        "summary_file": str(SUMMARY_FILE),
        "summary_file_exists": summary_exists,
        "dashboard_png": str(DASHBOARD_PNG),
        "dashboard_png_exists": png_exists,
        "geojson_file": str(GEOJSON_FILE),
        "geojson_file_exists": geojson_exists,
        "scientific_position": (
            "Navier–Stokes-informed diagnostics from current derivatives; "
            "not a full numerical Navier–Stokes solver."
        ),
    }

    if summary_exists:
        data = read_json(SUMMARY_FILE)
        payload["version"] = data.get("version")
        payload["snapshot_date"] = data.get("snapshot_date")
        payload["source_file"] = data.get("source_file")
        payload["diagnostic_terms"] = data.get("diagnostic_terms")
        payload["aggregate_mean_score"] = (
            data.get("aggregate", {}).get("score_stats", {}).get("mean")
        )
        payload["aggregate_max_score"] = (
            data.get("aggregate", {}).get("score_stats", {}).get("max")
        )
        payload["hotspot"] = data.get("aggregate", {}).get("hotspot")

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

    return JSONResponse(
        {
            "module": data.get("module"),
            "version": data.get("version"),
            "status": data.get("status"),
            "created_at": data.get("created_at"),
            "snapshot_date": data.get("snapshot_date"),
            "source_file": data.get("source_file"),
            "data_type": data.get("data_type"),
            "scientific_position": data.get("scientific_position"),
            "diagnostic_terms": data.get("diagnostic_terms"),
            "domain": data.get("domain"),
            "target_depths": data.get("target_depths"),
            "layers": data.get("layers"),
            "aggregate": data.get("aggregate"),
            "narrative": data.get("narrative"),
            "outputs": data.get("outputs"),
        },
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )


@router.get("/geojson")
def geojson():
    if not GEOJSON_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail=f"GeoJSON file not found: {GEOJSON_FILE}",
        )

    return FileResponse(
        GEOJSON_FILE,
        media_type="application/geo+json",
        filename="ns_ocean_diagnostics_latest.geojson",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )


@router.head("/dashboard.png")
@router.get("/dashboard.png")
def dashboard_png():
    if not DASHBOARD_PNG.exists():
        raise HTTPException(
            status_code=404,
            detail=f"NS ocean diagnostics dashboard PNG not found: {DASHBOARD_PNG}",
        )

    return FileResponse(
        DASHBOARD_PNG,
        media_type="image/png",
        filename="ns_ocean_diagnostics_dashboard_today.png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )


@router.get("/by-date/{date}")
def by_date(date: str):
    parts = date.split("-")
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")

    y, m, d = parts
    path = HISTORY_DIR / y / m / d / f"ns_ocean_diagnostics_{date}.json"

    return read_json(path)


@router.head("/dashboard/{date}.png")
@router.get("/dashboard/{date}.png")
def dashboard_by_date(date: str):
    parts = date.split("-")
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")

    y, m, d = parts
    path = HISTORY_DIR / y / m / d / f"ns_ocean_diagnostics_dashboard_{date}.png"

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"NS diagnostics dashboard PNG not found for {date}",
        )

    return FileResponse(
        path,
        media_type="image/png",
        filename=f"ns_ocean_diagnostics_dashboard_{date}.png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )
