from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

from app.services.wa_formatter import format_whatsapp_text

BASE = os.getenv("NELAYA_BASE", "http://127.0.0.1:8001").rstrip("/")


def _safe_get(d: Any, *keys: str, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def _classify_fgi(value: float | int | None) -> str:
    if value is None:
        return "Unknown"
    v = float(value)
    if v < 35:
        return "Low"
    if v < 65:
        return "Moderate"
    return "High"


def _build_headline(osi_value: float | None, fgi_value: float | None) -> str:
    if osi_value is None and fgi_value is None:
        return "Ringkasan laut hari ini belum lengkap"

    if osi_value is not None and fgi_value is not None:
        if osi_value >= 65 and fgi_value < 35:
            return "Laut Aceh cukup aktif, namun peluang ikan belum menguat"
        if osi_value >= 65 and fgi_value >= 35:
            return "Laut Aceh aktif dan peluang ikan mulai terbentuk"
        if osi_value < 55 and fgi_value < 35:
            return "Laut Aceh cenderung lemah dan peluang ikan terbatas"

    if osi_value is not None and osi_value >= 65:
        return "Laut Aceh berada pada kondisi cukup kuat hari ini"

    return "Kondisi laut Aceh hari ini perlu dibaca hati-hati"


def _build_summary_short(
    osi_label: str,
    fgi_value: float | None,
    strong_regions: List[str],
    weak_regions: List[str],
) -> str:
    parts: List[str] = []

    if osi_label:
        parts.append(f"Laut berada pada kondisi {osi_label.lower()}.")

    if fgi_value is not None:
        if fgi_value < 35:
            parts.append("Peluang agregasi ikan belum kuat.")
        elif fgi_value < 65:
            parts.append("Peluang ikan mulai terbentuk secara lokal.")
        else:
            parts.append("Peluang ikan terlihat cukup baik di beberapa area.")

    if strong_regions:
        parts.append(f"Wilayah yang relatif lebih baik: {strong_regions[0]}.")

    if weak_regions:
        parts.append(f"Wilayah yang perlu dicermati: {weak_regions[0]}.")

    return " ".join(parts).strip() or "Ringkasan singkat belum tersedia."


def _build_actions(
    fgi_value: float | None,
    hotspot_count: int,
    confidence: float | None,
) -> List[str]:
    actions: List[str] = []

    if fgi_value is None or fgi_value < 35:
        actions.append("Operasi terbatas dan hemat BBM")
        actions.append("Pilih area yang lebih stabil")
    elif fgi_value < 65:
        actions.append("Pantau hotspot lokal sebelum berangkat")
        actions.append("Pilih rute yang efisien")
    else:
        actions.append("Prioritaskan area dengan hotspot yang konsisten")
        actions.append("Tetap jaga batas operasi aman")

    if hotspot_count > 0:
        actions.append("Perhatikan zona hotspot untuk pemantauan lebih lanjut")

    if confidence is not None and confidence < 80:
        actions.append("Tunggu pembaruan bila data masih berubah")

    out: List[str] = []
    for x in actions:
        if x not in out:
            out.append(x)
    return out[:3]


def _build_warnings() -> List[str]:
    return [
        "tetap cek BMKG dan kondisi lapangan",
        "ini alat bantu pembacaan kondisi laut, bukan pengganti peringatan resmi",
    ]


async def _fetch_json(client: httpx.AsyncClient, url: str) -> Dict[str, Any]:
    r = await client.get(url)
    r.raise_for_status()
    return r.json()


def _to_fgi_100(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except Exception:
        return None

    # kalau masih skala 0..1, ubah ke 0..100
    if 0.0 <= x <= 1.0:
        return round(x * 100.0, 2)

    return round(x, 2)


async def _fetch_fgi_value(
    client: httpx.AsyncClient,
    signals_today: Dict[str, Any],
) -> tuple[float | None, str]:
    """
    Urutan:
    1) coba GET /api/v1/fgi/today
    2) fallback POST /api/v1/fgi/score dengan SST/SAL/CHL dari signals_today
    Return: (fgi_value_0_100, source_label)
    """
    # -------- 1) coba endpoint fgi/today --------
    try:
        r = await client.get(f"{BASE}/api/v1/fgi/today")
        if r.status_code < 400:
            j = r.json()

            candidates = [
                _safe_get(j, "score"),
                _safe_get(j, "fgi", "score"),
                _safe_get(j, "data", "score"),
                _safe_get(j, "value"),
                _safe_get(j, "fgi"),
            ]
            for c in candidates:
                val = _to_fgi_100(c)
                if val is not None:
                    return val, "fgi_today"
    except Exception:
        pass

    # -------- 2) fallback hitung dari signals_today --------
    sst = signals_today.get("sst_c")
    sal = signals_today.get("sal_psu")
    chl = signals_today.get("chl_mg_m3")

    if sst is None or sal is None or chl is None:
        return None, "missing_inputs"

    payload = {
        "temp": float(sst),
        "sal": float(sal),
        "chl": float(chl),
    }

    try:
        r = await client.post(f"{BASE}/api/v1/fgi/score", json=payload)
        if r.status_code < 400:
            j = r.json()

            candidates = [
                _safe_get(j, "score"),
                _safe_get(j, "fgi", "score"),
                _safe_get(j, "data", "score"),
                _safe_get(j, "value"),
            ]
            for c in candidates:
                val = _to_fgi_100(c)
                if val is not None:
                    return val, "fgi_score_from_signals"
    except Exception:
        pass

    return None, "unavailable"


async def build_today_brief(audience: str = "nelayan") -> Dict[str, Any]:
    audience = (audience or "nelayan").strip().lower()

    urls = {
        "osi_today": f"{BASE}/api/v1/osi/today",
        "insight_today": f"{BASE}/api/v1/insight/today",
        "signals_today": f"{BASE}/api/v1/signals/today",
        "osi_map": f"{BASE}/api/v1/osi/map",
    }

    data: Dict[str, Any] = {}
    status = "ok"
    errors: List[str] = []

    async with httpx.AsyncClient(timeout=20) as client:
        for key, url in urls.items():
            try:
                data[key] = await _fetch_json(client, url)
            except Exception as e:
                data[key] = {}
                errors.append(f"{key}: {e}")
                status = "partial"

        # FGI diambil dari sumber yang benar
        fgi_value, fgi_source = await _fetch_fgi_value(client, data.get("signals_today", {}) or {})

    # region / date
    region = (
        _safe_get(data.get("insight_today", {}), "region")
        or _safe_get(data.get("signals_today", {}), "region", "name")
        or "Aceh"
    )
    date = (
        _safe_get(data.get("insight_today", {}), "date")
        or _safe_get(data.get("osi_today", {}), "date_utc")
        or _safe_get(data.get("signals_today", {}), "date_utc")
        or "unknown"
    )
    generated_at = (
        _safe_get(data.get("insight_today", {}), "generated_at")
        or _safe_get(data.get("signals_today", {}), "generated_at")
        or _safe_get(data.get("signals_today", {}), "meta", "generated_at")
        or ""
    )

    # OSI
    osi_value = _safe_get(data.get("insight_today", {}), "osi", "score")
    osi_label = _safe_get(data.get("insight_today", {}), "osi", "label") or _safe_get(
        data.get("osi_today", {}), "osi", "label"
    ) or "Unknown"
    osi_conf = _safe_get(data.get("insight_today", {}), "osi", "confidence") or _safe_get(
        data.get("osi_today", {}), "osi", "confidence"
    )

    # Signals
    signals_obj = data.get("signals_today", {}) or {}
    signals = {
        "sst_c": signals_obj.get("sst_c"),
        "chl_mg_m3": signals_obj.get("chl_mg_m3"),
        "wind_ms": signals_obj.get("wind_ms"),
        "wave_m": signals_obj.get("wave_m"),
        "sal_psu": signals_obj.get("sal_psu"),
    }

    # FGI
    fgi_label = _classify_fgi(fgi_value)

    # Osi map spatial
    region_summary = data.get("osi_map", {}).get("region_summary") or []
    hotspot_regions = data.get("osi_map", {}).get("hotspot_regions") or []
    anomaly_summary = data.get("osi_map", {}).get("anomaly_summary") or {}
    hotspot_count = int((_safe_get(data.get("osi_map", {}), "summary", "hotspot_count", default=0) or 0))

    strong_regions = [x.get("name") for x in region_summary[:2] if x.get("name")]
    weak_regions = [x.get("name") for x in region_summary[-1:] if x.get("name")] if region_summary else []

    insight_points = data.get("insight_today", {}).get("insight_points") or []
    summary_short = _build_summary_short(osi_label, fgi_value, strong_regions, weak_regions)

    insight_summary = data.get("insight_today", {}).get("summary")
    if isinstance(insight_summary, str) and insight_summary.strip():
        summary_short = insight_summary.strip()

    headline = _build_headline(osi_value, fgi_value)
    actions = _build_actions(fgi_value, hotspot_count, osi_conf)
    warnings = _build_warnings()

    brief: Dict[str, Any] = {
        "ok": True,
        "date": date,
        "generated_at": generated_at,
        "region": region,
        "audience": audience,
        "status": status,
        "headline": headline,
        "summary_short": summary_short,
        "scores": {
            "osi": {
                "value": osi_value,
                "label": osi_label,
                "confidence": osi_conf,
            },
            "fgi": {
                "value": fgi_value,
                "label": fgi_label,
                "source": fgi_source,
            },
        },
        "signals": signals,
        "spatial": {
            "hotspot_count": hotspot_count,
            "strong_regions": strong_regions,
            "weak_regions": weak_regions,
            "hotspot_regions": hotspot_regions,
            "region_summary": region_summary,
            "anomaly_summary": anomaly_summary,
        },
        "insight_points": insight_points,
        "actions": actions,
        "warnings": warnings,
        "links": {
            "dashboard": "https://nelaya-ai.com/dashboard",
            "insights": "https://nelaya-ai.com/insights",
            "map": "https://nelaya-ai.com/insights",
        },
        "sources": {
            "osi_today": urls["osi_today"],
            "insight_today": urls["insight_today"],
            "signals_today": urls["signals_today"],
            "osi_map": urls["osi_map"],
            "fgi_source": fgi_source,
        },
    }

    brief["whatsapp_text"] = format_whatsapp_text(brief, audience=audience)

    if errors:
        brief["errors"] = errors

    return brief