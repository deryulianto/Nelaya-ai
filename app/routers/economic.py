from __future__ import annotations

import json
import urllib.request
import math
import xarray as xr
from pathlib import Path
from fastapi import APIRouter, Query

from app.services.economic_service import (
    estimate_fuel_liter,
    calculate_economic_score,
    risk_to_score,
    infer_risk_level,
    decision_label_from_score,
    build_explanation,
    advice_for_fishermen,
    economy_match,
)

router = APIRouter()

OUT = Path("data/economics/economic_today.json")
FEEDBACK = Path("data/field_feedback/field_feedback_today.json")
PORTS = Path("data/static/ports_aceh.json")
PHYSICS = Path(
    "data/physics/fgi_physics_support_today.json"
)
PHYSICS_NC = Path("data/physics/fgi_physics_support_today.nc")


def load_signals_today() -> dict:
    signals_url = "http://127.0.0.1:8001/api/v1/signals/today"

    try:
        with urllib.request.urlopen(signals_url, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}

def load_field_feedback(port: str) -> dict:
    if not FEEDBACK.exists():
        return {
            "available": False,
            "message": "Belum ada data validasi lapangan untuk pelabuhan ini.",
        }

    try:
        data = json.loads(FEEDBACK.read_text(encoding="utf-8"))
    except Exception:
        return {
            "available": False,
            "message": "Data validasi lapangan belum dapat dibaca.",
        }

    records = data.get("records", [])
    matched = [
        r for r in records
        if str(r.get("port", "")).lower() == port.lower()
    ]

    if not matched:
        return {
            "available": False,
            "message": "Belum ada data validasi lapangan untuk pelabuhan ini.",
        }

    last = matched[-1]

@router.get("/economic/ports")
def economic_ports():
    ports = load_ports()
    return {
        "version": "1.0",
        "count": len(ports),
        "ports": ports,
    }

    return {
        "available": True,
        "last_trip_date": last.get("date"),
        "last_trip_catch_kg": last.get("catch_kg"),
        "last_trip_fuel_liter": last.get("fuel_liter"),
        "fish_type": last.get("fish_type"),
        "fisher_note": last.get("note"),
        "message": "Data validasi lapangan terakhir tersedia untuk pelabuhan ini.",
    }

def load_ports() -> list[dict]:
    try:
        return json.loads(PORTS.read_text(encoding="utf-8"))
    except Exception:
        return []

def load_physics_cells():
    try:
        data = json.loads(PHYSICS.read_text(encoding="utf-8"))
    except Exception:
        return []

    cells = []

    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                if (
                    isinstance(item, dict)
                    and "lat" in item
                    and "lon" in item
                    and (
                        "fgi_physics_support_score" in item
                        or "fgi_physics_support_confidence_adjusted" in item
                    )
                ):
                    cells.append(item)
                else:
                    walk(item)

        elif isinstance(obj, dict):
            for value in obj.values():
                walk(value)

    walk(data)
    return cells

def nearest_cell(port_lat, port_lon):
    cells = load_physics_cells()

    if not cells or port_lat is None or port_lon is None:
        return None, None

    best = None
    best_d = 999999.0

    for c in cells:
        try:
            lat = float(c.get("lat"))
            lon = float(c.get("lon"))
            d = (float(port_lat) - lat) ** 2 + (float(port_lon) - lon) ** 2
        except Exception:
            continue

        if d < best_d:
            best_d = d
            best = c

    if best is None:
        return None, None

    return best, round(best_d ** 0.5, 4)

def spatial_confidence_from_distance(distance_deg: float | None) -> str:
    if distance_deg is None:
        return "tidak tersedia"

    if distance_deg <= 0.25:
        return "tinggi"

    if distance_deg <= 0.75:
        return "sedang"

    return "rendah"

