from __future__ import annotations

from typing import Optional, Dict, Any
from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.field_validation_service import (
    save_feedback,
    list_feedback,
    validation_summary,
    local_patterns,
    init_db,
    export_feedback_csv,
    validation_dashboard,
    backup_database,
    get_ocean_context,
    ocean_context_analytics,
    relationship_analytics,
    list_ports,
)

router = APIRouter(prefix="/api/v1/field-feedback", tags=["Field Feedback"])


class FisherFeedbackPayload(BaseModel):
    tanggal: Optional[str] = Field(None, description="YYYY-MM-DD")
    nama_responden: Optional[str] = None
    pelabuhan: Optional[str] = None
    panglima_laot: Optional[str] = None

    lat: Optional[float] = None
    lon: Optional[float] = None

    alat_tangkap: Optional[str] = None
    jenis_ikan: Optional[str] = None
    hasil_kg: Optional[float] = None

    kondisi_laut: Optional[str] = None
    arus_nelayan: Optional[str] = None
    warna_air: Optional[str] = None
    cuaca: Optional[str] = None
    catatan_lokal: Optional[str] = None


@router.get("/health")
def health() -> Dict[str, Any]:
    init_db()
    return {
        "ok": True,
        "module": "NELAYA-AI Field Validation Database",
        "version": "0.1"
    }


@router.post("/submit")
def submit_feedback(payload: FisherFeedbackPayload) -> Dict[str, Any]:
    return save_feedback(payload.model_dump())


@router.get("/list")
def get_feedback(limit: int = 50):
    return {
        "items": list_feedback(limit=limit)
    }


@router.get("/summary")
def get_summary():
    return validation_summary()


@router.get("/patterns")
def get_patterns(limit: int = 20):
    return local_patterns(limit=limit)


@router.get("/dashboard")
def get_dashboard():
    return validation_dashboard()


@router.get("/export.csv")
def export_csv():
    csv_text = export_feedback_csv()
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=nelaya_ai_field_feedback.csv"
        },
    )


@router.post("/backup")
def create_backup():
    return backup_database()


@router.get("/ocean-context")
def ocean_context(lat: float | None = None, lon: float | None = None):
    return get_ocean_context(lat=lat, lon=lon)

@router.get("/ocean-analytics")
def get_ocean_analytics():
    return ocean_context_analytics()


@router.get("/relationship-analytics")
def get_relationship_analytics():
    return relationship_analytics()


@router.get("/ports")
def get_ports():
    return list_ports()
