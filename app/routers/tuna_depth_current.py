from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(
    prefix="/api/v1/tuna-depth-current",
    tags=["tuna-depth-current"],
)

ROOT = Path(__file__).resolve().parents[2]

SUMMARY_FILE = ROOT / "data" / "physics" / "tuna_depth_current_today.json"
DASHBOARD_PNG = ROOT / "data" / "physics" / "tuna_depth_current_dashboard_today.png"
GEOJSON_FILE = ROOT / "data" / "physics" / "tuna_depth_current_latest.geojson"
HISTORY_DIR = ROOT / "data" / "physics" / "history_tuna_depth_current"
HISTORY_INDEX = HISTORY_DIR / "index.json"


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
        "api": "tuna_depth_current_health",
        "ok": summary_exists,
        "status": "ready" if summary_exists else "missing",
        "summary_file": str(SUMMARY_FILE),
        "summary_file_exists": summary_exists,
        "dashboard_png": str(DASHBOARD_PNG),
        "dashboard_png_exists": png_exists,
        "geojson_file": str(GEOJSON_FILE),
        "geojson_file_exists": geojson_exists,
        "scientific_position": (
            "Probabilistic current-depth habitat corridor signal, "
            "not a fish-location claim."
        ),
    }

    if summary_exists:
        data = read_json(SUMMARY_FILE)
        payload["version"] = data.get("version")
        payload["snapshot_date"] = data.get("snapshot_date")
        payload["status"] = data.get("status")
        payload["source_file"] = data.get("source_file")
        payload["composite_mean_score"] = (
            data.get("composite", {}).get("score_stats", {}).get("mean")
        )
        payload["composite_max_score"] = (
            data.get("composite", {}).get("score_stats", {}).get("max")
        )
        payload["hotspot"] = data.get("composite", {}).get("hotspot")
        payload["confidence_breakdown"] = data.get("confidence_breakdown")
        payload["thermal_diagnostics"] = data.get("thermal_diagnostics")
        payload["ssh_front_diagnostics"] = data.get("ssh_front_diagnostics")
        payload["safety_gate_diagnostics"] = data.get("safety_gate_diagnostics")
        payload["audit"] = data.get("audit")

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
            "domain": data.get("domain"),
            "target_depths": data.get("target_depths"),
            "audit": data.get("audit"),
            "vertical_diagnostics": data.get("vertical_diagnostics"),
            "thermal_diagnostics": data.get("thermal_diagnostics"),
            "ssh_front_diagnostics": data.get("ssh_front_diagnostics"),
            "safety_gate_diagnostics": data.get("safety_gate_diagnostics"),
            "confidence_breakdown": data.get("confidence_breakdown"),
            "clustered_candidates": data.get("clustered_candidates"),
            "layers": data.get("layers"),
            "species": data.get("species"),
            "composite": data.get("composite"),
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
        filename="tuna_depth_current_latest.geojson",
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
            detail=f"Tuna depth dashboard PNG not found: {DASHBOARD_PNG}",
        )

    return FileResponse(
        DASHBOARD_PNG,
        media_type="image/png",
        filename="tuna_depth_current_dashboard_today.png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )


@router.get("/history")
def history():
    if HISTORY_INDEX.exists():
        return read_json(HISTORY_INDEX)

    # fallback: scan history folders if index is not built yet
    entries: list[dict[str, Any]] = []

    for path in sorted(HISTORY_DIR.glob("20??/??/??/tuna_depth_current_20??-??-??.json")):
        try:
            data = read_json(path)
            date = data.get("snapshot_date")
            entries.append(
                {
                    "snapshot_date": date,
                    "summary_json": str(path),
                    "dashboard_png": str(
                        path.with_name(f"tuna_depth_current_dashboard_{date}.png")
                    )
                    if date
                    else None,
                    "version": data.get("version"),
                    "composite_mean_score": (
                        data.get("composite", {}).get("score_stats", {}).get("mean")
                    ),
                    "composite_max_score": (
                        data.get("composite", {}).get("score_stats", {}).get("max")
                    ),
                    "hotspot": data.get("composite", {}).get("hotspot"),
                }
            )
        except Exception:
            continue

    return {
        "module": "nelaya_ai_tuna_depth_current_history_index",
        "count": len(entries),
        "entries": entries,
    }


@router.get("/by-date/{date}")
def by_date(date: str):
    parts = date.split("-")
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")

    y, m, d = parts
    path = HISTORY_DIR / y / m / d / f"tuna_depth_current_{date}.json"

    return read_json(path)


@router.head("/dashboard/{date}.png")
@router.get("/dashboard/{date}.png")
def dashboard_by_date(date: str):
    parts = date.split("-")
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")

    y, m, d = parts
    path = HISTORY_DIR / y / m / d / f"tuna_depth_current_dashboard_{date}.png"

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Tuna depth dashboard PNG not found for {date}",
        )

    return FileResponse(
        path,
        media_type="image/png",
        filename=f"tuna_depth_current_dashboard_{date}.png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        },
    )