def spatial_warning_message(
    confidence: str,
    source: str
) -> str | None:

    if source == "regional_estimate":
        return (
            "Estimasi ini masih bersifat regional karena "
            "cell fisika terdekat belum cukup dekat "
            "dengan pelabuhan."
        )

    if confidence == "sedang":
        return (
            "Estimasi menggunakan cell fisika yang "
            "cukup dekat, namun tetap memerlukan "
            "kehati-hatian interpretasi."
        )

    return None

def build_rank_summary(rankings: list[dict]) -> str:

    if not rankings:
        return "Belum tersedia data pelabuhan."

    total = len(rankings)

    local_count = sum(
        1 for r in rankings
        if r.get("fgi_source") == "netcdf_local_grid"
    )

    regional_count = sum(
        1 for r in rankings
        if r.get("fgi_source") == "regional_estimate"
    )

    risk_levels = [
        r.get("risk_level")
        for r in rankings
        if r.get("risk_level")
    ]

    dominant_risk = (
        max(set(risk_levels), key=risk_levels.count)
        if risk_levels
        else "tidak tersedia"
    )

    top = rankings[0]

    return (
        f"Hari ini {local_count} dari {total} pelabuhan sudah memiliki "
        f"estimasi lokal berbasis grid NetCDF, sementara {regional_count} "
        f"pelabuhan masih memakai estimasi regional. Risiko umum terbaca "
        f"{dominant_risk}. Pelabuhan dengan ranking tertinggi saat ini "
        f"{top['port']} dengan ranking score {top['ranking_score']:.1f}. "
        f"Gunakan ranking ini sebagai panduan awal bersama validasi nelayan "
        f"dan pemantauan cuaca terbaru."
    )

def local_physics_from_nc(
    port_lat: float,
    port_lon: float,
    radius_deg: float = 0.35,
    adaptive: bool = True,
) -> dict:
    if not PHYSICS_NC.exists():
        return {
            "available": False,
            "message": "NetCDF physics grid belum tersedia.",
        }

    radii = [radius_deg, 0.5, 0.75, 1.0, 1.5] if adaptive else [radius_deg]

    try:
        ds = xr.open_dataset(PHYSICS_NC)

        for r in radii:
            sub = ds.sel(
                lat=slice(port_lat - r, port_lat + r),
                lon=slice(port_lon - r, port_lon + r),
            )

            valid = sub["fgi_physics_support_score"].where(
                sub["fgi_physics_support_score"].notnull()
            )

            cell_count = int(valid.count().values)

            if cell_count == 0:
                continue

            fgi_local = float(
                sub["fgi_physics_support_score"]
                .mean(skipna=True)
                .values
            )

            operational = float(
                sub["operational_score"]
                .mean(skipna=True)
                .values
            )

            wave = float(
                sub["wave_height_m"]
                .mean(skipna=True)
                .values
            )

            wind = float(
                sub["wind_speed_ms"]
                .mean(skipna=True)
                .values
            )

            current = float(
                sub["current_speed_ms"]
                .mean(skipna=True)
                .values
            )

            depth = float(
                sub["depth_m"]
                .mean(skipna=True)
                .values
            )

            confidence = float(
                sub["physics_confidence"]
                .mean(skipna=True)
                .values
            )

            return {
                "available": True,
                "radius_deg": r,
                "cell_count": cell_count,
                "fgi_local": fgi_local,
                "operational_score": operational,
                "wave_m": wave,
                "wind_ms": wind,
                "current_ms": current,
                "depth_m": depth,
                "physics_confidence": confidence,
                "source": "netcdf_local_grid_adaptive",
            }

        return {
            "available": False,
            "cell_count": 0,
            "message": "Tidak ada grid laut valid sampai radius maksimum.",
        }

    except Exception as e:
        return {
            "available": False,
            "message": str(e),
        }

def ranking_confidence_label(
    fgi_source: str,
    cell_count: int | None,
) -> str:
    if fgi_source == "regional_estimate":
        return "rendah"

    if fgi_source == "netcdf_local_grid":
        if cell_count is not None and cell_count >= 5:
            return "sedang"
        return "rendah-sedang"

    return "tidak tersedia"

