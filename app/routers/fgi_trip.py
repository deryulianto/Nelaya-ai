from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.fgi_trip_metrics import enrich_trip_metrics

router = APIRouter(prefix="/api/v1/fgi", tags=["fgi-trip"])

DATA_PATH = Path("data/fgi_trip")
DATA_PATH.mkdir(parents=True, exist_ok=True)


class TripPoint(BaseModel):
    lat: float
    lon: float
    ts: str
    accuracy_m: Optional[float] = None
    speed_mps: Optional[float] = None
    heading_deg: Optional[float] = None

class FGIContext(BaseModel):
    from_plan: bool = False
    plan_date: Optional[str] = None
    port_name: Optional[str] = None
    candidate_rank: Optional[int] = None
    fgi_score: Optional[float] = None
    trip_success_probability: Optional[float] = None
    recommended_lat: Optional[float] = None
    recommended_lon: Optional[float] = None
    model_version: Optional[str] = None

class TripSession(BaseModel):
    trip_id: str
    port_name: str
    vessel_type: str
    start_time: str
    points: list[TripPoint] = Field(default_factory=list)
    interval_min: Optional[int] = None
    fgi_context: Optional[FGIContext] = None


class TripPointPayload(BaseModel):
    trip_id: str
    point: TripPoint


class TripEnd(BaseModel):
    trip_id: str
    end_time: str
    trip_success: int = Field(..., ge=0, le=1)
    catch_kg: Optional[float] = None
    fuel_used_l: Optional[float] = None
    notes: Optional[str] = None


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _file(trip_id: str) -> Path:
    safe = "".join(c for c in trip_id if c.isalnum() or c in "-_")
    return DATA_PATH / f"{safe}.json"


def _read_trip(trip_id: str) -> dict:
    f = _file(trip_id)
    if not f.exists():
        raise HTTPException(status_code=404, detail="Trip tidak ditemukan")
    return json.loads(f.read_text(encoding="utf-8"))


def _write_trip(trip_id: str, data: dict) -> None:
    f = _file(trip_id)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@router.post("/trip/start")
def start_trip(payload: TripSession):
    f = _file(payload.trip_id)
    if f.exists():
        raise HTTPException(status_code=409, detail="Trip ID sudah ada")

    data = payload.model_dump()
    data["status"] = "active"
    data["created_at"] = now_iso()
    data["updated_at"] = now_iso()

    _write_trip(payload.trip_id, data)
    return {"status": "started", "trip_id": payload.trip_id}


@router.post("/trip/point")
def add_point(payload: TripPointPayload):
    data = _read_trip(payload.trip_id)

    if data.get("status") != "active":
        raise HTTPException(status_code=400, detail="Trip sudah tidak aktif")

    data.setdefault("points", [])
    data["points"].append(payload.point.model_dump())
    data["updated_at"] = now_iso()

    _write_trip(payload.trip_id, data)
    return {
        "status": "point_added",
        "trip_id": payload.trip_id,
        "points_count": len(data["points"]),
    }


@router.post("/trip/end")
def end_trip(payload: TripEnd):
    data = _read_trip(payload.trip_id)

    data["status"] = "completed"
    data["end"] = payload.model_dump()
    data["updated_at"] = now_iso()
    data["metrics"] = enrich_trip_metrics(data)

    _write_trip(payload.trip_id, data)
    return {
        "status": "trip_completed",
        "trip_id": payload.trip_id,
        "metrics": data["metrics"],
    }


@router.get("/trip-calibration/bias")
def trip_calibration_bias():
    trips = []
    for f in DATA_PATH.glob("trip-*.json"):
        try:
            trips.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue

    completed = [
        t for t in trips
        if t.get("status") == "completed"
        and t.get("end")
        and (t.get("fgi_context") or {}).get("from_plan") is True
    ]

    counts = {
        "total_fgi_completed": len(completed),
        "model_overestimate": 0,
        "model_underestimate": 0,
        "model_consistent_or_uncertain": 0,
        "no_fgi_calibration_context": 0,
    }

    samples = []

    for t in completed:
        ctx = t.get("fgi_context") or {}
        end = t.get("end") or {}
        metrics = t.get("metrics") or enrich_trip_metrics(t)

        p = ctx.get("trip_success_probability")
        success = end.get("trip_success")

        if p is None or success is None:
            label = "no_fgi_calibration_context"
        else:
            p = float(p)
            success = int(success)

            if success == 1 and p < 0.5:
                label = "model_underestimate"
            elif success == 0 and p > 0.65:
                label = "model_overestimate"
            else:
                label = "model_consistent_or_uncertain"

        counts[label] = counts.get(label, 0) + 1

        samples.append({
            "trip_id": t.get("trip_id"),
            "port_name": t.get("port_name"),
            "trip_success_probability": ctx.get("trip_success_probability"),
            "actual_success": end.get("trip_success"),
            "fgi_score": ctx.get("fgi_score"),
            "bias_label": label,
            "data_quality": metrics.get("data_quality"),
            "movement": metrics.get("movement"),
            "distance_km": metrics.get("distance_km"),
            "model_version": ctx.get("model_version"),
        })

    total = max(counts["total_fgi_completed"], 1)

    return {
        "counts": counts,
        "rates": {
            "overestimate_rate": round(counts["model_overestimate"] / total, 4),
            "underestimate_rate": round(counts["model_underestimate"] / total, 4),
            "consistent_or_uncertain_rate": round(counts["model_consistent_or_uncertain"] / total, 4),
        },
        "samples": samples[-20:],
        "interpretation": (
            "Data masih tahap awal; bias detection baru stabil setelah jumlah trip FGI selesai bertambah."
            if counts["total_fgi_completed"] < 10
            else "Data mulai cukup untuk membaca kecenderungan awal bias model."
        ),
    }