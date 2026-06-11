from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter

from app.services.fgi_modifier import (
    compute_fgi_confidence,
    compute_fgi_final,
    compute_iod_modifier,
)
from app.services.insight_engine import build_daily_ocean_insight
from app.services.iod_service import load_iod_operational
from app.services.enso_service import load_enso_operational

router = APIRouter(prefix="/insight", tags=["insight"])


EARTH_JSON_CANDIDATES = [
    Path("data/earth_signals_today.json"),
    Path("data/earth/earth_signals_today.json"),
    Path("data/signals_today.json"),
]

FGI_JSON_CANDIDATES = [
    Path("data/fgi_today.json"),
    Path("data/fgi/fgi_today.json"),
    Path("data/earth/fgi_today.json"),
    Path("data/earth/fgi_core_today.json"),
]

FGI_ENDPOINT_CANDIDATES = [
    os.getenv("FGI_CORE_URL", "").strip(),
    "http://127.0.0.1:8001/api/v1/fgi/today",
    "http://127.0.0.1:8001/api/v1/fgi/score",
    "http://127.0.0.1:8001/fgi/today",
    "http://127.0.0.1:8001/fgi/score",
]


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def load_earth_today() -> dict[str, Any] | None:
    for path in EARTH_JSON_CANDIDATES:
        data = load_json_if_exists(path)
        if isinstance(data, dict):
            return data
    return None


def pick_metric(payload: dict[str, Any], *keys: str) -> float | None:
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}

    for key in keys:
        # 1) top-level
        value = payload.get(key)

        # 2) metrics[key]
        if value is None:
            value = metrics.get(key)

        # 3) metrics[key] mungkin dict {"value": ...}
        if isinstance(value, dict):
            value = value.get("value")

        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue

    return None


def extract_core_fgi(payload: dict[str, Any] | None) -> float | None:
    if not isinstance(payload, dict):
        return None

    # pola umum langsung
    for key in ("fgi_core", "core_fgi", "core", "score", "fgi"):
        value = payload.get(key)
        if isinstance(value, dict):
            for subkey in ("value", "score"):
                subval = value.get(subkey)
                try:
                    if subval is not None:
                        return float(subval)
                except (TypeError, ValueError):
                    pass
        else:
            try:
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                pass

    # pola nested umum
    nested_candidates = [
        payload.get("fgi"),
        payload.get("data"),
        payload.get("result"),
    ]

    for item in nested_candidates:
        if isinstance(item, dict):
            for key in ("fgi_core", "core_fgi", "core", "score"):
                value = item.get(key)
                if isinstance(value, dict):
                    value = value.get("value", value.get("score"))
                try:
                    if value is not None:
                        return float(value)
                except (TypeError, ValueError):
                    continue

    return None


def load_core_fgi_from_files() -> tuple[float | None, str | None]:
    for path in FGI_JSON_CANDIDATES:
        data = load_json_if_exists(path)
        core = extract_core_fgi(data)
        if core is not None:
            return core, str(path)
    return None, None


def load_core_fgi_from_endpoint() -> tuple[float | None, str | None]:
    for url in FGI_ENDPOINT_CANDIDATES:
        if not url:
            continue
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code != 200:
                continue
            data = resp.json()
            core = extract_core_fgi(data)
            if core is not None:
                return core, url
        except Exception:
            continue
    return None, None


def resolve_core_fgi(earth: dict[str, Any]) -> tuple[float | None, str]:
    # 1) dari earth signals kalau suatu hari sudah tersedia
    core = pick_metric(earth, "fgi_core", "core_fgi", "fgi")
    if core is not None:
        return core, "earth_signals"

    # 2) dari file cache/json FGI
    core, source = load_core_fgi_from_files()
    if core is not None:
        return core, source or "fgi_json"

    # 3) dari endpoint internal FGI
    core, source = load_core_fgi_from_endpoint()
    if core is not None:
        return core, source or "fgi_endpoint"

    return None, "unavailable"

