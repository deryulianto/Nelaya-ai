from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from app.core.osi.engine import compute_osi
from app.core.osi.schemas import OsiFeatures

router = APIRouter(prefix="/api/v1/osi", tags=["osi-v1"])

BASE = os.getenv("NELAYA_BASE", "http://127.0.0.1:8001").rstrip("/")


def _safe_date(v: object) -> str | None:
    s = str(v or "").strip()
    if not s:
        return None
    return s[:10] if len(s) >= 10 else s


def _freshness_status(date_utc: str | None, generated_at: str | None = None) -> str:
    ref = datetime.now(timezone.utc).date()
    target = None

    for raw in (date_utc, generated_at):
        s = _safe_date(raw)
        if not s:
            continue
        try:
            target = datetime.fromisoformat(s).date()
            break
        except Exception:
            try:
                target = datetime.strptime(s, "%Y-%m-%d").date()
                break
            except Exception:
                continue

    if target is None:
        return "unknown"

    delta = (ref - target).days
    if delta <= 0:
        return "fresh"
    if delta <= 2:
        return "recent"
    return "stale"


def _confidence(required_ok: bool, completeness_ratio: float, freshness_status: str) -> str:
    if not required_ok:
        return "low"
    if completeness_ratio >= 0.95 and freshness_status in {"fresh", "recent"}:
        return "high"
    if completeness_ratio >= 0.80 and freshness_status in {"fresh", "recent"}:
        return "medium"
    return "low"


def _pick_metric(metrics: dict, key: str, alt: str | None = None):
    if metrics.get(key) is not None:
        return metrics.get(key)
    if alt and metrics.get(alt) is not None:
        return metrics.get(alt)

    v = metrics.get(key)
    if v is None and alt:
        v = metrics.get(alt)

    if isinstance(v, dict):
        return v.get("value")
    return v


def _build_explain(sst: float, chl: float, wind: float, wave: float, ssh: float | None, result: Any) -> dict[str, Any]:
    drivers: list[str] = []

    if sst >= 30.5:
        drivers.append("SST sangat hangat, yang dapat menekan stabilitas kondisi permukaan di beberapa area.")
    elif sst >= 29.0:
        drivers.append("SST hangat tropis, masih umum untuk Aceh tetapi tetap memengaruhi komponen termal indeks.")
    else:
        drivers.append("SST relatif lebih sejuk, sehingga komponen termal indeks cenderung lebih terkendali.")

    if chl >= 0.5:
        drivers.append("Klorofil-a tinggi, memberi dukungan kuat pada komponen produktivitas permukaan.")
    elif chl >= 0.15:
        drivers.append("Klorofil-a berada di level sedang, cukup menopang produktivitas tetapi belum dominan.")
    else:
        drivers.append("Klorofil-a rendah, sehingga dukungan produktivitas permukaan cenderung terbatas.")

    if wave >= 2.5:
        drivers.append("Gelombang tinggi menambah tekanan kondisi laut dan menurunkan kenyamanan operasional di lapangan.")
    elif wave >= 1.5:
        drivers.append("Gelombang sedang-tinggi memberi sinyal kehati-hatian pada pembacaan kondisi harian.")
    else:
        drivers.append("Gelombang relatif rendah-sedang, sehingga komponen dinamika permukaan tidak terlalu menekan indeks.")

    if wind >= 10:
        drivers.append("Angin kuat meningkatkan dinamika permukaan dan dapat menekan stabilitas kondisi laut harian.")
    elif wind >= 6:
        drivers.append("Angin sedang-kuat memberi pengaruh nyata pada kondisi permukaan laut.")
    else:
        drivers.append("Angin relatif lemah-sedang, sehingga tekanan atmosferik permukaan tidak terlalu dominan.")

    summary = "OSI harian dibangun dari sintesis SST, klorofil-a, angin, gelombang, dan SSH bila tersedia."
    if isinstance(result, dict):
        maybe_score = result.get("score") or result.get("osi") or result.get("value")
        if maybe_score is not None:
            summary = f"OSI harian dihitung dari sinyal oseanografi dan menghasilkan skor indikatif {maybe_score}."

    return {
        "drivers": drivers[:4],
        "input_summary": {
            "sst_c": round(float(sst), 3),
            "chl_mg_m3": round(float(chl), 4),
            "wind_ms": round(float(wind), 3),
            "wave_hs_m": round(float(wave), 3),
            "ssh_cm": round(float(ssh), 3) if ssh is not None else None,
        },
        "score_summary": summary,
        "model_note": "OSI today adalah indeks turunan dari sinyal oseanografi harian, bukan pengukuran langsung seluruh kesehatan ekosistem.",
    }


@router.get("/today")
async def osi_today(region: str = "aceh"):
    url = f"{BASE}/api/v1/signals/today"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            r.raise_for_status()
            j = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"signals fetch failed: {e}") from e

    metrics = j.get("metrics", {})

    def pick(root: dict, key: str, alt: str | None = None):
        if root.get(key) is not None:
            return root.get(key)
        if alt and root.get(alt) is not None:
            return root.get(alt)
        return _pick_metric(metrics, key, alt)

    sst = pick(j, "sst_c", "sst")
    chl = pick(j, "chl_mg_m3", "chl")
    wind = pick(j, "wind_ms", "wind")
    wave = pick(j, "wave_m", "wave")
    ssh = pick(j, "ssh_cm", "ssh")

    if sst is None or chl is None or wind is None or wave is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing required metrics",
                "sst": sst,
                "chl": chl,
                "wind": wind,
                "wave": wave,
                "ssh": ssh,
            },
        )

    date_utc = _safe_date(j.get("date_utc") or (j.get("generated_at", "")[:10] if j.get("generated_at") else None))
    generated_at = j.get("generated_at") or j.get("meta", {}).get("generated_at")
    completeness_ratio = 0.95

    payload = OsiFeatures(
        region=region,
        date=date_utc or "unknown",
        sst_c=float(sst),
        chl_mg_m3=float(chl),
        wind_ms=float(wind),
        wave_hs_m=float(wave),
        thermocline_depth_m=110.0,
        ssh_anom_cm=float(ssh) if ssh is not None else None,
        freshness_hours=6.0,
        completeness_ratio=completeness_ratio,
        zone_class="shelf",
    )

    result = compute_osi(payload)
    freshness = _freshness_status(date_utc, generated_at)
    confidence = _confidence(True, completeness_ratio, freshness)

    return {
        "source": "signals_today",
        "upstream_url": url,
        "region": j.get("region", {}).get("name", region) if isinstance(j.get("region"), dict) else j.get("region", region),
        "generated_at": generated_at,
        "date_utc": date_utc,
        "inputs_used": {
            "sst_c": sst,
            "chl_mg_m3": chl,
            "wind_ms": wind,
            "wave_m": wave,
            "ssh_cm": ssh,
        },
        "trust": {
            "source": "Signals today → OSI derived index",
            "date_utc": date_utc,
            "generated_at": generated_at,
            "freshness_status": freshness,
            "confidence": confidence,
            "basis_type": "derived_ocean_state_index",
            "mode": "daily-synthesis",
            "caveat": "OSI today adalah indeks sintesis berbasis sinyal oseanografi harian dan tidak identik dengan pengukuran langsung kesehatan ekosistem.",
        },
        "explain": _build_explain(float(sst), float(chl), float(wind), float(wave), float(ssh) if ssh is not None else None, result),
        "osi": result,
    }
