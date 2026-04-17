from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.services.behavior_today import get_behavior_today
from app.services.behavior_zones import compute_behavior_zones


ACEH_REF_POINTS = {
    "sabang": {"lat": 5.89, "lon": 95.32, "label": "Sekitar Sabang"},
    "simeulue": {"lat": 2.62, "lon": 96.08, "label": "Sekitar Simeulue"},
    "west_aceh": {"lat": 4.14, "lon": 96.13, "label": "Barat Aceh"},
    "south_aceh": {"lat": 3.16, "lon": 97.18, "label": "Selatan Aceh"},
    "malaka": {"lat": 5.30, "lon": 97.20, "label": "Arah Selat Malaka"},
    "hindia": {"lat": 4.60, "lon": 94.80, "label": "Arah Samudra Hindia"},
}


def _zone_role(rank: int) -> str:
    if rank == 1:
        return "primary"
    if rank == 2:
        return "alternatif"
    return "cadangan"


def _zone_type_from_radius(radius_km: float, point_count: int) -> str:
    if radius_km <= 15 and point_count <= 6:
        return "presisi"
    if radius_km <= 35:
        return "transisi"
    return "eksplorasi"


def _build_driver_list(component_means: Dict[str, float]) -> List[str]:
    drivers: List[str] = []

    chl = float(component_means.get("chl_score", 0.0))
    wind = float(component_means.get("wind_score", 0.0))
    wave = float(component_means.get("wave_score", 0.0))
    front = float(component_means.get("front_score", 0.0))
    stability = float(component_means.get("stability_score", 0.0))
    ssh = float(component_means.get("ssh_score", 0.0))
    sst = float(component_means.get("sst_score", 0.0))

    if chl >= 0.75:
        drivers.append("produktivitas tinggi")
    elif chl >= 0.5:
        drivers.append("produktivitas sedang")
    else:
        drivers.append("produktivitas lemah")

    if wind >= 0.75:
        drivers.append("angin mendukung")
    elif wind <= 0.3:
        drivers.append("angin kurang mendukung")
    else:
        drivers.append("angin moderat")

    if wave >= 0.75:
        drivers.append("gelombang mendukung")
    elif wave <= 0.3:
        drivers.append("gelombang kurang mendukung")
    else:
        drivers.append("gelombang moderat")

    if front >= 0.45:
        drivers.append("front cukup terbentuk")
    else:
        drivers.append("front lemah")

    if stability >= 0.7:
        drivers.append("kolom air stabil")
    else:
        drivers.append("kolom air kurang stabil")

    if ssh >= 0.3:
        drivers.append("ssh cukup mendukung")

    if sst >= 0.65:
        drivers.append("suhu mendekati optimum")
    elif sst <= 0.35:
        drivers.append("suhu kurang optimum")

    return drivers


def _direction_hint(center_lat: float, center_lon: float) -> str:
    candidates: List[Tuple[str, float]] = []
    for item in ACEH_REF_POINTS.values():
        d = ((center_lat - item["lat"]) ** 2 + (center_lon - item["lon"]) ** 2) ** 0.5
        candidates.append((item["label"], d))

    candidates.sort(key=lambda x: x[1])
    nearest_label = candidates[0][0] if candidates else "wilayah referensi Aceh"

    if center_lon < 95.4:
        return f"{nearest_label} / sisi Samudra Hindia"
    if center_lon > 97.0:
        return f"{nearest_label} / sisi timur Aceh"
    return nearest_label


def _confidence_score(
    *,
    mean_score: float,
    max_score: float,
    point_count: int,
    radius_km: float,
    component_means: Dict[str, float],
) -> float:
    front = float(component_means.get("front_score", 0.0))
    stability = float(component_means.get("stability_score", 0.0))
    wave = float(component_means.get("wave_score", 0.0))
    wind = float(component_means.get("wind_score", 0.0))

    point_factor = min(point_count / 12.0, 1.0)
    radius_penalty = min(radius_km / 80.0, 1.0)

    score = (
        0.34 * mean_score
        + 0.18 * max_score
        + 0.16 * front
        + 0.12 * stability
        + 0.10 * wave
        + 0.10 * wind
        + 0.08 * point_factor
        - 0.08 * radius_penalty
    )

    return max(0.0, min(1.0, score))


def _risk_level(component_means: Dict[str, float], radius_km: float, zone_type: str) -> str:
    wave = float(component_means.get("wave_score", 0.0))
    wind = float(component_means.get("wind_score", 0.0))
    front = float(component_means.get("front_score", 0.0))

    risk = 0

    if wave <= 0.35:
        risk += 2
    elif wave <= 0.55:
        risk += 1

    if wind <= 0.35:
        risk += 2
    elif wind <= 0.55:
        risk += 1

    if zone_type == "eksplorasi" and radius_km > 45:
        risk += 1

    if front < 0.2:
        risk += 1

    if risk >= 4:
        return "tinggi"
    if risk >= 2:
        return "sedang"
    return "rendah"


def _best_time_window(component_means: Dict[str, float], risk_level: str, zone_type: str) -> str:
    wave = float(component_means.get("wave_score", 0.0))
    wind = float(component_means.get("wind_score", 0.0))

    if risk_level == "tinggi":
        return "pagi singkat, hindari operasi terlalu jauh"
    if zone_type == "presisi":
        return "pagi hingga menjelang siang"
    if wave >= 0.75 and wind >= 0.75:
        return "pagi sampai sore awal"
    return "pagi hingga siang"