def port_advice_message(
    ranking_confidence: str,
    fgi_source: str,
    risk_level: str,
) -> str:
    if fgi_source == "regional_estimate":
        return (
            "Gunakan sebagai indikasi awal regional. "
            "Data lokal pelabuhan belum cukup kuat, sehingga perlu "
            "validasi nelayan dan pemantauan cuaca sebelum keputusan."
        )

    if risk_level == "tinggi":
        return (
            "Data lokal tersedia, tetapi risiko laut relatif tinggi. "
            "Keselamatan kapal dan awak perlu menjadi pertimbangan utama."
        )

    if ranking_confidence == "sedang":
        return (
            "Data lokal pelabuhan tersedia dengan keyakinan sedang. "
            "Rekomendasi dapat dipertimbangkan bersama pengalaman nelayan "
            "dan kondisi cuaca terbaru."
        )

    return (
        "Data lokal mulai tersedia, tetapi keyakinannya masih terbatas. "
        "Gunakan sebagai pembanding awal dan tetap utamakan validasi lapangan."
    )

def ranking_note_message(
    fgi_source: str,
    ranking_confidence: str,
    ranking_score: float,
) -> str:
    if fgi_source == "regional_estimate":
        return (
            "Ranking ini masih berbasis estimasi regional, sehingga belum "
            "boleh dibaca sebagai keunggulan lokal pelabuhan."
        )

    if ranking_confidence in ["rendah", "rendah-sedang"]:
        return (
            "Ranking ini sudah memakai data lokal, tetapi jumlah cell valid "
            "masih terbatas sehingga perlu validasi lapangan."
        )

    return (
        "Ranking ini memakai data lokal dengan keyakinan sedang dan dapat "
        "dipakai sebagai indikasi awal yang lebih kuat."
    )

def build_coverage_summary(rankings: list[dict]) -> dict:
    total = len(rankings)

    local_grid_ports = sum(
        1 for r in rankings
        if r.get("fgi_source") == "netcdf_local_grid"
    )

    regional_ports = sum(
        1 for r in rankings
        if r.get("fgi_source") == "regional_estimate"
    )

    medium_confidence_ports = sum(
        1 for r in rankings
        if r.get("ranking_confidence") == "sedang"
    )

    low_medium_confidence_ports = sum(
        1 for r in rankings
        if r.get("ranking_confidence") == "rendah-sedang"
    )

    low_confidence_ports = sum(
        1 for r in rankings
        if r.get("ranking_confidence") == "rendah"
    )

    return {
        "total_ports": total,
        "local_grid_ports": local_grid_ports,
        "regional_ports": regional_ports,
        "medium_confidence_ports": medium_confidence_ports,
        "low_medium_confidence_ports": low_medium_confidence_ports,
        "low_confidence_ports": low_confidence_ports,
    }

def readiness_status_from_coverage(coverage: dict) -> str:
    total = coverage.get("total_ports", 0)
    local = coverage.get("local_grid_ports", 0)
    low = coverage.get("low_confidence_ports", 0)

    if total == 0:
        return "limited"

    local_ratio = local / total
    low_ratio = low / total

    if local_ratio >= 0.75 and low_ratio <= 0.25:
        return "ready"

    if local_ratio >= 0.5:
        return "caution"

    return "limited"


