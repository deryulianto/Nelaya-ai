from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException

from app.core.osi.engine import compute_osi
from app.core.osi.schemas import OsiFeatures

router = APIRouter(prefix="/api/v1/osi", tags=["osi-v1"])

BASE = os.getenv("NELAYA_BASE", "http://127.0.0.1:8001").rstrip("/")


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
        # 1) coba ambil langsung dari root JSON
        if root.get(key) is not None:
            return root.get(key)
        if alt and root.get(alt) is not None:
            return root.get(alt)

        # 2) coba ambil dari metrics
        v = metrics.get(key)
        if v is None and alt:
            v = metrics.get(alt)

        # 3) jika formatnya {"value": ...}
        if isinstance(v, dict):
            return v.get("value")

        return v

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

    payload = OsiFeatures(
        region=region,
        date=j.get("date_utc") or (j.get("generated_at", "")[:10] if j.get("generated_at") else "unknown"),
        sst_c=float(sst),
        chl_mg_m3=float(chl),
        wind_ms=float(wind),
        wave_hs_m=float(wave),
        thermocline_depth_m=110.0,  # fallback sementara sampai kita hubungkan profil suhu
        ssh_anom_cm=float(ssh) if ssh is not None else None,
        freshness_hours=6.0,
        completeness_ratio=0.95,
        zone_class="shelf",
    )

    result = compute_osi(payload)

    return {
        "source": "signals_today",
        "upstream_url": url,
        "region": j.get("region", {}).get("name", region) if isinstance(j.get("region"), dict) else j.get("region", region),
        "generated_at": j.get("generated_at") or j.get("meta", {}).get("generated_at"),
        "date_utc": j.get("date_utc"),
        "inputs_used": {
            "sst_c": sst,
            "chl_mg_m3": chl,
            "wind_ms": wind,
            "wave_m": wave,
            "ssh_cm": ssh,
        },
        "osi": result,
    }