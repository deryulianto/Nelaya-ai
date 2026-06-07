from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json

from fastapi import APIRouter, HTTPException

from app.services.data_health_service import check_netcdf_file


router = APIRouter(
    prefix="/api/v1/ocean/health",
    tags=["ocean-health"],
)


def _candidate_paths(snapshot_date: str):
    year = snapshot_date[:4]
    month = snapshot_date[5:7]

    base = Path("data/raw/aceh_simeulue")

    return [
        {
            "kind": "chl_nrt",
            "path": base / "chl_nrt" / year / month / f"chl_nrt_aceh_{snapshot_date}.nc",
        },
        {
            "kind": "sst_nrt",
            "path": base / "sst_nrt" / year / month / f"sst_nrt_aceh_{snapshot_date}.nc",
        },
        {
            "kind": "wind_nrt",
            "path": base / "wind_nrt" / year / month / f"wind_nrt_aceh_{snapshot_date}.nc",
        },
        {
            "kind": "wave_anfc",
            "path": base / "wave_anfc" / year / month / f"wave_anfc_aceh_{snapshot_date}.nc",
        },
        {
            "kind": "ssh_anfc",
            "path": base / "ssh_anfc" / year / month / f"ssh_anfc_aceh_{snapshot_date}.nc",
        },
        {
            "kind": "sal_anfc",
            "path": base / "sal_anfc" / year / month / f"sal_anfc_aceh_{snapshot_date}.nc",
        },
    ]


def _build_health(snapshot_date: str):
    checks = []

    for item in _candidate_paths(snapshot_date):
        checks.append(
            check_netcdf_file(
                kind=item["kind"],
                file_path=str(item["path"]),
                snapshot_date=snapshot_date,
            )
        )

    available = [c for c in checks if c.get("status") == "available"]
    missing = [c for c in checks if c.get("status") == "missing"]
    stale = [c for c in checks if c.get("status") == "stale"]
    invalid = [c for c in checks if c.get("status") == "invalid"]
    corrupt = [c for c in checks if c.get("status") == "corrupt"]
    partial = [c for c in checks if c.get("status") == "partial"]

    problematic = [
        c for c in checks
        if c.get("status") not in ["available", "missing"]
    ]

    if len(available) == len(checks):
        overall_status = "healthy"
    elif len(available) > 0:
        overall_status = "partial"
    elif len(stale) > 0 or len(invalid) > 0 or len(partial) > 0 or len(corrupt) > 0:
        overall_status = "problematic"
    else:
        overall_status = "unavailable"

    output = {
        "module": "ocean_data_health",
        "version": "0.1.2",
        "snapshot_date": snapshot_date,
        "summary": {
            "total_checked": len(checks),
            "available_count": len(available),
            "missing_count": len(missing),
            "problematic_count": len(problematic),
            "stale_count": len(stale),
            "invalid_count": len(invalid),
            "corrupt_count": len(corrupt),
            "partial_count": len(partial),
            "overall_status": overall_status,
        },
        "checks": checks,
    }

    return output


def _write_cache(output: dict, name: str):
    out_path = Path("data/health") / name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")


@router.get("/date/{snapshot_date}")
def ocean_health_by_date(snapshot_date: str):
    try:
        datetime.strptime(snapshot_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Format tanggal harus YYYY-MM-DD, contoh: 2026-06-05",
        )

    return _build_health(snapshot_date)


@router.get("/today")
def ocean_health_today():
    snapshot_date = date.today().isoformat()
    output = _build_health(snapshot_date)
    _write_cache(output, "ocean_data_health_today.json")
    return output


@router.get("/latest")
def ocean_health_latest(lookback_days: int = 7, min_available_layers: int = 1):
    """
    Cari snapshot terbaru yang punya minimal sejumlah layer available.
    Default min_available_layers=1 agar tetap bisa membaca indikasi terbatas.
    Confidence Layer nanti yang menentukan kuat/lemahnya pembacaan.
    """

    if lookback_days < 1:
        lookback_days = 1

    if lookback_days > 30:
        lookback_days = 30

    if min_available_layers < 1:
        min_available_layers = 1

    today = date.today()
    candidates = []

    for i in range(lookback_days):
        snapshot_date = (today - timedelta(days=i)).isoformat()
        output = _build_health(snapshot_date)

        candidates.append({
            "snapshot_date": output["snapshot_date"],
            "available_count": output["summary"]["available_count"],
            "missing_count": output["summary"]["missing_count"],
            "problematic_count": output["summary"]["problematic_count"],
            "stale_count": output["summary"]["stale_count"],
            "invalid_count": output["summary"]["invalid_count"],
            "overall_status": output["summary"]["overall_status"],
        })

        if output["summary"]["available_count"] >= min_available_layers:
            output["latest_search"] = {
                "resolved_snapshot_date": snapshot_date,
                "lookback_days": lookback_days,
                "min_available_layers": min_available_layers,
                "days_behind_today": i,
                "message": "Snapshot terbaru dengan layer available ditemukan.",
            }

            _write_cache(output, "ocean_data_health_latest.json")
            return output

    return {
        "module": "ocean_data_health",
        "version": "0.1.2",
        "summary": {
            "overall_status": "unavailable",
            "message": f"Tidak ditemukan snapshot dengan minimal {min_available_layers} layer available dalam {lookback_days} hari terakhir.",
        },
        "candidates": candidates,
    }
