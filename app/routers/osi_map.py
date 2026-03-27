from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re

from fastapi import APIRouter, HTTPException, Query

ROOT = Path(__file__).resolve().parents[2]
GRID_DIR = ROOT / "data" / "fgi_map_grid"
LATEST = GRID_DIR / "latest.geojson"
PAT = re.compile(r"fgi_grid_(\d{4}-\d{2}-\d{2})\.geojson$")

router = APIRouter(prefix="/api/v1/osi", tags=["Ocean State Index"])


def classify_osi(osi: float) -> str:
    if osi < 40:
        return "Poor"
    if osi < 55:
        return "Weak"
    if osi < 65:
        return "Moderate"
    if osi < 75:
        return "Good"
    return "Strong"


def compute_osi(p: dict):
    sst = p.get("sst_c")
    chl = p.get("chl_mg_m3")
    sal = p.get("sal_psu")
    score = p.get("score")

    means = p.get("means") if isinstance(p.get("means"), dict) else {}
    fgi = p.get("fgi") if isinstance(p.get("fgi"), dict) else {}

    if sst is None:
        sst = means.get("sst_c")
    if chl is None:
        chl = means.get("chl_mg_m3")
    if sal is None:
        sal = means.get("sal_psu")
    if score is None:
        score = fgi.get("score")

    if None in (sst, chl, sal, score):
        return None

    thermal = max(0.0, 100.0 - abs(float(sst) - 29.0) * 25.0)
    prod = min(float(chl) / 0.4, 1.0) * 100.0
    habitat = float(score) * 100.0
    water = max(0.0, 100.0 - abs(float(sal) - 33.5) * 20.0)

    osi = (
        0.30 * thermal +
        0.30 * prod +
        0.25 * habitat +
        0.15 * water
    )

    return round(osi, 2), thermal, prod, habitat, water


def infer_region(lon: float, lat: float) -> str:
    if lon >= 96.7:
        return "Selat Malaka"
    if lon <= 94.8 and lat <= 4.8:
        return "Barat Simeulue"
    if lon <= 95.5 and lat >= 5.0:
        return "Utara Aceh"
    if 94.8 < lon < 96.7 and lat < 5.0:
        return "Barat Aceh"
    return "Tengah Aceh Laut"


def build_map_narrative(region_summary: list[dict], anomaly_summary: dict, mean_osi: float) -> list[str]:
    lines: list[str] = []

    if mean_osi >= 75:
        lines.append("Secara umum sistem laut Aceh hari ini berada pada kondisi kuat, dengan beberapa grid menunjukkan sinyal sangat baik.")
    elif mean_osi >= 65:
        lines.append("Secara umum sistem laut Aceh berada pada kondisi baik, dengan variasi moderat antar wilayah.")
    elif mean_osi >= 55:
        lines.append("Secara umum sistem laut Aceh berada pada level moderat–baik, sehingga pembacaan per wilayah menjadi penting.")
    else:
        lines.append("Secara umum sistem laut Aceh masih cenderung lemah–moderat, sehingga hotspot lokal lebih penting daripada rata-rata wilayah.")

    if region_summary:
        best = region_summary[0]
        worst = region_summary[-1]

        lines.append(
            f"Wilayah dengan performa relatif terbaik hari ini adalah {best['name']} "
            f"(rata-rata OSI {best['mean_osi']:.0f}, {best['class']})."
        )
        lines.append(
            f"Wilayah yang relatif lebih lemah adalah {worst['name']} "
            f"(rata-rata OSI {worst['mean_osi']:.0f}, {worst['class']})."
        )

    high_count = int(anomaly_summary.get("high_count", 0) or 0)
    low_count = int(anomaly_summary.get("low_count", 0) or 0)

    if high_count > 0:
        lines.append(
            f"Terdapat {high_count} grid dengan anomali tinggi, yang dapat dibaca sebagai area laut yang relatif menonjol dibanding distribusi harian."
        )
    if low_count > 0:
        lines.append(
            f"Terdapat {low_count} grid dengan anomali rendah, yang menandai zona yang relatif lebih lemah dibanding pola umum hari ini."
        )

    return lines


def file_generated_at_iso(p: Path) -> str | None:
    try:
        ts = p.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return None


def safe_date(v: object) -> str | None:
    s = str(v or "").strip()
    if not s:
        return None
    return s[:10] if len(s) >= 10 else s


def _freshness_status(date_utc: str | None, generated_at: str | None = None) -> str:
    ref = datetime.now(timezone.utc).date()
    target = None
    for raw in (date_utc, generated_at):
        s = safe_date(raw)
        if not s:
            continue
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


def _confidence_from_feature_count(n: int) -> str:
    if n >= 100:
        return "high"
    if n >= 20:
        return "medium"
    return "low"


