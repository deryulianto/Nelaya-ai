from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional


def _direction_id(bearing: Optional[float]) -> str:
    if bearing is None:
        return "belum_terbaca"

    sectors = [
        ("utara", 337.5, 360.0),
        ("utara", 0.0, 22.5),
        ("timur_laut", 22.5, 67.5),
        ("timur", 67.5, 112.5),
        ("tenggara", 112.5, 157.5),
        ("selatan", 157.5, 202.5),
        ("barat_daya", 202.5, 247.5),
        ("barat", 247.5, 292.5),
        ("barat_laut", 292.5, 337.5),
    ]

    for label, low, high in sectors:
        if low <= bearing < high:
            return label

    return "belum_terbaca"


def _direction_label(direction_id: str) -> str:
    mapping = {
        "utara": "utara",
        "timur_laut": "timur laut",
        "timur": "timur",
        "tenggara": "tenggara",
        "selatan": "selatan",
        "barat_daya": "barat daya",
        "barat": "barat",
        "barat_laut": "barat laut",
        "belum_terbaca": "belum terbaca",
    }
    return mapping.get(direction_id, direction_id.replace("_", " "))


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def _bearing_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)

    y = math.sin(dlambda) * math.cos(phi2)
    x = (
        math.cos(phi1) * math.sin(phi2)
        - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    )

    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def _load_history(path: Path, species_group: str) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if isinstance(data, dict) and isinstance(data.get("species"), dict):
        arr = data["species"].get(species_group, [])
        if isinstance(arr, list):
            return arr

    if isinstance(data, dict):
        arr = data.get(species_group, [])
        if isinstance(arr, list):
            return arr

    return []


def _clean_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clean = []

    for e in entries:
        try:
            lat = float(e.get("lat"))
            lon = float(e.get("lon"))
        except Exception:
            continue

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue

        item = dict(e)
        item["lat"] = lat
        item["lon"] = lon
        clean.append(item)

    clean.sort(key=lambda x: (str(x.get("date", "")), str(x.get("snapshot_at", ""))))
    return clean


def _strength_label(distance_km: float) -> str:
    if distance_km < 2.0:
        return "sangat_lemah"
    if distance_km < 10.0:
        return "lemah"
    if distance_km < 30.0:
        return "sedang"
    return "kuat"


def build_hotspot_shift(data_dir: Path, species_group: str) -> Dict[str, Any]:
    """
    Membaca pergeseran centroid hotspot pelagis dari:
    data/fgi_movement/pelagic_centroid_history.json

    Catatan ilmiah:
    Ini membaca pergeseran pusat peluang FGI, bukan pelacakan ikan individu.
    """
    path = data_dir / "fgi_movement" / "pelagic_centroid_history.json"
    entries = _clean_entries(_load_history(path, species_group))

    if not entries:
        return {
            "available": False,
            "method": "primary_zone_centroid_shift",
            "reason": "Belum ada histori centroid hotspot pelagis.",
            "history_file": str(path),
        }

    latest = entries[-1]

    previous = None
    latest_date = latest.get("date")
    for e in reversed(entries[:-1]):
        if e.get("date") != latest_date:
            previous = e
            break

    latest_centroid = {
        "date": latest.get("date"),
        "lat": latest.get("lat"),
        "lon": latest.get("lon"),
        "mean_score": latest.get("mean_score"),
        "confidence_score": latest.get("confidence_score"),
        "risk_level": latest.get("risk_level"),
        "direction_hint": latest.get("direction_hint"),
        "source": latest.get("source"),
    }

    if previous is None:
        return {
            "available": False,
            "method": "primary_zone_centroid_shift",
            "reason": "Snapshot centroid hari ini sudah ada, tetapi belum ada tanggal pembanding sebelumnya.",
            "latest_centroid": latest_centroid,
            "history_count": len(entries),
            "history_file": str(path),
            "interpretation": "Sistem sudah menyimpan pusat peluang pelagis. Pergeseran baru bisa dihitung setelah ada minimal dua tanggal centroid berbeda.",
        }

    lat1 = float(previous["lat"])
    lon1 = float(previous["lon"])
    lat2 = float(latest["lat"])
    lon2 = float(latest["lon"])

    distance_km = _haversine_km(lat1, lon1, lat2, lon2)
    bearing_deg = _bearing_between(lat1, lon1, lat2, lon2)

    direction = _direction_id(bearing_deg)
    direction_label = _direction_label(direction)

    d1 = _parse_date(previous.get("date"))
    d2 = _parse_date(latest.get("date"))
    days_between = (d2 - d1).days if d1 and d2 else None

    strength = _strength_label(distance_km)

    previous_centroid = {
        "date": previous.get("date"),
        "lat": previous.get("lat"),
        "lon": previous.get("lon"),
        "mean_score": previous.get("mean_score"),
        "confidence_score": previous.get("confidence_score"),
        "risk_level": previous.get("risk_level"),
        "direction_hint": previous.get("direction_hint"),
        "source": previous.get("source"),
    }

    return {
        "available": True,
        "method": "primary_zone_centroid_shift",
        "latest_centroid": latest_centroid,
        "previous_centroid": previous_centroid,
        "distance_km": round(distance_km, 2),
        "bearing_deg": round(bearing_deg, 1),
        "direction": direction,
        "direction_label": direction_label,
        "strength": strength,
        "days_between": days_between,
        "history_count": len(entries),
        "history_file": str(path),
        "scientific_caution": "Ini adalah pergeseran pusat peluang/hotspot FGI, bukan pelacakan ikan individu.",
        "interpretation": (
            f"Pusat peluang pelagis bergeser sekitar {distance_km:.1f} km ke arah "
            f"{direction_label} dibanding snapshot sebelumnya."
        ),
    }



