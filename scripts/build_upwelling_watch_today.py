#!/usr/bin/env python3
"""
Build Upwelling Watch / UPI v0.1 for NELAYA-AI.

Scientific position:
- This is an indicator of potential upwelling based on surface ocean proxies.
- It is not definitive proof of upwelling without vertical profile, nutrient, or field validation.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import xarray as xr


BASE_DIR = Path.home() / "NELAYA-AI-LAB"
RAW_DIR = BASE_DIR / "data" / "raw"
OUT_DIR = BASE_DIR / "data" / "upwelling"
OUT_JSON = OUT_DIR / "upwelling_watch_today.json"
OUT_GEOJSON = OUT_DIR / "upwelling_candidates_today.geojson"

REGION_NAME = "Aceh"

UPI_VERSION = "0.3"
MAX_CANDIDATE_LOCATIONS = 10
INTERPRETATION_RADIUS_KM = 15


CORE_UPWELLING_COMPONENTS = {
    "sst_cooling",
    "chl_enhancement",
    "current_divergence",
    "ssh_low",
}

VAR_CANDIDATES = {
    "lat": ["lat", "latitude", "nav_lat"],
    "lon": ["lon", "longitude", "nav_lon"],
    "sst": ["sst", "analysed_sst", "sea_surface_temperature", "thetao", "temperature"],
    "chl": ["chl", "chlor_a", "CHL", "chl_ocx", "mass_concentration_of_chlorophyll_a_in_sea_water"],
    "u_current": ["uo", "u", "eastward_sea_water_velocity", "water_u"],
    "v_current": ["vo", "v", "northward_sea_water_velocity", "water_v"],
    "ssh": ["zos", "adt", "sla", "ssh", "sea_surface_height_above_geoid"],
    "u_wind": ["u10", "eastward_wind", "uwnd", "wind_u"],
    "v_wind": ["v10", "northward_wind", "vwnd", "wind_v"],
    "bathy": ["elevation", "depth", "z", "Band1"],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def find_latest_file(keywords: List[str], root: Path = RAW_DIR) -> Optional[Path]:
    """
    Find latest NetCDF-like file containing any keyword in filename/path.
    """
    if not root.exists():
        return None

    candidates: List[Path] = []
    suffixes = {".nc", ".nc4", ".cdf", ".netcdf"}

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in suffixes:
            continue
        text = str(p).lower()
        if any(k.lower() in text for k in keywords):
            candidates.append(p)

    if not candidates:
        return None

    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return candidates[0]


def find_optional_bathy() -> Optional[Path]:
    possible_roots = [
        BASE_DIR / "data" / "bathymetry",
        BASE_DIR / "data" / "raw",
        BASE_DIR / "data",
    ]
    keywords = ["gebco", "bathy", "bathymetry", "depth"]

    candidates: List[Path] = []
    for root in possible_roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".nc", ".nc4", ".cdf", ".netcdf"}:
                continue
            text = str(p).lower()
            if any(k in text for k in keywords):
                candidates.append(p)

    if not candidates:
        return None

    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return candidates[0]


def pick_var(ds: xr.Dataset, names: List[str]) -> Optional[str]:
    for name in names:
        if name in ds.variables:
            return name
    for v in ds.data_vars:
        low = v.lower()
        if any(name.lower() == low for name in names):
            return v
    for v in ds.data_vars:
        low = v.lower()
        if any(name.lower() in low for name in names):
            return v
    return None


def pick_coord(ds: xr.Dataset, kind: str) -> Optional[str]:
    names = VAR_CANDIDATES[kind]
    for name in names:
        if name in ds.coords or name in ds.variables:
            return name
    return None


def squeeze_latest(da: xr.DataArray) -> xr.DataArray:
    """
    Pick latest time/depth slice and squeeze to 2D if needed.
    """
    for dim in list(da.dims):
        low = dim.lower()
        if "time" in low:
            da = da.isel({dim: -1})
        elif low in ["depth", "deptht", "lev", "level", "z"]:
            da = da.isel({dim: 0})
    return da.squeeze(drop=True)


def open_field(path: Optional[Path], field_key: str) -> Tuple[Optional[xr.DataArray], Optional[str]]:
    if path is None:
        return None, None

    try:
        ds = xr.open_dataset(path)
        var = pick_var(ds, VAR_CANDIDATES[field_key])
        if var is None:
            return None, str(path)

        da = squeeze_latest(ds[var])

        lat_name = pick_coord(ds, "lat")
        lon_name = pick_coord(ds, "lon")

        if lat_name and lon_name:
            if lat_name in ds.variables and lat_name not in da.coords:
                da = da.assign_coords({lat_name: ds[lat_name]})
            if lon_name in ds.variables and lon_name not in da.coords:
                da = da.assign_coords({lon_name: ds[lon_name]})

        return da, str(path)

    except Exception:
        return None, str(path)


def coord_names(da: xr.DataArray) -> Tuple[Optional[str], Optional[str]]:
    lat_name = None
    lon_name = None
    for c in list(da.coords) + list(da.dims):
        low = str(c).lower()
        if low in ["lat", "latitude", "nav_lat"] or "lat" == low:
            lat_name = str(c)
        if low in ["lon", "longitude", "nav_lon"] or "lon" == low:
            lon_name = str(c)
    return lat_name, lon_name


def normalize_lon(da: xr.DataArray) -> xr.DataArray:
    lat_name, lon_name = coord_names(da)
    if lon_name is None:
        return da

    lon = da[lon_name]
    try:
        if float(lon.max()) > 180:
            da = da.assign_coords({lon_name: (((lon + 180) % 360) - 180)})
            da = da.sortby(lon_name)
    except Exception:
        pass
    return da


def to_celsius_if_needed(da: xr.DataArray) -> xr.DataArray:
    arr = da.values
    finite = np.isfinite(arr)
    if finite.any():
        med = float(np.nanmedian(arr))
        if med > 100:
            da = da - 273.15
    return da


def align_to_ref(da: Optional[xr.DataArray], ref: xr.DataArray) -> Optional[xr.DataArray]:
    if da is None:
        return None

    da = normalize_lon(da)
    ref = normalize_lon(ref)

    ref_lat, ref_lon = coord_names(ref)
    da_lat, da_lon = coord_names(da)

    if ref_lat is None or ref_lon is None or da_lat is None or da_lon is None:
        return da

    try:
        # Rename to common names for interpolation.
        da2 = da
        ref2 = ref
        if da_lat != "lat":
            da2 = da2.rename({da_lat: "lat"})
        if da_lon != "lon":
            da2 = da2.rename({da_lon: "lon"})
        if ref_lat != "lat":
            ref2 = ref2.rename({ref_lat: "lat"})
        if ref_lon != "lon":
            ref2 = ref2.rename({ref_lon: "lon"})

        da2 = da2.interp(lat=ref2["lat"], lon=ref2["lon"], method="linear")
        return da2
    except Exception:
        return da


def robust_score_high(values: np.ndarray, p_low: float = 20, p_high: float = 90) -> np.ndarray:
    """
    Higher original value -> higher score 0..100.
    """
    arr = values.astype(float)
    finite = np.isfinite(arr)
    out = np.full_like(arr, np.nan, dtype=float)

    if finite.sum() < 10:
        return out

    lo = np.nanpercentile(arr, p_low)
    hi = np.nanpercentile(arr, p_high)

    if not np.isfinite(lo) or not np.isfinite(hi) or abs(hi - lo) < 1e-12:
        return out

    out[finite] = 100.0 * (arr[finite] - lo) / (hi - lo)
    return np.clip(out, 0, 100)


def robust_score_low(values: np.ndarray, p_low: float = 10, p_high: float = 75) -> np.ndarray:
    """
    Lower original value -> higher score 0..100.
    Useful for cold SST and low SSH.
    """
    arr = values.astype(float)
    finite = np.isfinite(arr)
    out = np.full_like(arr, np.nan, dtype=float)

    if finite.sum() < 10:
        return out

    lo = np.nanpercentile(arr, p_low)
    hi = np.nanpercentile(arr, p_high)

    if not np.isfinite(lo) or not np.isfinite(hi) or abs(hi - lo) < 1e-12:
        return out

    out[finite] = 100.0 * (hi - arr[finite]) / (hi - lo)
    return np.clip(out, 0, 100)


def current_divergence_score(
    u_da: Optional[xr.DataArray],
    v_da: Optional[xr.DataArray],
    ref: xr.DataArray,
) -> Optional[np.ndarray]:
    if u_da is None or v_da is None:
        return None

    u = align_to_ref(u_da, ref)
    v = align_to_ref(v_da, ref)

    if u is None or v is None:
        return None

    if "lat" not in u.coords or "lon" not in u.coords:
        return None

    try:
        u_arr = np.array(u.values, dtype=float)
        v_arr = np.array(v.values, dtype=float)

        lat = np.array(u["lat"].values, dtype=float)
        lon = np.array(u["lon"].values, dtype=float)

        if u_arr.ndim != 2 or v_arr.ndim != 2:
            return None

        earth_r = 6_371_000.0
        lat_rad = np.deg2rad(lat)
        lon_rad = np.deg2rad(lon)

        # Approximate spacing.
        dy = np.gradient(lat_rad) * earth_r
        dx_1d = np.gradient(lon_rad) * earth_r

        coslat = np.cos(lat_rad)
        dx = np.outer(coslat, dx_1d)
        dy2 = np.outer(dy, np.ones_like(lon))

        du_dx = np.gradient(u_arr, axis=1) / dx
        dv_dy = np.gradient(v_arr, axis=0) / dy2

        div = du_dx + dv_dy

        # Positive divergence = surface water spreading out, one proxy for upward compensation.
        score = robust_score_high(div, 60, 95)
        return score

    except Exception:
        return None


def bathy_score(bathy_da: Optional[xr.DataArray], ref: xr.DataArray) -> Optional[np.ndarray]:
    if bathy_da is None:
        return None

    b = align_to_ref(bathy_da, ref)
    if b is None:
        return None

    try:
        arr = np.array(b.values, dtype=float)
        if arr.ndim != 2:
            return None

        # GEBCO elevation is usually negative at sea.
        depth = np.where(arr < 0, -arr, arr)
        depth = np.where(depth < 0, np.nan, depth)

        # Shelf/slope-friendly depth band.
        depth_component = 100.0 * np.exp(-((depth - 250.0) ** 2) / (2 * 300.0**2))
        depth_component = np.clip(depth_component, 0, 100)

        gy, gx = np.gradient(depth)
        slope = np.sqrt(gx**2 + gy**2)
        slope_component = robust_score_high(slope, 50, 95)

        score = np.nanmean(np.stack([0.6 * depth_component, 0.4 * slope_component]), axis=0)
        return np.clip(score, 0, 100)

    except Exception:
        return None


def get_lat_lon_arrays(ref: xr.DataArray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    if "lat" not in ref.coords or "lon" not in ref.coords:
        return None, None

    lat = np.array(ref["lat"].values, dtype=float)
    lon = np.array(ref["lon"].values, dtype=float)

    if lat.ndim == 1 and lon.ndim == 1:
        lon2, lat2 = np.meshgrid(lon, lat)
        return lat2, lon2

    return lat, lon


def zone_label(lat: float, lon: float) -> str:
    """
    Aceh-oriented marine zone heuristic.
    Ini masih label geografis sederhana, bukan polygon administratif final.
    Nanti bisa ditingkatkan dengan shapefile garis pantai/pulau.
    """

    # Selatan dan barat daya Aceh, termasuk sekitar Simeulue dan Samudra Hindia.
    if lat < 2.3 and 95.5 <= lon <= 98.5:
        return "Selatan Simeulue / Samudra Hindia"

    if lat < 3.8 and lon < 95.5:
        return "Barat–Selatan Aceh / Samudra Hindia"

    # Barat-utara Aceh, perairan Samudra Hindia sisi barat daratan Aceh.
    if 3.8 <= lat < 5.3 and lon < 96.0:
        return "Barat–Utara Aceh / Samudra Hindia"

    # Sabang, Pulau Weh, Aceh Besar bagian utara.
    if lat >= 5.3 and 94.8 <= lon <= 96.4:
        return "Aceh Besar–Sabang–Pulau Weh"

    # Utara-timur Aceh sampai Selat Malaka.
    if lat >= 4.0 and lon > 96.0:
        return "Utara–Timur Aceh / Selat Malaka"

    # Area transisi barat-laut.
    if lat >= 5.0 and lon < 94.8:
        return "Barat Laut Aceh / Samudra Hindia"

    # Area transisi tengah laut, bukan Aceh Tengah daratan.
    return "Perairan transisi Aceh"


def summarize_top_cells(
    upi: np.ndarray,
    lat2: Optional[np.ndarray],
    lon2: Optional[np.ndarray],
    component_maps: Dict[str, Optional[np.ndarray]],
    top_k: int = 12,
) -> List[Dict[str, Any]]:
    if lat2 is None or lon2 is None:
        return []

    finite = np.isfinite(upi) & np.isfinite(lat2) & np.isfinite(lon2)
    if finite.sum() == 0:
        return []

    flat_idx = np.argsort(np.where(finite, upi, -9999).ravel())[::-1]
    rows = []

    used = 0
    for idx in flat_idx:
        if used >= top_k:
            break

        iy, ix = np.unravel_index(idx, upi.shape)
        score = float(upi[iy, ix])

        if not np.isfinite(score):
            continue

        lat = float(lat2[iy, ix])
        lon = float(lon2[iy, ix])

        cell = {
            "rank": used + 1,
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "upi_score": round(score, 1),
            "zone_label": zone_label(lat, lon),
            "components": {},
        }

        for name, arr in component_maps.items():
            if arr is not None and arr.shape == upi.shape and np.isfinite(arr[iy, ix]):
                cell["components"][name] = round(float(arr[iy, ix]), 1)

        rows.append(cell)
        used += 1

    return rows


def aggregate_zones(top_cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_zone: Dict[str, List[float]] = {}
    for c in top_cells:
        z = c["zone_label"]
        by_zone.setdefault(z, []).append(float(c["upi_score"]))

    zones = []
    for z, vals in by_zone.items():
        zones.append({
            "zone_label": z,
            "mean_top_score": round(float(np.mean(vals)), 1),
            "max_score": round(float(np.max(vals)), 1),
            "top_cell_count": len(vals),
        })

    zones.sort(key=lambda x: x["mean_top_score"], reverse=True)
    return zones


def level_from_score(score: Optional[float]) -> Dict[str, str]:
    if score is None or not np.isfinite(score):
        return {
            "level": "unavailable",
            "label": "Belum tersedia",
            "message": "Data belum cukup untuk membaca indikasi potensi upwelling.",
        }

    if score >= 85:
        return {
            "level": "very_strong_watch",
            "label": "Sinyal sangat kuat, belum konklusif",
            "message": (
                "Kombinasi sinyal permukaan sangat mendukung potensi upwelling "
                "atau proses pengayaan/mixing lokal. Tetap perlu validasi vertikal, "
                "nutrien, atau data lapangan."
            ),
        }
    if score >= 70:
        return {
            "level": "strong_watch",
            "label": "Indikasi kuat, perlu verifikasi",
            "message": (
                "Beberapa sinyal utama mendukung potensi upwelling, tetapi hasil ini "
                "tetap dibaca sebagai indikasi awal."
            ),
        }
    if score >= 50:
        return {
            "level": "moderate_watch",
            "label": "Indikasi sedang",
            "message": "Ada sinyal yang perlu dipantau, tetapi belum cukup kuat untuk disimpulkan.",
        }
    if score >= 30:
        return {
            "level": "weak_watch",
            "label": "Perlu dipantau",
            "message": "Sinyal upwelling masih lemah atau parsial.",
        }
    return {
        "level": "low_signal",
        "label": "Belum terlihat kuat",
        "message": "Belum terlihat kombinasi sinyal permukaan yang kuat.",
    }

def build_interpretation_note(max_score: Optional[float], confidence: float) -> str:
    if max_score is None or not np.isfinite(max_score):
        return (
            "UPI belum dapat ditafsirkan karena data utama belum cukup. "
            "Hasil perlu menunggu pembaruan data berikutnya."
        )

    base = (
        "Skor UPI adalah skor relatif 0–100 terhadap grid dan data yang tersedia pada hari ini. "
        "Skor tinggi tidak berarti peluang upwelling 100%, melainkan menunjukkan lokasi dengan "
        "kombinasi sinyal permukaan paling kuat dibanding area lain yang dibaca NELAYA-AI."
    )

    if confidence >= 0.8:
        conf = "Tingkat keyakinan data cukup baik karena sebagian besar komponen utama tersedia."
    elif confidence >= 0.6:
        conf = "Tingkat keyakinan data sedang karena beberapa komponen tersedia, tetapi belum lengkap."
    else:
        conf = "Tingkat keyakinan data terbatas karena komponen pendukung belum lengkap."

    return f"{base} {conf}"


def build_component_diagnostic_note(top_cells: List[Dict[str, Any]]) -> str:
    if not top_cells:
        return "Belum ada sel prioritas yang cukup untuk membaca komposisi sinyal."

    comps = top_cells[0].get("components", {})

    core_support = int(float(comps.get("core_support_count", 0) or 0))
    evidence_count = int(float(comps.get("evidence_component_count", 0) or 0))
    coverage_percent = float(comps.get("coverage_percent", 0) or 0)

    if core_support >= 4:
        return (
            "Sinyal teratas didukung oleh empat komponen inti: pendinginan SST, peningkatan chlorophyll-a, "
            "divergensi arus, dan sinyal SSH. Ini merupakan indikasi kuat, tetapi tetap belum konklusif "
            "tanpa validasi vertikal atau lapangan."
        )

    if core_support == 3:
        return (
            "Sinyal teratas didukung oleh tiga komponen inti. Ini cukup menarik untuk dipantau sebagai "
            "indikasi potensi upwelling atau proses pengayaan/mixing lokal."
        )

    if core_support == 2:
        return (
            "Sinyal teratas didukung oleh dua komponen inti. Ini dapat dibaca sebagai indikasi sedang, "
            "tetapi belum cukup untuk disebut kuat."
        )

    if core_support == 1:
        return (
            f"Sinyal teratas baru didukung oleh satu komponen inti dengan cakupan bukti sekitar "
            f"{coverage_percent:.1f}%. Ini lebih tepat dibaca sebagai sinyal awal, misalnya pendinginan SST, "
            "bukan bukti kuat upwelling aktif."
        )

    if evidence_count > 0:
        return (
            "Ada beberapa sinyal permukaan, tetapi belum ada komponen inti yang cukup kuat. "
            "Hasil ini sebaiknya dibaca sebagai pantauan awal."
        )

    return (
        "Sinyal masih parsial. Perlu dilihat kembali apakah pendinginan SST, peningkatan chlorophyll-a, "
        "divergensi arus, dan SSH saling mendukung."
    )

def evidence_color(level: str) -> str:
    colors = {
        "sangat_kuat_belum_konklusif": "#22d3ee",
        "kuat_perlu_verifikasi": "#34d399",
        "sedang_perlu_dipantau": "#fbbf24",
        "awal_parsial": "#94a3b8",
        "lemah": "#64748b",
    }
    return colors.get(level, "#94a3b8")


def build_candidate_geojson(candidate_locations: List[Dict[str, Any]]) -> Dict[str, Any]:
    features = []

    for c in candidate_locations:
        lat = c.get("lat")
        lon = c.get("lon")

        if lat is None or lon is None:
            continue

        level = c.get("evidence_level") or "awal_parsial"

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(lon), float(lat)],
            },
            "properties": {
                "rank": c.get("rank"),
                "coordinate_text": c.get("coordinate_text"),
                "zone_label": c.get("zone_label"),
                "upi_score": c.get("upi_score"),
                "evidence_level": level,
                "evidence_label": c.get("evidence_label"),
                "core_support_text": c.get("core_support_text"),
                "coverage_percent": c.get("coverage_percent"),
                "interpretation_radius_km": c.get("interpretation_radius_km"),
                "interpretation": c.get("interpretation"),
                "strong_drivers": ", ".join(
                    (c.get("drivers") or {}).get("strong_drivers") or []
                ),
                "marker_color": evidence_color(level),
            },
        })

    return {
        "type": "FeatureCollection",
        "name": "NELAYA-AI Upwelling Candidate Locations",
        "generated_at": now_iso(),
        "version": UPI_VERSION,
        "features": features,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    files = {
        "sst": find_latest_file(["sst", "thetao", "temperature"]),
        "chl": find_latest_file(["chl", "chlor", "ocx"]),
        "current": find_latest_file(["current", "curr", "uo", "vo", "phy-cur"]),
        "ssh": find_latest_file(["ssh", "zos", "adt", "sla", "phy"]),
        "wind": find_latest_file(["wind", "u10", "v10"]),
        "bathy": find_optional_bathy(),
    }

    sst_da, sst_file = open_field(files["sst"], "sst")
    if sst_da is None:
        payload = {
            "module": "upwelling_watch",
            "version": UPI_VERSION,
            "region": REGION_NAME,
            "generated_at": now_iso(),
            "available": False,
            "reason": "SST tidak tersedia. UPI membutuhkan SST sebagai grid referensi utama.",
            "data_files_used": {k: str(v) if v else None for k, v in files.items()},
        }
        OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

        geojson = build_candidate_geojson(payload.get("candidate_locations", []))
        OUT_GEOJSON.write_text(json.dumps(geojson, indent=2, ensure_ascii=False))
        print(f"Wrote: {OUT_JSON}")
        print(f"Wrote: {OUT_GEOJSON}")
        return

    sst_da = normalize_lon(to_celsius_if_needed(sst_da))

    # Normalize ref coord names.
    lat_name, lon_name = coord_names(sst_da)
    if lat_name and lat_name != "lat":
        sst_da = sst_da.rename({lat_name: "lat"})
    if lon_name and lon_name != "lon":
        sst_da = sst_da.rename({lon_name: "lon"})

    chl_da, chl_file = open_field(files["chl"], "chl")
    u_da, current_file_u = open_field(files["current"], "u_current")
    v_da, current_file_v = open_field(files["current"], "v_current")
    ssh_da, ssh_file = open_field(files["ssh"], "ssh")
    u_wind_da, wind_file_u = open_field(files["wind"], "u_wind")
    v_wind_da, wind_file_v = open_field(files["wind"], "v_wind")
    bathy_da, bathy_file = open_field(files["bathy"], "bathy")

    # Component 1: cold SST signal.
    sst_arr = np.array(sst_da.values, dtype=float)
    sst_score = robust_score_low(sst_arr, 10, 75)

    # Component 2: high CHL signal, log-scaled.
    chl_score = None
    if chl_da is not None:
        chl_aligned = align_to_ref(chl_da, sst_da)
        if chl_aligned is not None:
            chl_arr = np.array(chl_aligned.values, dtype=float)
            chl_arr = np.where(chl_arr > 0, chl_arr, np.nan)
            chl_score = robust_score_high(np.log1p(chl_arr), 20, 90)

    # Component 3: current divergence proxy.
    div_score = current_divergence_score(u_da, v_da, sst_da)

    # Component 4: low SSH signal.
    ssh_score = None
    if ssh_da is not None:
        ssh_aligned = align_to_ref(ssh_da, sst_da)
        if ssh_aligned is not None:
            ssh_arr = np.array(ssh_aligned.values, dtype=float)
            ssh_score = robust_score_low(ssh_arr, 10, 75)

    # Component 5: bathymetry/slope friendliness.
    bathy_component = bathy_score(bathy_da, sst_da)

    # Diagnostic wind magnitude, not included in UPI v0.1 weight unless later refined into Ekman.
    wind_mag_score = None
    if u_wind_da is not None and v_wind_da is not None:
        uw = align_to_ref(u_wind_da, sst_da)
        vw = align_to_ref(v_wind_da, sst_da)
        if uw is not None and vw is not None:
            wind_mag = np.sqrt(np.array(uw.values, dtype=float) ** 2 + np.array(vw.values, dtype=float) ** 2)
            wind_mag_score = robust_score_high(wind_mag, 30, 90)

    weighted_components = {
        "sst_cooling": {"weight": 0.35, "score": sst_score},
        "chl_enhancement": {"weight": 0.25, "score": chl_score},
        "current_divergence": {"weight": 0.20, "score": div_score},
        "ssh_low": {"weight": 0.10, "score": ssh_score},
        "bathymetry_slope": {"weight": 0.10, "score": bathy_component},
    }

        # ------------------------------------------------------------------
    # Evidence-gated UPI v0.1c
    # ------------------------------------------------------------------
    # Masalah v0.1:
    # Jika hanya 1 komponen valid, misalnya SST cooling saja, raw score bisa menjadi 100.
    # Itu terlalu optimistis untuk klaim upwelling.
    #
    # Solusi v0.1c:
    # 1. Hitung raw relative signal.
    # 2. Kalikan dengan coverage_ratio berdasarkan bobot komponen yang benar-benar tersedia.
    # 3. Batasi skor berdasarkan jumlah komponen inti yang kuat.
    # ------------------------------------------------------------------

    designed_total_weight = sum(float(v["weight"]) for v in weighted_components.values())

    numerator = np.zeros_like(sst_arr, dtype=float)
    present_weight = np.zeros_like(sst_arr, dtype=float)

    evidence_component_count = np.zeros_like(sst_arr, dtype=float)
    core_support_count = np.zeros_like(sst_arr, dtype=float)

    available_components = []
    missing_components = []

    for name, item in weighted_components.items():
        arr = item["score"]
        weight = float(item["weight"])

        if arr is None:
            missing_components.append(name)
            continue

        if arr.shape != sst_arr.shape:
            missing_components.append(name)
            continue

        valid = np.isfinite(arr)

        numerator[valid] += weight * arr[valid]
        present_weight[valid] += weight
        evidence_component_count[valid] += 1

        # Komponen inti dianggap benar-benar mendukung jika skornya >= 60.
        if name in CORE_UPWELLING_COMPONENTS:
            strong = valid & (arr >= 60)
            core_support_count[strong] += 1

        available_components.append(name)

    raw_upi = np.full_like(sst_arr, np.nan, dtype=float)
    valid_weight = present_weight > 0
    raw_upi[valid_weight] = numerator[valid_weight] / present_weight[valid_weight]

    coverage_ratio = np.zeros_like(sst_arr, dtype=float)
    coverage_ratio[valid_weight] = present_weight[valid_weight] / designed_total_weight

    # Penalti utama: skor tinggi harus didukung banyak komponen, bukan hanya satu komponen.
    upi = np.full_like(sst_arr, np.nan, dtype=float)
    upi[valid_weight] = raw_upi[valid_weight] * coverage_ratio[valid_weight]

    # Evidence cap:
    # - 0 komponen inti kuat: maksimal 25
    # - 1 komponen inti kuat: maksimal 45
    # - 2 komponen inti kuat: maksimal 70
    # - 3 komponen inti kuat: maksimal 85
    # - 4 komponen inti kuat: maksimal 100
    support_cap = np.full_like(sst_arr, 25.0, dtype=float)
    support_cap[core_support_count >= 1] = 45.0
    support_cap[core_support_count >= 2] = 70.0
    support_cap[core_support_count >= 3] = 85.0
    support_cap[core_support_count >= 4] = 100.0

    upi = np.minimum(upi, support_cap)
    upi = np.clip(upi, 0, 100)

    lat2, lon2 = get_lat_lon_arrays(sst_da)

    component_maps = {
        "sst_cooling": sst_score,
        "chl_enhancement": chl_score,
        "current_divergence": div_score,
        "ssh_low": ssh_score,
        "bathymetry_slope": bathy_component,
        "wind_magnitude_diagnostic": wind_mag_score,

        # Evidence diagnostics
        "raw_relative_signal": raw_upi,
        "coverage_percent": coverage_ratio * 100.0,
        "evidence_component_count": evidence_component_count,
        "core_support_count": core_support_count,
    }

    top_cells = summarize_top_cells(upi, lat2, lon2, component_maps, top_k=15)
    top_zones = aggregate_zones(top_cells)

    candidate_locations = build_candidate_locations(
        top_cells,
        max_n=MAX_CANDIDATE_LOCATIONS,
    )

    candidate_summary = build_candidate_summary(candidate_locations)

    mean_score = float(np.nanmean(upi)) if np.isfinite(upi).any() else None
    max_score = float(np.nanmax(upi)) if np.isfinite(upi).any() else None

    # Confidence based on number of available core components.
    confidence = round(len(available_components) / len(weighted_components), 2)

    payload = {
        "module": "upwelling_watch",
        "version": UPI_VERSION,
        "region": REGION_NAME,
        "generated_at": now_iso(),
        "available": True,
        "index": {
            "name": "UPI",
            "full_name": "Upwelling Potential Index",
            "score_mean": round(mean_score, 1) if mean_score is not None else None,
            "score_max": round(max_score, 1) if max_score is not None else None,
            "score_unit": "relative_signal_score_0_100",
            "score_method": "relative_percentile_grid_score",
            "status": level_from_score(max_score),
            "confidence": confidence,
            "confidence_label": (
                "cukup baik" if confidence >= 0.8 else
                "sedang" if confidence >= 0.6 else
                "terbatas"
          ),
     },
        "top_zones": top_zones,
        "top_cells": top_cells,
        "candidate_locations": candidate_locations,
        "candidate_summary": candidate_summary,
        "location_note": build_location_note(),
        "interpretation_radius_km": INTERPRETATION_RADIUS_KM,
        "user_guidance": build_user_guidance(max_score, candidate_locations),
        "components": {
            "available": available_components,
            "missing": missing_components,
            "weights": {k: v["weight"] for k, v in weighted_components.items()},
            "diagnostic_only": ["wind_magnitude_diagnostic"],
        },
        "quality_control": {
            "evidence_gate": True,
            "method": "raw_relative_signal_times_component_coverage_with_core_support_cap",
            "reason": (
                "UPI v0.1c mencegah skor tinggi hanya karena satu komponen, misalnya SST cooling saja. "
                "Skor tinggi harus didukung oleh beberapa komponen inti."
            ),
            "core_components": sorted(list(CORE_UPWELLING_COMPONENTS)),
        }, 
        "data_files_used": {
            "sst": sst_file,
            "chl": chl_file,
            "current_u": current_file_u,
            "current_v": current_file_v,
            "ssh": ssh_file,
            "wind_u": wind_file_u,
            "wind_v": wind_file_v,
            "bathy": bathy_file,
        },
        "scientific_caution": (
            "UPI v0.1 membaca indikasi potensi upwelling dari proxy permukaan laut "
            "seperti pendinginan SST, peningkatan chlorophyll-a, divergensi arus, SSH, "
            "dan bathymetri. Ini bukan bukti final upwelling tanpa validasi vertikal, "
            "nutrien, atau data lapangan."
        ),
        "interpretation_note": build_interpretation_note(max_score, confidence),
        "component_diagnostic_note": build_component_diagnostic_note(top_cells),
        "public_narrative": build_public_narrative(max_score, top_zones, confidence),
    }

    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote: {OUT_JSON}")


def build_public_narrative(
    max_score: Optional[float],
    top_zones: List[Dict[str, Any]],
    confidence: float,
) -> str:
    if max_score is None or not np.isfinite(max_score):
        return "Data belum cukup untuk membaca indikasi potensi upwelling hari ini."

    if top_zones:
        zone = top_zones[0]["zone_label"]
    else:
        zone = "beberapa perairan Aceh"

    if max_score >= 85:
        lead = (
            "NELAYA-AI membaca sinyal permukaan yang sangat kuat untuk potensi upwelling "
            "atau proses pengayaan/mixing lokal"
        )
    elif max_score >= 70:
        lead = "NELAYA-AI membaca indikasi potensi upwelling yang kuat"
    elif max_score >= 50:
        lead = "NELAYA-AI membaca indikasi potensi upwelling tingkat sedang"
    elif max_score >= 30:
        lead = "NELAYA-AI membaca sinyal awal yang masih perlu dipantau"
    else:
        lead = "NELAYA-AI belum membaca sinyal upwelling yang kuat"

    conf_text = "cukup baik" if confidence >= 0.8 else "sedang" if confidence >= 0.6 else "terbatas"

    return (
        f"{lead} di sekitar {zone}. Pembacaan ini berbasis kombinasi sinyal permukaan laut "
        f"dengan tingkat keyakinan data {conf_text}. Skor UPI bersifat relatif terhadap grid hari ini, "
        f"bukan probabilitas kepastian kejadian upwelling. Hasil ini perlu dibaca sebagai indikasi ilmiah awal, "
        f"bukan kesimpulan final tanpa validasi vertikal atau lapangan."
    )

def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def evidence_level_from(score: float, core_support: int) -> str:
    if score >= 85 and core_support >= 4:
        return "sangat_kuat_belum_konklusif"
    if score >= 70 and core_support >= 3:
        return "kuat_perlu_verifikasi"
    if score >= 50 and core_support >= 2:
        return "sedang_perlu_dipantau"
    if score >= 30:
        return "awal_parsial"
    return "lemah"


def evidence_label_from(score: float, core_support: int) -> str:
    level = evidence_level_from(score, core_support)

    labels = {
        "sangat_kuat_belum_konklusif": "Sangat kuat, belum konklusif",
        "kuat_perlu_verifikasi": "Kuat, perlu verifikasi",
        "sedang_perlu_dipantau": "Sedang, perlu dipantau",
        "awal_parsial": "Sinyal awal/parsial",
        "lemah": "Lemah",
    }

    return labels.get(level, "Belum tersedia")


def component_driver_summary(comps: Dict[str, Any]) -> Dict[str, Any]:
    sst = _num(comps.get("sst_cooling"))
    chl = _num(comps.get("chl_enhancement"))
    cur = _num(comps.get("current_divergence"))
    ssh = _num(comps.get("ssh_low"))
    bathy = _num(comps.get("bathymetry_slope"))

    strong = []
    moderate = []
    weak = []

    checks = [
        ("pendinginan SST", sst),
        ("peningkatan chlorophyll-a", chl),
        ("divergensi arus permukaan", cur),
        ("sinyal SSH rendah", ssh),
        ("dukungan bathymetri/lereng", bathy),
    ]

    for label, value in checks:
        if value >= 70:
            strong.append(label)
        elif value >= 50:
            moderate.append(label)
        elif value > 0:
            weak.append(label)

    return {
        "strong_drivers": strong,
        "moderate_drivers": moderate,
        "weak_or_partial_drivers": weak,
    }


def build_location_interpretation(cell: Dict[str, Any]) -> str:
    comps = cell.get("components", {}) or {}
    score = _num(cell.get("upi_score"))
    core_support = int(_num(comps.get("core_support_count")))
    drivers = component_driver_summary(comps)

    strong = drivers["strong_drivers"]
    moderate = drivers["moderate_drivers"]

    if core_support >= 3:
        if strong:
            return (
                "Lokasi grid ini menarik karena didukung beberapa komponen inti, terutama "
                + ", ".join(strong[:3])
                + ". Hasil tetap indikatif dan perlu validasi vertikal/lapangan."
            )
        return (
            "Lokasi grid ini memiliki dukungan beberapa komponen inti, tetapi kekuatan masing-masing "
            "komponen perlu dibaca hati-hati."
        )

    if core_support == 2:
        joined = ", ".join((strong + moderate)[:3]) if (strong or moderate) else "beberapa sinyal permukaan"
        return (
            f"Lokasi grid ini menunjukkan indikasi sedang dengan dukungan {joined}. "
            "Belum cukup untuk disebut indikasi kuat."
        )

    if core_support == 1:
        joined = ", ".join((strong + moderate)[:2]) if (strong or moderate) else "satu komponen inti"
        return (
            f"Lokasi grid ini baru didukung oleh {joined}. Lebih tepat dibaca sebagai sinyal awal, "
            "bukan bukti kuat upwelling aktif."
        )

    if score >= 30:
        return (
            "Lokasi grid ini memiliki sinyal parsial. Perlu pembacaan ulang saat komponen SST, CHL, arus, "
            "dan SSH saling mendukung."
        )

    return "Belum ada sinyal yang cukup kuat pada lokasi grid ini."


def build_candidate_locations(
    top_cells: List[Dict[str, Any]],
    max_n: int = MAX_CANDIDATE_LOCATIONS,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    for cell in top_cells[:max_n]:
        comps = cell.get("components", {}) or {}
        score = _num(cell.get("upi_score"))
        core_support = int(_num(comps.get("core_support_count")))
        evidence_count = int(_num(comps.get("evidence_component_count")))
        coverage = _num(comps.get("coverage_percent"))

        drivers = component_driver_summary(comps)

        candidates.append({
            "rank": cell.get("rank"),
            "lat": cell.get("lat"),
            "lon": cell.get("lon"),
            "coordinate_text": (
                f"{_num(cell.get('lat')):.4f}, {_num(cell.get('lon')):.4f}"
                if cell.get("lat") is not None and cell.get("lon") is not None
                else None
            ),
            "zone_label": cell.get("zone_label"),
            "upi_score": round(score, 1),
            "evidence_level": evidence_level_from(score, core_support),
            "evidence_label": evidence_label_from(score, core_support),
            "core_support": core_support,
            "core_support_text": f"{core_support}/4",
            "evidence_component_count": evidence_count,
            "coverage_percent": round(coverage, 1),
            "interpretation_radius_km": INTERPRETATION_RADIUS_KM,
            "drivers": drivers,
            "interpretation": build_location_interpretation(cell),
            "components": comps,
        })

    return candidates


def build_candidate_summary(candidate_locations: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not candidate_locations:
        return {
            "count": 0,
            "strong_count": 0,
            "moderate_count": 0,
            "main_message": "Belum ada kandidat lokasi yang cukup kuat untuk ditampilkan.",
        }

    strong = [
        c for c in candidate_locations
        if c.get("evidence_level") in ["sangat_kuat_belum_konklusif", "kuat_perlu_verifikasi"]
    ]
    moderate = [
        c for c in candidate_locations
        if c.get("evidence_level") == "sedang_perlu_dipantau"
    ]

    zones = {}
    for c in candidate_locations:
        z = c.get("zone_label") or "Zona tidak diketahui"
        zones.setdefault(z, 0)
        zones[z] += 1

    zone_list = [
        {"zone_label": z, "candidate_count": n}
        for z, n in sorted(zones.items(), key=lambda item: item[1], reverse=True)
    ]

    if strong:
        main = (
            f"NELAYA-AI membaca {len(strong)} kandidat lokasi dengan indikasi kuat atau lebih, "
            "tetapi semuanya tetap perlu dibaca sebagai indikasi awal berbasis grid."
        )
    elif moderate:
        main = (
            f"NELAYA-AI membaca {len(moderate)} kandidat lokasi dengan indikasi sedang. "
            "Belum ada sinyal yang cukup kuat untuk disebut indikasi utama."
        )
    else:
        main = (
            "NELAYA-AI membaca beberapa sinyal awal/parsial. Belum ada kandidat lokasi yang cukup kuat."
        )

    return {
        "count": len(candidate_locations),
        "strong_count": len(strong),
        "moderate_count": len(moderate),
        "zones": zone_list,
        "main_message": main,
    }


def build_location_note() -> str:
    return (
        f"Koordinat kandidat adalah titik grid indikatif dengan radius interpretasi sekitar ±{INTERPRETATION_RADIUS_KM} km, "
        "bukan titik GPS pasti kejadian upwelling. Lokasi perlu dibaca sebagai area sekitar koordinat, "
        "tergantung resolusi data satelit/model dan dinamika laut harian."
    )


def build_user_guidance(
    max_score: Optional[float],
    candidate_locations: List[Dict[str, Any]],
) -> Dict[str, str]:
    if max_score is None or not np.isfinite(max_score):
        status = "Data belum cukup untuk memberi panduan operasional."
    elif max_score >= 70:
        status = (
            "Ada kandidat lokasi yang menarik untuk dipantau lebih lanjut, terutama untuk validasi lapangan "
            "dan pembacaan produktivitas laut."
        )
    elif max_score >= 50:
        status = (
            "Ada sinyal sedang yang dapat menjadi bahan pemantauan, tetapi belum cukup kuat untuk dijadikan "
            "dasar kesimpulan."
        )
    else:
        status = "Sinyal masih lemah atau parsial. Gunakan sebagai informasi pemantauan awal."

    top = candidate_locations[0] if candidate_locations else {}
    top_zone = top.get("zone_label", "zona prioritas hari ini")

    return {
        "general": status,
        "research": (
            f"Prioritaskan {top_zone} dan kandidat koordinat teratas untuk pengukuran suhu vertikal, "
            "nutrien, DO, plankton, atau observasi lapangan."
        ),
        "fisheries": (
            "Baca UPI sebagai sinyal pendukung produktivitas dan dinamika habitat, bukan jaminan keberadaan ikan "
            "atau hasil tangkapan."
        ),
        "management": (
            "Gunakan sebagai early watch untuk diskusi pengelolaan perikanan, konservasi, produktivitas primer, "
            "dan perubahan kondisi laut harian."
        ),
        "public": (
            "Area kandidat menunjukkan lokasi laut yang sedang menarik untuk dipantau, bukan lokasi pasti terjadinya upwelling."
        ),
        "safety": (
            "Informasi ini tidak menggantikan prakiraan cuaca, peringatan gelombang, keselamatan pelayaran, "
            "atau regulasi resmi."
        ),
    }


if __name__ == "__main__":
    main()