def compute_core_fgi_via_api(
    sst: float | None,
    sal: float | None,
    chl: float | None,
    date_utc: str | None,
) -> tuple[float | None, str]:
    if sst is None or sal is None or chl is None:
        return None, "missing_inputs"

    url = "http://127.0.0.1:8001/api/v1/fgi/score"
    payload = {
        "temp": sst,
        "sal": sal,
        "chl": chl,
        "date_utc": date_utc,
    }

    try:
        resp = requests.post(url, json=payload, timeout=3)
        if resp.status_code != 200:
            return None, f"http_{resp.status_code}"

        data = resp.json()

        # respons nyata sudah punya field "score"
        score = data.get("score")
        try:
            if score is not None:
                return float(score), url
        except (TypeError, ValueError):
            pass

        # fallback tambahan kalau format berubah di masa depan
        for key in ("fgi", "value", "core", "prediction"):
            val = data.get(key)
            if isinstance(val, dict):
                for subkey in ("value", "score", "prediction"):
                    subval = val.get(subkey)
                    try:
                        if subval is not None:
                            return float(subval), url
                    except (TypeError, ValueError):
                        pass
            else:
                try:
                    if val is not None:
                        return float(val), url
                except (TypeError, ValueError):
                    pass

        return None, "no_score_field"

    except Exception as e:
        return None, f"request_failed:{type(e).__name__}"



@router.get("/today")
def get_insight_today():
    earth = load_earth_today() or {}
    iod = load_iod_operational() or {}
    enso = load_enso_operational() or {}

    sst = pick_metric(
        earth,
        "sst",
        "sst_c",
        "sea_surface_temperature",
    )
    chl = pick_metric(
        earth,
        "chl",
        "chl_mg_m3",
        "chlorophyll",
        "chlor_a",
    )
    wind = pick_metric(
        earth,
        "wind",
        "wind_ms",
        "wind_speed",
        "wind_mps",
    )
    wave = pick_metric(
        earth,
        "wave",
        "wave_m",
        "wave_hs",
        "hs",
    )
    sal = pick_metric(
        earth,
        "sal",
        "sal_psu",
        "salinity",
    )
    ssh = pick_metric(
        earth,
        "ssh",
        "ssh_cm",
        "ssh_m",
        "sea_surface_height",
    )

    region_value = earth.get("region", "Aceh, Indonesia")
    region_name = region_value.get("name") if isinstance(region_value, dict) else region_value

    earth_date = (
        earth.get("date")
        or earth.get("date_utc")
        or earth.get("generated_date")
        or earth.get("day")
        or earth.get("as_of")
    )

    core_fgi, core_fgi_source = compute_core_fgi_via_api(
        sst=sst,
        sal=sal,
        chl=chl,
        date_utc=earth_date,
    )

    

    dmi = iod.get("dmi")
    iod_status = iod.get("status")

    iod_mod = compute_iod_modifier(
        dmi=dmi,
        iod_status=iod_status,
        sst=sst,
        chl=chl,
        wind=wind,
        wave=wave,
    )

    fgi_final = (
        compute_fgi_final(core_score=core_fgi, iod_modifier=iod_mod["modifier"])
        if core_fgi is not None
        else None
    )

    confidence = compute_fgi_confidence(
        has_sst=sst is not None,
        has_chl=chl is not None,
        has_wind=wind is not None,
        has_wave=wave is not None,
        has_sal=sal is not None,
        has_ssh=ssh is not None,
        iod_status=iod_mod["status"],
        iod_modifier=iod_mod["modifier"],
    )

    insight = build_daily_ocean_insight(
        sst=sst,
        chl=chl,
        wind=wind,
        wave=wave,
        sal=sal,
        ssh=ssh,
        dmi=dmi,
    )

    return {
        "date": earth_date or iod.get("date"),
        "region": region_name,
        "region_meta": region_value if isinstance(region_value, dict) else None,
        "signals": {
            "sst": sst,
            "chl": chl,
            "wind": wind,
            "wave": wave,
            "sal": sal,
            "ssh": ssh,
            "iod_dmi": dmi,
        },
        "classification": insight["classification"],
        "iod": iod,
        "enso": enso,
        "fgi": {
            "core": core_fgi,
            "core_source": core_fgi_source,
            "iod_modifier": iod_mod["modifier"],
            "final": fgi_final,
            "confidence": confidence,
            "explain": iod_mod,
        },
        "insight": {
            "opportunity": insight["opportunity"],
            "drivers": insight["drivers"],
            "risks": insight["risks"],
            "caution": insight["caution"],
            "summary": insight["summary"],
        },
        "generated_from": {
            "earth_candidates": [str(p) for p in EARTH_JSON_CANDIDATES],
            "fgi_candidates": [str(p) for p in FGI_JSON_CANDIDATES],
            "iod": "data/earth/iod_today.json",
        },
    }