def _unique_latest_by_date(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ambil satu record terakhir untuk setiap tanggal.
    Ini mencegah duplikasi jika update script dijalankan beberapa kali pada tanggal yang sama.
    """
    by_date: Dict[str, Dict[str, Any]] = {}

    for e in entries:
        d = str(e.get("date", ""))
        if not d:
            continue
        by_date[d] = e

    out = list(by_date.values())
    out.sort(key=lambda x: str(x.get("date", "")))
    return out


def _angle_diff_deg(a: float, b: float) -> float:
    """
    Selisih sudut terkecil dalam derajat.
    """
    return abs((a - b + 180.0) % 360.0 - 180.0)


def build_movement_memory(
    data_dir: Path,
    species_group: str,
    window_days: int = 3,
) -> Dict[str, Any]:
    """
    Membaca memori arah pergeseran hotspot pelagis dalam window tertentu.

    Catatan ilmiah:
    - Ini membaca konsistensi pergeseran pusat peluang FGI.
    - Ini bukan pelacakan individu ikan.
    - Butuh minimal 3 tanggal centroid berbeda agar tidak halu.
    """
    path = data_dir / "fgi_movement" / "pelagic_centroid_history.json"
    entries = _clean_entries(_load_history(path, species_group))
    entries = _unique_latest_by_date(entries)

    if len(entries) < window_days:
        return {
            "available": False,
            "method": "centroid_direction_consistency",
            "window_days": window_days,
            "history_count": len(entries),
            "min_required": window_days,
            "reason": (
                f"Butuh minimal {window_days} tanggal centroid berbeda untuk membaca "
                f"konsistensi arah gerak {window_days} hari."
            ),
            "history_file": str(path),
            "scientific_caution": "Movement memory tidak dibuat dari data palsu. Sistem menunggu histori alami dari pipeline harian.",
        }

    window = entries[-window_days:]

    segments: List[Dict[str, Any]] = []
    total_distance = 0.0
    x_sum = 0.0
    y_sum = 0.0

    for prev, curr in zip(window[:-1], window[1:]):
        lat1 = float(prev["lat"])
        lon1 = float(prev["lon"])
        lat2 = float(curr["lat"])
        lon2 = float(curr["lon"])

        dist = _haversine_km(lat1, lon1, lat2, lon2)
        bearing = _bearing_between(lat1, lon1, lat2, lon2)
        direction = _direction_id(bearing)
        direction_label = _direction_label(direction)

        total_distance += dist

        # Resultant vector berbobot jarak.
        rad = math.radians(bearing)
        x_sum += math.sin(rad) * dist
        y_sum += math.cos(rad) * dist

        segments.append(
            {
                "from_date": prev.get("date"),
                "to_date": curr.get("date"),
                "from_centroid": {
                    "lat": prev.get("lat"),
                    "lon": prev.get("lon"),
                },
                "to_centroid": {
                    "lat": curr.get("lat"),
                    "lon": curr.get("lon"),
                },
                "distance_km": round(dist, 2),
                "bearing_deg": round(bearing, 1),
                "direction": direction,
                "direction_label": direction_label,
            }
        )

    if total_distance <= 0:
        return {
            "available": False,
            "method": "centroid_direction_consistency",
            "window_days": window_days,
            "history_count": len(entries),
            "reason": "Histori cukup, tetapi total pergeseran centroid terlalu kecil untuk membaca arah dominan.",
            "segments": segments,
            "history_file": str(path),
        }

    dominant_bearing = (math.degrees(math.atan2(x_sum, y_sum)) + 360.0) % 360.0
    dominant_direction = _direction_id(dominant_bearing)
    dominant_direction_label = _direction_label(dominant_direction)

    resultant_distance = math.sqrt(x_sum * x_sum + y_sum * y_sum)
    consistency_score = resultant_distance / total_distance if total_distance > 0 else 0.0

    if consistency_score >= 0.75:
        consistency_label = "kuat"
    elif consistency_score >= 0.5:
        consistency_label = "sedang"
    elif consistency_score >= 0.3:
        consistency_label = "lemah"
    else:
        consistency_label = "tidak_konsisten"

    latest = window[-1]
    earliest = window[0]

    net_distance = _haversine_km(
        float(earliest["lat"]),
        float(earliest["lon"]),
        float(latest["lat"]),
        float(latest["lon"]),
    )

    return {
        "available": True,
        "method": "centroid_direction_consistency",
        "window_days": window_days,
        "history_count": len(entries),
        "window_dates": [e.get("date") for e in window],
        "dominant_direction": dominant_direction,
        "dominant_direction_label": dominant_direction_label,
        "dominant_bearing_deg": round(dominant_bearing, 1),
        "consistency_label": consistency_label,
        "consistency_score": round(consistency_score, 3),
        "total_segment_distance_km": round(total_distance, 2),
        "net_distance_km": round(net_distance, 2),
        "segments": segments,
        "latest_centroid": {
            "date": latest.get("date"),
            "lat": latest.get("lat"),
            "lon": latest.get("lon"),
            "mean_score": latest.get("mean_score"),
            "confidence_score": latest.get("confidence_score"),
            "risk_level": latest.get("risk_level"),
            "direction_hint": latest.get("direction_hint"),
        },
        "history_file": str(path),
        "scientific_caution": "Ini membaca konsistensi pergeseran pusat peluang FGI, bukan pelacakan individu ikan.",
        "interpretation": (
            f"Dalam jendela {window_days} hari, pusat peluang pelagis cenderung "
            f"bergerak ke arah {dominant_direction_label} dengan konsistensi "
            f"{consistency_label}."
        ),
    }



def build_front_signal(data_dir: Path, species_group: str) -> Dict[str, Any]:
    """
    v0.5A — Front Signal konservatif.

    Membaca sinyal front dari drivers pada centroid primary_zone yang disimpan
    dari endpoint FGI behavior/decision.

    Catatan:
    Ini belum menghitung front spasial penuh dari gradien SST–CHL–SSH.
    Ini adalah indikator awal berbasis hasil behavior engine.
    """
    path = data_dir / "fgi_movement" / "pelagic_centroid_history.json"
    entries = _clean_entries(_load_history(path, species_group))
    entries = _unique_latest_by_date(entries)

    if not entries:
        return {
            "available": False,
            "method": "behavior_driver_front_signal",
            "reason": "Belum ada histori centroid untuk membaca sinyal front.",
            "history_file": str(path),
        }

    latest = entries[-1]
    drivers = latest.get("drivers") or []

    if not isinstance(drivers, list):
        drivers = []

    driver_text = " | ".join(str(x).lower() for x in drivers)

    status = "unknown"
    label = "belum terbaca"
    score = 0.4

    if "front kuat" in driver_text or "front tajam" in driver_text:
        status = "strong"
        label = "front kuat"
        score = 0.8
    elif "front sedang" in driver_text or "front cukup" in driver_text:
        status = "moderate"
        label = "front sedang"
        score = 0.65
    elif "front lemah" in driver_text:
        status = "weak"
        label = "front lemah"
        score = 0.45
    elif "front" in driver_text:
        status = "detected_unspecified"
        label = "front terdeteksi"
        score = 0.55

    if status == "unknown":
        interpretation = (
            "Sinyal front belum terbaca jelas dari drivers FGI behavior. "
            "Untuk pembacaan lebih kuat, diperlukan gradien spasial SST–CHL–SSH."
        )
    elif status == "weak":
        interpretation = (
            "Sinyal front terbaca lemah. Zona peluang masih dapat terbentuk oleh produktivitas, "
            "arus, dan stabilitas kolom air, tetapi agregasi pada batas massa air belum tajam."
        )
    elif status == "moderate":
        interpretation = (
            "Sinyal front sedang. Ini dapat mendukung agregasi pelagis pada zona transisi, "
            "tetapi tetap perlu dibaca bersama arus, CHL, SST, SSH, dan validasi lapangan."
        )
    elif status == "strong":
        interpretation = (
            "Sinyal front kuat. Zona transisi massa air berpotensi menjadi area agregasi pelagis, "
            "tetapi informasi ini tetap bukan kepastian keberadaan ikan."
        )
    else:
        interpretation = (
            "Ada indikasi front dalam drivers FGI behavior, tetapi kekuatannya belum diklasifikasikan."
        )

    return {
        "available": status != "unknown",
        "method": "behavior_driver_front_signal",
        "status": status,
        "label": label,
        "score": score,
        "source_date": latest.get("date"),
        "source": latest.get("source"),
        "drivers": drivers,
        "history_file": str(path),
        "scientific_caution": (
            "Ini adalah sinyal front konservatif dari behavior engine FGI, "
            "belum hasil perhitungan gradien spasial penuh SST–CHL–SSH."
        ),
        "interpretation": interpretation,
    }