def _build_trust(*, source: str, date_utc: str | None, generated_at: str | None, feature_count: int, mode: str, basis_type: str) -> dict:
    freshness = _freshness_status(date_utc, generated_at)
    confidence = _confidence_from_feature_count(feature_count)
    caveat = (
        "OSI map adalah indeks spasial turunan dari grid FGI/env signals, bukan pengukuran langsung kesehatan ekosistem pada setiap titik."
        if mode == "map"
        else "Riwayat OSI dibangun dari grid harian yang tersedia; celah file atau perubahan coverage dapat memengaruhi kontinuitas seri."
    )
    return {
        "source": source,
        "date_utc": date_utc,
        "generated_at": generated_at,
        "freshness_status": freshness,
        "confidence": confidence,
        "basis_type": basis_type,
        "mode": mode,
        "feature_count": feature_count,
        "caveat": caveat,
    }


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def extract_lon_lat(geom: dict) -> tuple[float, float] | None:
    gtype = geom.get("type")
    coords = geom.get("coordinates")

    try:
        if gtype == "Point" and isinstance(coords, list) and len(coords) >= 2:
            return float(coords[0]), float(coords[1])

        if gtype == "Polygon" and isinstance(coords, list) and coords and coords[0] and len(coords[0][0]) >= 2:
            xs = [float(pt[0]) for pt in coords[0]]
            ys = [float(pt[1]) for pt in coords[0]]
            return sum(xs) / len(xs), sum(ys) / len(ys)

        if gtype == "MultiPolygon" and isinstance(coords, list) and coords and coords[0] and coords[0][0]:
            ring = coords[0][0]
            xs = [float(pt[0]) for pt in ring]
            ys = [float(pt[1]) for pt in ring]
            return sum(xs) / len(xs), sum(ys) / len(ys)
    except Exception:
        return None

    return None