@router.get("/economic/ports/rank")
def economic_ports_rank():
    ports = load_ports()
    rankings = []

    distance_km = 18.5
    fuel_price_idr = 10000

    for p in ports:
        local = local_physics_from_nc(
            port_lat=p.get("lat"),
            port_lon=p.get("lon"),
            radius_deg=0.35,
        )

        if local.get("available"):
            local_fgi = local.get("operational_score") or local.get("fgi_local") or 0.5
            wave_m = local.get("wave_m")
            wind_ms = local.get("wind_ms")
            current_ms = local.get("current_ms")
            fgi_source = "netcdf_local_grid"
            spatial_confidence = "tinggi"
            spatial_warning = None
        else:
            signals = load_signals_today()
            local_fgi = (
                signals.get("fgi_current_aware")
                or signals.get("fgi")
                or 0.5
            )
            wave_m = signals.get("wave_m")
            wind_ms = signals.get("wind_ms")
            current_ms = signals.get("current_ms")
            fgi_source = "regional_estimate"
            spatial_confidence = "rendah"
            spatial_warning = (
                "Estimasi ini masih bersifat regional karena grid lokal "
                "NetCDF belum tersedia untuk pelabuhan ini."
            )

        risk_level = infer_risk_level(wave_m, wind_ms)
        risk_score = risk_to_score(risk_level)

        fuel_liter = estimate_fuel_liter(
            distance_km=distance_km,
            km_per_liter=1.4,
        )

        estimated_trip_cost_idr = int(round(fuel_liter * fuel_price_idr))

        fuel_efficiency_score = max(
            0.0,
            min(1.0, 1.0 - (fuel_liter / 40.0)),
        )

        distance_score = max(
            0.0,
            min(1.0, 1.0 - (distance_km / 60.0)),
        )

        economic_score = calculate_economic_score(
            fgi_probability=local_fgi,
            fuel_efficiency_score=fuel_efficiency_score,
            risk_score=risk_score,
            distance_score=distance_score,
        )

        decision_label = decision_label_from_score(economic_score)
        confidence_penalty = 0.0

        if fgi_source == "regional_estimate":
            confidence_penalty = 8.0

        ranking_score = round(
            max(0.0, economic_score - confidence_penalty),
            1,
        )
        
        cell_count = (
            local.get("cell_count")
            if local.get("available")
            else None
        )

        ranking_confidence = ranking_confidence_label(
            fgi_source=fgi_source,
            cell_count=cell_count,
        )

        port_advice = port_advice_message(
            ranking_confidence=ranking_confidence,
            fgi_source=fgi_source,
            risk_level=risk_level,
        )

        ranking_note = ranking_note_message(
           fgi_source=fgi_source,
           ranking_confidence=ranking_confidence,
           ranking_score=ranking_score,
        )

        rankings.append({
            "port_id": p.get("id"),
            "port": p.get("name"),
            "lat": p.get("lat"),
            "lon": p.get("lon"),
            "economic_score": economic_score,
            "ranking_score": ranking_score,
            "confidence_penalty": confidence_penalty,
            "local_fgi": local_fgi,
            "fgi_source": fgi_source,
            "risk_level": risk_level,
            "decision_label": decision_label,
            "distance_km": distance_km,
            "fuel_estimate_liter": fuel_liter,
            "fuel_price_idr": fuel_price_idr,
            "estimated_trip_cost_idr": estimated_trip_cost_idr,
            "spatial_confidence": spatial_confidence,
            "spatial_warning": spatial_warning,
            "local_physics": local if local.get("available") else None,
            "local_opportunity_score": local_fgi,
            "raw_fgi_physics_support": local.get("fgi_local") if local.get("available") else None,
            "ranking_confidence": ranking_confidence,
            "port_advice": port_advice,
            "ranking_note": ranking_note,
            "source": {
                "wave_m": wave_m,
                "wind_ms": wind_ms,
                "current_ms": current_ms,
            },
        })

    rankings = sorted(
        rankings,
        key=lambda x: x["ranking_score"],
        reverse=True,
    )

    summary = build_rank_summary(rankings)
    coverage = build_coverage_summary(rankings)
    readiness_status = readiness_status_from_coverage(coverage)

    return {
        "version": "2.9",
        "count": len(rankings),
        "summary": summary,
        "coverage": coverage,
        "readiness_status": readiness_status,
        "ports": rankings,
    }

