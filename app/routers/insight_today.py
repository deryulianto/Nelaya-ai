from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/insight", tags=["insight"])

BASE = os.getenv("NELAYA_BASE", "http://127.0.0.1:8001").rstrip("/")


@router.get("/today")
async def insight_today():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            osi_r = await client.get(f"{BASE}/api/v1/osi/today")
            sig_r = await client.get(f"{BASE}/api/v1/signals/today")

            osi_r.raise_for_status()
            sig_r.raise_for_status()

        osi = osi_r.json()
        sig = sig_r.json()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"fetch failed: {e}") from e

    osi_data = osi.get("osi", {})
    inputs = osi.get("inputs_used", {}) or {}
    narrative = osi_data.get("narrative", {}) or {}

    sst = inputs.get("sst_c")
    chl = inputs.get("chl_mg_m3")
    wind = inputs.get("wind_ms")
    wave = inputs.get("wave_m")

    osi_score = osi_data.get("osi")
    label = osi_data.get("label")
    confidence = osi_data.get("confidence")

    insight: list[str] = []

    # ---------------------------------------------------------
    # Rule 1: Ocean state
    # ---------------------------------------------------------
    if osi_score is not None:
        if osi_score >= 76:
            insight.append("Ocean State Index menunjukkan kondisi laut yang kuat dan cukup aktif untuk dipantau lebih lanjut.")
        elif osi_score >= 58:
            insight.append("Kondisi laut berada pada level kuat-moderat, dengan struktur dan dinamika yang masih cukup sehat.")
        elif osi_score >= 40:
            insight.append("Kondisi laut berada pada level moderat, cukup stabil namun belum menunjukkan penguatan yang menonjol.")
        else:
            insight.append("Kondisi laut cenderung lemah atau membutuhkan kehati-hatian dalam membaca dinamika hari ini.")

    # ---------------------------------------------------------
    # Rule 2: SST
    # ---------------------------------------------------------
    if sst is not None:
        if sst >= 30.0:
            insight.append("Suhu permukaan laut berada pada fase hangat (~30°C), menandakan perairan tropis yang stabil namun perlu dipantau bila pemanasan berlanjut.")
        elif sst >= 29.0:
            insight.append("Suhu permukaan laut berada pada kisaran tropis yang cukup seimbang untuk dinamika laut harian.")
        else:
            insight.append("Suhu permukaan laut relatif lebih rendah dari kisaran hangat tropis dominan.")

    # ---------------------------------------------------------
    # Rule 3: CHL
    # ---------------------------------------------------------
    if chl is not None:
        if chl >= 0.35:
            insight.append("Klorofil relatif tinggi, memberi sinyal produktivitas biologis permukaan yang cukup kuat.")
        elif chl >= 0.18:
            insight.append("Klorofil berada pada tingkat moderat, cukup mendukung aktivitas biologis namun belum menunjukkan lonjakan produktivitas.")
        else:
            insight.append("Klorofil masih rendah, menandakan produktivitas permukaan belum menguat.")

    # ---------------------------------------------------------
    # Rule 4: Wind + Wave
    # ---------------------------------------------------------
    if wind is not None and wave is not None:
        if wind >= 8.0 or wave >= 1.5:
            insight.append("Angin atau gelombang cukup tinggi, sehingga aktivitas laut perlu mempertimbangkan faktor keselamatan.")
        elif wind >= 4.0 or wave >= 0.7:
            insight.append("Dinamika angin dan gelombang berada pada kisaran moderat, cukup terasa namun masih relatif terkendali.")
        else:
            insight.append("Permukaan laut relatif tenang, cocok untuk pembacaan kondisi laut yang lebih stabil.")

    # ---------------------------------------------------------
    # Rule 5: fallback minimal insight
    # ---------------------------------------------------------
    if not insight:
        insight.append("Kondisi laut hari ini relatif stabil, namun interpretasi rinci tetap memerlukan pembacaan konteks oseanografi.")
        insight.append("Gunakan indeks dan sinyal harian sebagai panduan awal, bukan satu-satunya dasar keputusan lapangan.")

    # Biar tidak terlalu panjang
    insight = insight[:4]

    summary = narrative.get("summary") or "Ringkasan kondisi laut harian belum tersedia."

    return {
        "region": osi.get("region"),
        "date": osi.get("date_utc"),
        "osi": {
            "score": osi_score,
            "label": label,
            "confidence": confidence,
        },
        "summary": summary,
        "insight_points": insight,
        "signals": {
            "sst_c": sst,
            "chl_mg_m3": chl,
            "wind_ms": wind,
            "wave_m": wave,
        },
        "status": osi_data.get("status"),
        "generated_at": osi.get("generated_at"),
    }