def build_snapshot_from_fc(fc: dict, fallback_date: str | None, generated_at: str | None, include_geojson: bool = True) -> dict:
    src_features = fc.get("features", []) or []

    features = []
    osi_values: list[float] = []
    data_dates: list[str] = []

    for f in src_features:
        props = f.get("properties", {}) or {}
        geom = f.get("geometry", {}) or {}

        lonlat = extract_lon_lat(geom)
        if lonlat is None:
            continue

        lon, lat = lonlat
        result = compute_osi(props)
        if result is None:
            continue

        osi, thermal, prod, habitat, water = result
        osi_values.append(osi)

        d = safe_date(props.get("date_utc")) or fallback_date
        if d:
            data_dates.append(d)

        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "date_utc": d,
                "osi": osi,
                "osi_class": classify_osi(osi),
                "thermal": round(thermal, 2),
                "productivity": round(prod, 2),
                "habitat": round(habitat, 2),
                "water_mass": round(water, 2),
                "confidence": 85,
                "hotspot": False,
                "anomaly_flag": "normal",
                "region_hint": infer_region(lon, lat),
            },
        })

    if not features:
        snap = {
            "date": fallback_date,
            "generated_at": generated_at,
            "feature_count": 0,
            "summary": {
                "min": None,
                "max": None,
                "mean": None,
                "p10": None,
                "p90": None,
                "hotspot_count": 0,
            },
            "region_summary": [],
            "anomaly_summary": {"high_count": 0, "low_count": 0},
            "hotspot_regions": [],
            "map_narrative": [],
            "trust": _build_trust(
                source="FGI grid substrate • latest.geojson",
                date_utc=fallback_date,
                generated_at=generated_at,
                feature_count=0,
                mode="history-snapshot",
                basis_type="derived_spatial_index",
            ),
        }
        if include_geojson:
            snap["geojson"] = {"type": "FeatureCollection", "features": []}
        return snap

    sorted_vals = sorted(osi_values)
    p10 = sorted_vals[max(0, int(len(sorted_vals) * 0.1) - 1)]
    p90 = sorted_vals[max(0, int(len(sorted_vals) * 0.9) - 1)]

    hotspot_count = 0
    high_anom = 0
    low_anom = 0
    region_buckets: dict[str, list[float]] = {}
    hotspot_buckets: dict[str, int] = {}

    for feat in features:
        osi = feat["properties"]["osi"]
        region_hint = feat["properties"]["region_hint"]
        region_buckets.setdefault(region_hint, []).append(osi)

        is_hotspot = osi >= max(75.0, p90)
        feat["properties"]["hotspot"] = is_hotspot
        if is_hotspot:
            hotspot_count += 1
            hotspot_buckets[region_hint] = hotspot_buckets.get(region_hint, 0) + 1

        if osi >= p90:
            feat["properties"]["anomaly_flag"] = "high"
            high_anom += 1
        elif osi <= p10:
            feat["properties"]["anomaly_flag"] = "low"
            low_anom += 1
        else:
            feat["properties"]["anomaly_flag"] = "normal"

    mean_osi = round(sum(osi_values) / len(osi_values), 2)

    region_summary = []
    for region_name, vals in region_buckets.items():
        m = round(sum(vals) / len(vals), 2)
        region_summary.append({
            "name": region_name,
            "mean_osi": m,
            "class": classify_osi(m),
            "count": len(vals),
        })
    region_summary = sorted(region_summary, key=lambda x: x["mean_osi"], reverse=True)

    hotspot_regions = sorted(
        [{"name": k, "count": v} for k, v in hotspot_buckets.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    anomaly_summary = {"high_count": high_anom, "low_count": low_anom}
    map_narrative = build_map_narrative(region_summary, anomaly_summary, mean_osi)
    latest_data_date = max(data_dates) if data_dates else fallback_date

    snap = {
        "date": latest_data_date,
        "generated_at": generated_at,
        "feature_count": len(features),
        "summary": {
            "min": round(min(osi_values), 2),
            "max": round(max(osi_values), 2),
            "mean": mean_osi,
            "p10": round(p10, 2),
            "p90": round(p90, 2),
            "hotspot_count": hotspot_count,
        },
        "region_summary": region_summary,
        "anomaly_summary": anomaly_summary,
        "hotspot_regions": hotspot_regions,
        "map_narrative": map_narrative,
        "trust": _build_trust(
            source=f"FGI grid substrate • {fc.get('name') or 'geojson'}",
            date_utc=latest_data_date,
            generated_at=generated_at,
            feature_count=len(features),
            mode="history-snapshot",
            basis_type="derived_spatial_index",
        ),
    }

    if include_geojson:
        snap["geojson"] = {"type": "FeatureCollection", "features": features}

    return snap


@router.get("/map")
def osi_map():
    if not LATEST.exists():
        raise HTTPException(404, "FGI grid not found")

    fc = load_json(LATEST)
    generated_at = fc.get("generated_at") or file_generated_at_iso(LATEST)
    snap = build_snapshot_from_fc(fc, fallback_date=None, generated_at=generated_at, include_geojson=True)

    return {
        "type": "FeatureCollection",
        "date_utc": snap.get("date"),
        "generated_at": snap.get("generated_at"),
        "feature_count": snap.get("feature_count", 0),
        "features": snap.get("geojson", {}).get("features", []),
        "summary": snap.get("summary", {}),
        "region_summary": snap.get("region_summary", []),
        "anomaly_summary": snap.get("anomaly_summary", {}),
        "hotspot_regions": snap.get("hotspot_regions", []),
        "map_narrative": snap.get("map_narrative", []),
        "trust": _build_trust(
            source=f"FGI grid substrate • {LATEST.name}",
            date_utc=snap.get("date"),
            generated_at=snap.get("generated_at"),
            feature_count=snap.get("feature_count", 0),
            mode="map",
            basis_type="derived_spatial_index",
        ),
    }


@router.get("/history")
def osi_history(days: int = Query(7, ge=1, le=60)):
    items: list[tuple[str, Path]] = []

    for p in GRID_DIR.glob("fgi_grid_*.geojson"):
        m = PAT.search(p.name)
        if m:
            items.append((m.group(1), p))

    items = sorted(items, key=lambda x: x[0], reverse=True)[:days]

    if not items:
        if not LATEST.exists():
            raise HTTPException(404, "No OSI history files found")

        fc = load_json(LATEST)
        generated_at = fc.get("generated_at") or file_generated_at_iso(LATEST)
        snap = build_snapshot_from_fc(fc, fallback_date=safe_date(generated_at), generated_at=generated_at, include_geojson=True)

        return {
            "ok": True,
            "mode": "latest-fallback",
            "days": int(days),
            "snapshots": [snap],
            "trust": _build_trust(
                source=f"FGI grid substrate • {LATEST.name}",
                date_utc=snap.get("date"),
                generated_at=snap.get("generated_at"),
                feature_count=snap.get("feature_count", 0),
                mode="history",
                basis_type="derived_spatial_index",
            ),
        }

    snapshots = []
    for d, p in items:
        fc = load_json(p)
        generated_at = fc.get("generated_at") or file_generated_at_iso(p)
        snap = build_snapshot_from_fc(fc, fallback_date=d, generated_at=generated_at, include_geojson=True)
        snapshots.append(snap)

    top = snapshots[0] if snapshots else {}
    return {
        "ok": True,
        "mode": "history-files",
        "days": int(days),
        "snapshots": snapshots,
        "trust": _build_trust(
            source=f"FGI grid substrate • {GRID_DIR.name}",
            date_utc=top.get("date"),
            generated_at=top.get("generated_at"),
            feature_count=top.get("feature_count", 0),
            mode="history",
            basis_type="derived_spatial_index",
        ),
    }