@router.get("/economic/today")
def economic_today(port: str = Query("tpi_lampulo")):
    signals = load_signals_today()

    ports = load_ports()
    selected_port = next(
        (
            p for p in ports
            if p.get("id") == port or p.get("name") == port
        ),
        ports[0] if ports else {
            "id": "unknown",
            "name": "Unknown Port",
            "lat": None,
            "lon": None,
        },
    )

    port_id = selected_port.get("id")
    port_name = selected_port.get("name")
    port_lat = selected_port.get("lat")
    port_lon = selected_port.get("lon")

    fgi_probability = (
        signals.get("fgi_current_aware")
        or signals.get("fgi")
        or 0.5
    )

    wave_m = signals.get("wave_m")
    wind_ms = signals.get("wind_ms")
    current_ms = signals.get("current_ms")

    distance_km = 18.5
    fuel_price_idr = 10000

    risk_level = infer_risk_level(wave_m, wind_ms)

    fuel_liter = estimate_fuel_liter(distance_km, km_per_liter=1.4)
    estimated_trip_cost_idr = int(round(fuel_liter * fuel_price_idr))

    fuel_efficiency_score = max(0.0, min(1.0, 1.0 - (fuel_liter / 40.0)))
    distance_score = max(0.0, min(1.0, 1.0 - (distance_km / 60.0)))
    risk_score = risk_to_score(risk_level)

    economic_score = calculate_economic_score(
        fgi_probability=fgi_probability,
        fuel_efficiency_score=fuel_efficiency_score,
        risk_score=risk_score,
        distance_score=distance_score,
    )

    decision_label = decision_label_from_score(economic_score)

    advice = advice_for_fishermen(
        decision_label=decision_label,
        risk_level=risk_level,
        economic_score=economic_score,
    )

    why = build_explanation(
        fgi_probability=fgi_probability,
        risk_level=risk_level,
        fuel_liter=fuel_liter,
        estimated_trip_cost_idr=estimated_trip_cost_idr,
        distance_km=distance_km,
    )

    field_feedback = load_field_feedback(port_name)

    match_result = economy_match(
        catch_kg=field_feedback.get("last_trip_catch_kg"),
        actual_fuel_liter=field_feedback.get("last_trip_fuel_liter"),
        estimated_fuel_liter=fuel_liter,
    )

    result = {
        "version": "1.0",
        "module": "NELAYA-AI Economic Intelligence Layer",
        "port_id": port_id,
        "port": port_name,
        "lat": port_lat,
        "lon": port_lon,
        "economic_score": economic_score,
        "fgi_probability": fgi_probability,
        "distance_km": distance_km,
        "fuel_estimate_liter": fuel_liter,
        "fuel_price_idr": fuel_price_idr,
        "estimated_trip_cost_idr": estimated_trip_cost_idr,
        "risk_level": risk_level,
        "decision_label": decision_label,
        "advice_for_fishermen": advice,
        "why": why,
        "field_feedback": field_feedback,
        "economy_match": match_result,
        "local_fgi":local_fgi,
        "nearest_depth_m":
            cell.get(
                "depth_m"
            )
            if cell
            else None, 
        "source": {
            "signals_endpoint": "/api/v1/signals/today",
            "date_utc": signals.get("date_utc"),
            "generated_at": signals.get("generated_at"),
            "fgi": signals.get("fgi"),
            "fgi_current_aware": signals.get("fgi_current_aware"),
            "wave_m": wave_m,
            "wind_ms": wind_ms,
            "current_ms": current_ms,
        },
        "message": (
            "Rekomendasi ini membaca peluang ekonomi perjalanan berdasarkan "
            "FGI aktual dari sinyal harian NELAYA-AI, estimasi BBM, jarak, "
            "dan risiko laut. Ini bukan janji hasil tangkapan, tetapi alat "
            "bantu keputusan awal bagi nelayan."
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return result