def _recommendation_text(
    zone_type: str,
    role: str,
    drivers: List[str],
    risk_level: str,
    best_time: str,
) -> str:
    if zone_type == "presisi":
        base = "Gunakan operasi lebih fokus pada radius kecil dan pertahankan akurasi posisi."
    elif zone_type == "transisi":
        base = "Gunakan pola pencarian menengah sambil memantau perubahan sinyal di sekitar zona."
    else:
        base = "Gunakan pola eksplorasi yang lebih luas karena hotspot cenderung menyebar."

    if role == "primary":
        prefix = "Zona ini menjadi prioritas utama hari ini. "
    elif role == "alternatif":
        prefix = "Zona ini layak menjadi alternatif utama. "
    else:
        prefix = "Zona ini lebih cocok sebagai cadangan operasi. "

    if "front lemah" in drivers:
        structure = "Struktur agregasi belum terlalu tajam, jadi jangan terlalu mengandalkan satu titik saja. "
    elif "front cukup terbentuk" in drivers:
        structure = "Struktur zona cukup terbentuk, sehingga peluang konsentrasi lebih baik. "
    else:
        structure = ""

    risk_text = f"Risiko operasional {risk_level}. Waktu yang paling masuk akal: {best_time}."

    return prefix + base + " " + structure + risk_text


def _overall_summary(
    zones: List[Dict[str, Any]],
    component_means: Dict[str, float],
) -> str:
    if not zones:
        return "Hari ini belum terbentuk zona operasi yang cukup kuat untuk direkomendasikan."

    primary = zones[0]
    drivers = primary.get("drivers", [])
    driver_text = ", ".join(drivers[:3]) if drivers else "sinyal gabungan laut"

    return (
        f"Zona utama hari ini berada di {primary.get('direction_hint', 'wilayah referensi Aceh')} "
        f"dengan karakter {primary.get('zone_type', 'transisi')}. "
        f"Radius operasional sekitar {float(primary.get('radius_km', 0.0)):.1f} km, "
        f"terbentuk dari {int(primary.get('point_count', 0))} titik hotspot, "
        f"dengan mean score {float(primary.get('mean_score', 0.0)):.3f}. "
        f"Tingkat keyakinan model sekitar {round(float(primary.get('confidence_score', 0.0)) * 100)}%, "
        f"dengan risiko operasional {primary.get('risk_level', 'sedang')}. "
        f"Zona ini terutama didukung oleh {driver_text}."
    )


def compute_behavior_decision(
    *,
    species: str = "medium_pelagic",
    hotspot_threshold: float = 0.55,
    top_k: int = 80,
    eps_km: float = 25.0,
    min_samples: int = 4,
) -> Dict[str, Any]:
    behavior = get_behavior_today(
        species=species,
        hotspot_threshold=hotspot_threshold,
        top_k=top_k,
    )

    zones_result = compute_behavior_zones(
        species=species,
        hotspot_threshold=hotspot_threshold,
        top_k=top_k,
        eps_km=eps_km,
        min_samples=min_samples,
    )

    zones = zones_result.get("zones", [])
    component_means = behavior.get("component_means", {})

    enriched_zones: List[Dict[str, Any]] = []
    for i, zone in enumerate(zones, start=1):
        radius_km = float(zone.get("radius_km", 0.0))
        point_count = int(zone.get("point_count", 0))
        mean_score = float(zone.get("mean_score", 0.0))
        max_score = float(zone.get("max_score", 0.0))

        zone_type = zone.get("zone_type") or _zone_type_from_radius(radius_km, point_count)
        role = _zone_role(i)
        direction_hint = zone.get("direction_hint") or _direction_hint(
            float(zone.get("center_lat", 0.0)),
            float(zone.get("center_lon", 0.0)),
        )

        drivers = _build_driver_list(component_means)
        confidence_score = _confidence_score(
            mean_score=mean_score,
            max_score=max_score,
            point_count=point_count,
            radius_km=radius_km,
            component_means=component_means,
        )
        risk_level = _risk_level(component_means, radius_km, zone_type)
        best_time = _best_time_window(component_means, risk_level, zone_type)
        recommendation = _recommendation_text(zone_type, role, drivers, risk_level, best_time)

        enriched = {
            **zone,
            "rank": i,
            "role": role,
            "zone_type": zone_type,
            "direction_hint": direction_hint,
            "drivers": drivers,
            "confidence_score": round(confidence_score, 3),
            "risk_level": risk_level,
            "best_time_window": best_time,
            "recommendation": recommendation,
        }
        enriched_zones.append(enriched)

    summary = _overall_summary(enriched_zones, component_means)
    primary_zone = enriched_zones[0] if enriched_zones else None

    return {
        "date": behavior.get("date"),
        "species": species,
        "summary": summary,
        "component_means": component_means,
        "primary_zone": primary_zone,
        "zone_count": len(enriched_zones),
        "zones": enriched_zones,
        "meta": {
            "hotspot_threshold": hotspot_threshold,
            "top_k": top_k,
            "eps_km": eps_km,
            "min_samples": min_samples,
        },
    }