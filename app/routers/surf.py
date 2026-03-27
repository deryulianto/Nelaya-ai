from __future__ import annotations

from pathlib import Path
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/surf", tags=["Surf"])

ROOT = Path(__file__).resolve().parents[2]
DERIVED_DIR = ROOT / "data" / "derived" / "surf_snapshot"
LATEST = DERIVED_DIR / "surf_wave_snapshot_latest.json"

PAT = re.compile(r"surf_wave_snapshot_(\d{4}-\d{2}-\d{2})\.json$")


def _no_store(resp: JSONResponse) -> JSONResponse:
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def _load_json(p: Path) -> Dict[str, Any]:
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"missing_file: {p.name}")
    try:
        return json.loads(p.read_text())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"bad_json: {p.name}: {e}")


def _safe_iso(s: Any) -> str | None:
    x = str(s or "").strip()
    if not x:
        return None
    return x.replace(".Z", "Z")


def _extract_date_and_valid(raw: Dict[str, Any]) -> Tuple[str | None, str | None]:
    valid = _safe_iso(raw.get("valid_utc") or raw.get("valid_time_utc") or raw.get("asOf"))
    raw_date = str(raw.get("date") or "").strip()
    date = raw_date if raw_date and raw_date != "unknown-date" else (valid[:10] if valid else None)
    return date, valid


def _freshness_status(date_utc: str | None, ref_day_utc: str | None = None) -> str:
    if not date_utc:
        return "unknown"

    try:
        target = datetime.strptime(date_utc, "%Y-%m-%d").date()
    except Exception:
        return "unknown"

    if ref_day_utc:
        try:
            ref = datetime.strptime(ref_day_utc, "%Y-%m-%d").date()
        except Exception:
            ref = datetime.now(timezone.utc).date()
    else:
        ref = datetime.now(timezone.utc).date()

    age_days = (ref - target).days
    if age_days <= 0:
        return "fresh"
    if age_days == 1:
        return "recent"
    return "stale"


def _confidence_today(raw: Dict[str, Any]) -> str:
    spots = raw.get("spots")
    if isinstance(spots, dict) and spots:
        valid_count = 0
        total = 0
        for _, s in spots.items():
            total += 1
            if isinstance(s, dict) and any(
                isinstance(s.get(k), (int, float)) for k in ("hs_m", "tp_s", "dir_deg")
            ):
                valid_count += 1
        if valid_count >= max(1, total // 2):
            return "high"
        if valid_count > 0:
            return "medium"
    return "low"


def _confidence_history(series: Dict[str, list]) -> str:
    if not isinstance(series, dict) or not series:
        return "low"
    total_points = 0
    valid_points = 0
    for _, pts in series.items():
        for p in pts or []:
            total_points += 1
            if any(isinstance(p.get(k), (int, float)) for k in ("hs_m", "tp_s", "dir_deg")):
                valid_points += 1
    if total_points == 0:
        return "low"
    ratio = valid_points / total_points
    if ratio >= 0.7:
        return "high"
    if ratio >= 0.3:
        return "medium"
    return "low"


def _build_trust(
    *,
    source: Any,
    date_utc: str | None,
    generated_at: str | None,
    confidence: str,
    basis_type: str,
    mode: str | None = None,
) -> Dict[str, Any]:
    freshness = _freshness_status(date_utc)
    caveat = (
        "Perairan terbuka dapat lebih dinamis dibanding rerata snapshot spot."
        if basis_type == "model_snapshot"
        else "Riwayat spot dibangun dari snapshot harian; celah data dapat memengaruhi kelancaran seri."
    )
    return {
        "source": source or "Copernicus Marine (CMEMS)",
        "date_utc": date_utc,
        "generated_at": generated_at,
        "freshness_status": freshness,
        "confidence": confidence,
        "basis_type": basis_type,
        "mode": mode,
        "caveat": caveat,
    }


@router.get("/spots/today")
def spots_today():
    raw = _load_json(LATEST)
    date_utc, valid_utc = _extract_date_and_valid(raw)
    generated_at = _safe_iso(raw.get("generated_at")) or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    payload = {
        "ok": True,
        **raw,
        "date": date_utc,
        "valid_utc": valid_utc,
        "generated_at": generated_at,
        "trust": _build_trust(
            source=raw.get("source"),
            date_utc=date_utc,
            generated_at=generated_at,
            confidence=_confidence_today(raw),
            basis_type="model_snapshot",
            mode="upstream",
        ),
    }
    return _no_store(JSONResponse(payload))


@router.get("/spots/history")
def spots_history(days: int = Query(7, ge=1, le=60)):
    files = []
    for p in DERIVED_DIR.glob("surf_wave_snapshot_*.json"):
        m = PAT.search(p.name)
        if m:
            files.append((m.group(1), p))
    if not files:
        raise HTTPException(status_code=404, detail="no_history_files")

    files.sort(key=lambda x: x[0])
    take = files[-days:]

    series: Dict[str, list] = {}
    oldest_day = None
    newest_day = None

    for day, p in take:
        oldest_day = oldest_day or day
        newest_day = day
        raw = _load_json(p)
        spots = raw.get("spots") or {}
        if isinstance(spots, dict):
            for sid, s in spots.items():
                series.setdefault(sid, []).append(
                    {
                        "t": day,
                        "hs_m": s.get("hs_m"),
                        "tp_s": s.get("tp_s"),
                        "dir_deg": s.get("dir_deg"),
                    }
                )

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "ok": True,
        "days": days,
        "generated_at": generated_at,
        "history_window": {
            "oldest_day": oldest_day,
            "newest_day": newest_day,
        },
        "series": series,
        "trust": _build_trust(
            source="Copernicus Marine (CMEMS)",
            date_utc=newest_day,
            generated_at=generated_at,
            confidence=_confidence_history(series),
            basis_type="derived_metric",
            mode="upstream",
        ),
    }
    return _no_store(JSONResponse(payload))
