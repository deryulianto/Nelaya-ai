from __future__ import annotations

from pathlib import Path
import json
import math
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]

CANDIDATE_FILES = {
    "small_islands": [
        ROOT / "data" / "reference" / "pulau_aceh.json",
    ],
    "ports": [
        ROOT / "data" / "reference" / "pelabuhan_aceh.json",
    ],
    "surf_spots": [
        ROOT / "data" / "reference" / "surf_spots_aceh.json",
    ],
    "rumpon": [
        ROOT / "data" / "reference" / "rumpon_aceh.json",
        ROOT / "data" / "rumpon_aceh.json",
    ],
    "fish": [
        ROOT / "data" / "reference" / "ikan_aceh.json",
        ROOT / "data" / "ikan_aceh.json",
    ],
}


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _load_first_existing(paths: List[Path]) -> List[Dict[str, Any]]:
    for p in paths:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    for key in ["items", "data", "rows", "features"]:
                        val = data.get(key)
                        if isinstance(val, list):
                            return val
                    return [data]
            except Exception:
                continue
    return []


def _pick_name(row: Dict[str, Any]) -> Optional[str]:
    for k in [
        "name",
        "nama",
        "nama_pulau",
        "pulau",
        "island_name",
        "nama_pelabuhan",
        "port_name",
        "spot_name",
        "nama_spot",
        "spot",
        "surf_spot",
        "location",
    ]:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _pick_region(row: Dict[str, Any]) -> Optional[str]:
    for k in [
        "kabupaten",
        "kab_kota",
        "kabupaten_kota",
        "wilayah",
        "region",
        "provinsi",
        "kota",
        "district",
        "area",
    ]:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _pick_latlon(row: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    lat_keys = ["lat", "latitude", "y"]
    lon_keys = ["lon", "lng", "longitude", "x"]

    lat = None
    lon = None

    for k in lat_keys:
        v = row.get(k)
        if v is not None:
            try:
                lat = float(v)
                break
            except Exception:
                pass

    for k in lon_keys:
        v = row.get(k)
        if v is not None:
            try:
                lon = float(v)
                break
            except Exception:
                pass

    if lat is None or lon is None:
        return None

    return (lat, lon)


def _dataset_rows(dataset: str) -> List[Dict[str, Any]]:
    return _load_first_existing(CANDIDATE_FILES.get(dataset, []))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _filter_rows_by_region(rows: List[Dict[str, Any]], region: Optional[str]) -> List[Dict[str, Any]]:
    if not region or _norm(region) in {"aceh", "provinsi aceh"}:
        return rows

    r = _norm(region)
    filtered = []

    for row in rows:
        try:
            raw_region = _pick_region(row)
            if not raw_region:
                continue
            row_region = _norm(raw_region)

            if r == row_region or r in row_region or row_region in r:
                filtered.append(row)
        except Exception:
            continue

    return filtered


def count_dataset(dataset: str, region: Optional[str] = None) -> Dict[str, Any]:
    rows = _dataset_rows(dataset)
    if not rows:
        return {"count": 0, "items": [], "region": region, "found": False}

    filtered = _filter_rows_by_region(rows, region)

    names = []
    for row in filtered:
        nm = _pick_name(row)
        if nm:
            names.append(nm)

    names = list(dict.fromkeys(names))

    return {
        "count": len(filtered),
        "items": names[:20],
        "region": region or "Aceh",
        "found": True,
    }


def list_dataset(dataset: str, region: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    rows = _dataset_rows(dataset)
    if not rows:
        return {"count": 0, "items": [], "region": region, "found": False}

    filtered = _filter_rows_by_region(rows, region)

    names = []
    for row in filtered:
        nm = _pick_name(row)
        if nm:
            names.append(nm)

    names = list(dict.fromkeys(names))

    return {
        "count": len(names),
        "items": names[:limit],
        "region": region or "Aceh",
        "found": True,
    }


def load_small_islands() -> List[Dict[str, Any]]:
    return _dataset_rows("small_islands")


def count_small_islands(region: Optional[str] = None) -> Dict[str, Any]:
    return count_dataset("small_islands", region)


def list_small_islands(region: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    return list_dataset("small_islands", region, limit=limit)


def resolve_region_center(region: Optional[str]) -> Optional[Tuple[float, float]]:
    """
    Cari titik representatif nyata dari sebuah region menggunakan dataset reference.
    Urutan:
    1. pulau
    2. pelabuhan
    3. surf spot
    """
    if not region:
        return None

    datasets = ["small_islands", "ports", "surf_spots"]
    points: List[Tuple[float, float]] = []

    for ds in datasets:
        rows = _filter_rows_by_region(_dataset_rows(ds), region)
        for row in rows:
            latlon = _pick_latlon(row)
            if latlon:
                points.append(latlon)

        if points:
            break

    if not points:
        return None

    mean_lat = sum(p[0] for p in points) / len(points)
    mean_lon = sum(p[1] for p in points) / len(points)
    return (round(mean_lat, 6), round(mean_lon, 6))


def find_nearest_ports(lat: float, lon: float, limit: int = 3) -> List[Dict[str, Any]]:
    rows = _dataset_rows("ports")
    results: List[Dict[str, Any]] = []

    for row in rows:
        try:
            latlon = _pick_latlon(row)
            if not latlon:
                continue

            plat, plon = latlon
            name = _pick_name(row)
            region = _pick_region(row)

            if not name:
                continue

            dist = haversine_km(lat, lon, plat, plon)
            results.append(
                {
                    "name": name,
                    "region": region,
                    "distance_km": round(dist, 2),
                    "lat": plat,
                    "lon": plon,
                }
            )
        except Exception:
            continue

    results.sort(key=lambda x: x["distance_km"])
    return results[:limit]


def find_nearest_surf_spots(lat: float, lon: float, limit: int = 3) -> List[Dict[str, Any]]:
    rows = _dataset_rows("surf_spots")
    results: List[Dict[str, Any]] = []

    for row in rows:
        try:
            latlon = _pick_latlon(row)
            if not latlon:
                continue

            slat, slon = latlon
            name = _pick_name(row)
            region = _pick_region(row)

            if not name:
                continue

            dist = haversine_km(lat, lon, slat, slon)
            results.append(
                {
                    "name": name,
                    "region": region,
                    "distance_km": round(dist, 2),
                    "lat": slat,
                    "lon": slon,
                }
            )
        except Exception:
            continue

    results.sort(key=lambda x: x["distance_km"])
    return results[:limit]