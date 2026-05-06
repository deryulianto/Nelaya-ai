#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NELAYA-AI Daily Ocean Current Analysis Builder

Purpose:
- Analyze daily Copernicus CMEMS current NRT data for Aceh-Simeulue domain.
- Produce JSON + PNG dashboard for current-analysis page.

Input:
  data/raw/aceh_simeulue/cur_nrt/YYYY/MM/current_nrt_aceh_YYYY-MM-DD.nc

Outputs:
  data/physics/current_analysis_today.json
  data/physics/current_analysis_dashboard_today.png
  data/physics/current_analysis_latest.geojson

Archive:
  data/physics/history_current/YYYY/MM/DD/current_analysis_YYYY-MM-DD.json
  data/physics/history_current/YYYY/MM/DD/current_dashboard_YYYY-MM-DD.png

Main variables expected:
  uo = eastward current velocity, m/s
  vo = northward current velocity, m/s
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import xarray as xr


os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


ROOT = Path(".")
CUR_DIR = ROOT / "data" / "raw" / "aceh_simeulue" / "cur_nrt"
OUT_DIR = ROOT / "data" / "physics"
HISTORY_DIR = OUT_DIR / "history_current"

DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def to_builtin(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_builtin(v) for v in obj]
    if isinstance(obj, tuple):
        return [to_builtin(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


def safe_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def open_dataset_any(path: Path) -> xr.Dataset:
    errors = []
    for engine in ["scipy", "netcdf4", "h5netcdf", None]:
        try:
            if engine is None:
                return xr.open_dataset(path, cache=False, decode_times=False)
            return xr.open_dataset(path, engine=engine, cache=False, decode_times=False)
        except Exception as exc:
            errors.append(f"{engine}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Cannot open dataset: " + " | ".join(errors))


def detect_coord(ds: xr.Dataset, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in ds.coords or c in ds.dims:
            return c
    return None


def detect_var(ds: xr.Dataset, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in ds.data_vars:
            return c
    return None


def extract_date_from_filename(path: Path) -> Optional[str]:
    m = DATE_RE.search(path.name)
    return m.group(1) if m else None


def find_latest_current_file(root: Path, days_back: int = 10, date: Optional[str] = None) -> Path:
    if date:
        y, m, _ = date.split("-")
        p = root / y / m / f"current_nrt_aceh_{date}.nc"
        if p.exists():
            return p
        raise FileNotFoundError(f"Requested current file not found: {p}")

    files = sorted(root.glob("20??/??/current_nrt_aceh_20??-??-??.nc"))
    if not files:
        raise FileNotFoundError(f"No current files found in {root}")

    if days_back <= 0:
        return files[-1]

    today = datetime.now(ZoneInfo("Asia/Jakarta")).date()
    min_date = today - timedelta(days=days_back)

    candidates = []
    for f in files:
        d = extract_date_from_filename(f)
        if not d:
            continue
        try:
            dd = datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
            continue
        if dd >= min_date:
            candidates.append(f)

    return candidates[-1] if candidates else files[-1]


def squeeze_to_2d(da: xr.DataArray, lat_name: str, lon_name: str) -> xr.DataArray:
    da = da.squeeze(drop=True)

    # Keep only lat/lon if extra dims remain.
    for dim in list(da.dims):
        if dim not in {lat_name, lon_name}:
            da = da.isel({dim: 0}, drop=True)

    if lat_name not in da.dims or lon_name not in da.dims:
        raise ValueError(f"Expected lat/lon dims in {da.name}, got dims={da.dims}")

    da = da.transpose(lat_name, lon_name)
    da = da.rename({lat_name: "lat", lon_name: "lon"})

    return xr.DataArray(
        np.asarray(da.values, dtype=float),
        coords={
            "lat": np.asarray(da["lat"].values, dtype=float),
            "lon": np.asarray(da["lon"].values, dtype=float),
        },
        dims=("lat", "lon"),
        name=da.name,
        attrs=dict(da.attrs),
    )


def vector_bearing_deg(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """
    Direction toward which current moves.
    0 = north, 90 = east, 180 = south, 270 = west.
    """
    return (np.degrees(np.arctan2(u, v)) + 360.0) % 360.0


def vector_mean_direction_deg(u: np.ndarray, v: np.ndarray) -> Optional[float]:
    u_mean = np.nanmean(u)
    v_mean = np.nanmean(v)
    if not np.isfinite(u_mean) or not np.isfinite(v_mean):
        return None
    if abs(u_mean) < 1e-12 and abs(v_mean) < 1e-12:
        return None
    return float((math.degrees(math.atan2(u_mean, v_mean)) + 360.0) % 360.0)


def direction_label_id(deg: Optional[float]) -> Optional[str]:
    if deg is None:
        return None
    labels = [
        "utara",
        "timur_laut",
        "timur",
        "tenggara",
        "selatan",
        "barat_daya",
        "barat",
        "barat_laut",
    ]
    idx = int(((deg + 22.5) % 360) // 45)
    return labels[idx]


def direction_label_pretty(label: Optional[str]) -> str:
    if not label:
        return "Belum tersedia"
    return " ".join(w.capitalize() for w in label.replace("_", " ").split())


def safe_stats(arr: np.ndarray) -> Dict[str, Any]:
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return {
            "count": 0,
            "nan_ratio": 1.0,
            "min": None,
            "p05": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "max": None,
            "mean": None,
            "std": None,
        }

    return {
        "count": int(valid.size),
        "nan_ratio": float(1.0 - valid.size / arr.size),
        "min": float(np.nanmin(valid)),
        "p05": float(np.nanpercentile(valid, 5)),
        "p25": float(np.nanpercentile(valid, 25)),
        "p50": float(np.nanpercentile(valid, 50)),
        "p75": float(np.nanpercentile(valid, 75)),
        "p90": float(np.nanpercentile(valid, 90)),
        "p95": float(np.nanpercentile(valid, 95)),
        "max": float(np.nanmax(valid)),
        "mean": float(np.nanmean(valid)),
        "std": float(np.nanstd(valid)),
    }


def classify_current(speed_mean: Optional[float]) -> Dict[str, Any]:
    if speed_mean is None:
        return {
            "level": "unknown",
            "label": "Belum tersedia",
            "interpretation": "Data arus belum tersedia.",
        }

    if speed_mean < 0.15:
        return {
            "level": "low",
            "label": "Lemah",
            "interpretation": "Arus relatif lemah; distribusi massa air dan plankton cenderung tidak terlalu aktif.",
        }

    if speed_mean < 0.45:
        return {
            "level": "moderate",
            "label": "Lemah–sedang",
            "interpretation": "Arus lemah–sedang; cukup mendukung distribusi plankton, transport massa air, dan pergerakan ikan.",
        }

    return {
        "level": "strong",
        "label": "Kuat",
        "interpretation": "Arus kuat; dinamika laut tinggi dan operasi kapal kecil perlu kehati-hatian.",
    }


def build_histogram(speed: np.ndarray, bins: int = 36) -> Dict[str, Any]:
    valid = speed[np.isfinite(speed)]
    if valid.size == 0:
        return {"bins": [], "counts": []}

    counts, edges = np.histogram(valid, bins=bins)
    centers = 0.5 * (edges[:-1] + edges[1:])

    return {
        "bin_centers": [float(x) for x in centers],
        "bin_edges": [float(x) for x in edges],
        "counts": [int(x) for x in counts],
    }


def build_rose(direction_deg: np.ndarray, speed: np.ndarray, bins_deg: int = 30) -> Dict[str, Any]:
    valid = np.isfinite(direction_deg) & np.isfinite(speed)
    if not np.any(valid):
        return {"bin_centers_deg": [], "counts": [], "mean_speed": []}

    dirs = direction_deg[valid]
    spd = speed[valid]

    edges = np.arange(0, 360 + bins_deg, bins_deg)
    counts, _ = np.histogram(dirs, bins=edges)

    mean_speed = []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (dirs >= a) & (dirs < b)
        mean_speed.append(float(np.nanmean(spd[m])) if np.any(m) else None)

    centers = 0.5 * (edges[:-1] + edges[1:])

    return {
        "bin_edges_deg": [float(x) for x in edges],
        "bin_centers_deg": [float(x) for x in centers],
        "counts": [int(x) for x in counts],
        "mean_speed": mean_speed,
    }


def build_profiles(
    lat: np.ndarray,
    lon: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    speed: np.ndarray,
) -> Dict[str, Any]:
    # Meridional profile: mean by latitude.
    u_by_lat = np.nanmean(u, axis=1)
    v_by_lat = np.nanmean(v, axis=1)
    s_by_lat = np.nanmean(speed, axis=1)

    # Zonal profile: mean by longitude.
    u_by_lon = np.nanmean(u, axis=0)
    v_by_lon = np.nanmean(v, axis=0)
    s_by_lon = np.nanmean(speed, axis=0)

    return {
        "meridional_by_lat": {
            "lat": [float(x) for x in lat],
            "uo_mean_ms": [safe_float(x) for x in u_by_lat],
            "vo_mean_ms": [safe_float(x) for x in v_by_lat],
            "speed_mean_ms": [safe_float(x) for x in s_by_lat],
        },
        "zonal_by_lon": {
            "lon": [float(x) for x in lon],
            "uo_mean_ms": [safe_float(x) for x in u_by_lon],
            "vo_mean_ms": [safe_float(x) for x in v_by_lon],
            "speed_mean_ms": [safe_float(x) for x in s_by_lon],
        },
    }


def find_hotspot(lat: np.ndarray, lon: np.ndarray, speed: np.ndarray, u: np.ndarray, v: np.ndarray) -> Dict[str, Any]:
    arr = np.asarray(speed, dtype=float)
    if not np.any(np.isfinite(arr)):
        return {}

    idx = int(np.nanargmax(arr))
    ny, nx = arr.shape
    i = idx // nx
    j = idx % nx

    bearing = safe_float(vector_bearing_deg(np.array([[u[i, j]]]), np.array([[v[i, j]]]))[0, 0])

    return {
        "lat": float(lat[i]),
        "lon": float(lon[j]),
        "speed_ms": safe_float(speed[i, j]),
        "uo_ms": safe_float(u[i, j]),
        "vo_ms": safe_float(v[i, j]),
        "direction_deg": bearing,
        "direction_label": direction_label_id(bearing),
    }


def make_geojson_hotspots(
    lat: np.ndarray,
    lon: np.ndarray,
    speed: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    out_file: Path,
    threshold: float,
    max_points: int,
) -> Dict[str, Any]:
    rows = []
    for i in range(speed.shape[0]):
        for j in range(speed.shape[1]):
            sp = safe_float(speed[i, j])
            if sp is None or sp < threshold:
                continue
            bearing = safe_float(vector_bearing_deg(np.array([[u[i, j]]]), np.array([[v[i, j]]]))[0, 0])
            rows.append(
                {
                    "lat": float(lat[i]),
                    "lon": float(lon[j]),
                    "speed_ms": sp,
                    "uo_ms": safe_float(u[i, j]),
                    "vo_ms": safe_float(v[i, j]),
                    "direction_deg": bearing,
                    "direction_label": direction_label_id(bearing),
                }
            )

    rows = sorted(rows, key=lambda r: r["speed_ms"], reverse=True)[:max_points]

    features = []
    for r in rows:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [r["lon"], r["lat"]],
                },
                "properties": {
                    "speed_ms": r["speed_ms"],
                    "uo_ms": r["uo_ms"],
                    "vo_ms": r["vo_ms"],
                    "direction_deg": r["direction_deg"],
                    "direction_label": r["direction_label"],
                    "label": "Current speed hotspot",
                },
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "name": "NELAYA-AI Current Speed Hotspots",
        "features": features,
    }

    out_file.write_text(json.dumps(to_builtin(geojson), indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "created": True,
        "file": str(out_file),
        "threshold": threshold,
        "point_count": len(features),
        "max_points": max_points,
    }


def build_narrative(
    date: str,
    stats: Dict[str, Any],
    direction_label: Optional[str],
    hotspot: Dict[str, Any],
    classification: Dict[str, Any],
) -> Dict[str, Any]:
    mean_speed = stats.get("mean")
    max_speed = stats.get("max")
    p75 = stats.get("p75")

    hotspot_label = direction_label_pretty(hotspot.get("direction_label"))

    return {
        "short": (
            f"Pada {date}, arus rata-rata di domain Aceh-Simeulue sekitar "
            f"{mean_speed:.3f} m/s dengan kecenderungan dominan menuju "
            f"{direction_label_pretty(direction_label)}."
            if mean_speed is not None
            else "Data arus belum tersedia."
        ),
        "analysis": [
            f"Kecepatan rata-rata arus berada pada kategori {classification.get('label')}.",
            f"P75 kecepatan arus sekitar {p75:.3f} m/s, sehingga sebagian area memiliki dinamika lebih aktif daripada rata-rata."
            if p75 is not None
            else "P75 kecepatan arus belum tersedia.",
            f"Hotspot kecepatan tertinggi terdeteksi di sekitar {hotspot.get('lat'):.2f}°N, {hotspot.get('lon'):.2f}°E dengan kecepatan {hotspot.get('speed_ms'):.3f} m/s dan arah lokal menuju {hotspot_label}."
            if hotspot
            else "Hotspot kecepatan belum tersedia.",
        ],
        "fisheries_context": (
            "Arus lemah–sedang dapat membantu transport massa air, distribusi plankton, dan pembentukan koridor habitat, "
            "tetapi interpretasi peluang ikan tetap perlu dibaca bersama FGI, SST, CHL, front, bathymetry, dan keselamatan melaut."
        ),
        "scientific_caution": (
            "Analisis ini membaca arus permukaan dari Copernicus CMEMS pada domain Aceh-Simeulue. "
            "Ini bukan prediksi langsung hasil tangkapan dan perlu divalidasi dengan data lapangan."
        ),
    }


def make_png_dashboard(
    out_png: Path,
    date: str,
    lat: np.ndarray,
    lon: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    speed: np.ndarray,
    direction_deg: np.ndarray,
    summary: Dict[str, Any],
) -> None:
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "figure.facecolor": "#071528",
        "axes.facecolor": "#0b1e3a",
        "savefig.facecolor": "#071528",
        "text.color": "#e5edf7",
        "axes.labelcolor": "#d7e3f1",
        "xtick.color": "#d7e3f1",
        "ytick.color": "#d7e3f1",
        "axes.edgecolor": "#1d7ea6",
        "font.size": 9,
    })

    fig = plt.figure(figsize=(16, 10), dpi=160)
    gs = fig.add_gridspec(2, 3, width_ratios=[1.1, 1.1, 1.05], height_ratios=[1, 1], wspace=0.38, hspace=0.46)

    fig.suptitle(
        f"Dashboard Analisis Arus Laut — NELAYA-AI\nCopernicus CMEMS · {date}",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )

    valid_speed = speed[np.isfinite(speed)]
    stats = summary["speed_stats"]

    # 1. Histogram speed.
    ax1 = fig.add_subplot(gs[0, 0])
    if valid_speed.size:
        n, bins, patches = ax1.hist(valid_speed, bins=36, edgecolor="#0b1220", linewidth=0.4)
        for patch, b0 in zip(patches, bins[:-1]):
            patch.set_alpha(0.9)
        ax1.axvline(stats["mean"], linestyle="--", linewidth=1.2, label=f"Mean: {stats['mean']:.3f} m/s")
        ax1.axvline(stats["p75"], linestyle=":", linewidth=1.5, label=f"P75: {stats['p75']:.3f} m/s")
        ax1.legend(loc="upper right", frameon=True, fontsize=8)
    ax1.set_title("Distribusi Kecepatan", fontweight="bold")
    ax1.set_xlabel("Kecepatan (m/s)")
    ax1.set_ylabel("Frekuensi")
    ax1.grid(alpha=0.18)

    # 2. Scatter u vs v.
    ax2 = fig.add_subplot(gs[0, 1])
    uf = u.flatten()
    vf = v.flatten()
    sf = speed.flatten()
    mask = np.isfinite(uf) & np.isfinite(vf) & np.isfinite(sf)
    if np.any(mask):
        sc = ax2.scatter(uf[mask], vf[mask], c=sf[mask], s=6, alpha=0.55)
        cb = fig.colorbar(sc, ax=ax2, fraction=0.046, pad=0.04)
        cb.set_label("Speed (m/s)")
    ax2.axhline(0, linewidth=1.0, alpha=0.6)
    ax2.axvline(0, linewidth=1.0, alpha=0.6)
    ax2.set_title("Scatter uo vs vo\n(bias barat–selatan)", fontweight="bold")
    ax2.set_xlabel("uo — Eastward (m/s)")
    ax2.set_ylabel("vo — Northward (m/s)")
    ax2.grid(alpha=0.18)

    # 3. Rose diagram.
    ax3 = fig.add_subplot(gs[0, 2], projection="polar")
    rose = summary["rose"]
    centers = np.radians(np.asarray(rose["bin_centers_deg"], dtype=float))
    counts = np.asarray(rose["counts"], dtype=float)
    width = np.radians(30)
    if counts.size:
        ax3.bar(centers, counts, width=width, alpha=0.82, align="center", edgecolor="#071528", linewidth=0.6)
    ax3.set_theta_zero_location("N")
    ax3.set_theta_direction(-1)
    ax3.set_title("Rose Diagram\nArah Arus", fontweight="bold", pad=14)
    ax3.grid(alpha=0.45)

    # 4. Meridional profile.
    ax4 = fig.add_subplot(gs[1, 0])
    prof = summary["profiles"]["meridional_by_lat"]
    ax4.plot(prof["uo_mean_ms"], prof["lat"], label="uo (E-W)", linewidth=2)
    ax4.plot(prof["vo_mean_ms"], prof["lat"], label="vo (N-S)", linewidth=2)
    ax4.axvline(0, linewidth=1, alpha=0.5)
    ax4.set_title("Profil Meridional\n(rata-rata per lintang)", fontweight="bold")
    ax4.set_xlabel("Kecepatan rata-rata (m/s)")
    ax4.set_ylabel("Lintang (°N)")
    ax4.legend(fontsize=8)
    ax4.grid(alpha=0.18)

    # 5. Zonal profile.
    ax5 = fig.add_subplot(gs[1, 1])
    profz = summary["profiles"]["zonal_by_lon"]
    ax5.plot(profz["lon"], profz["uo_mean_ms"], label="uo (E-W)", linewidth=2)
    ax5.plot(profz["lon"], profz["vo_mean_ms"], label="vo (N-S)", linewidth=2)
    ax5.plot(profz["lon"], profz["speed_mean_ms"], label="speed", linewidth=1.5, linestyle="--", alpha=0.85)
    ax5.axhline(0, linewidth=1, alpha=0.5)
    ax5.set_title("Profil Zonal\n(rata-rata per bujur)", fontweight="bold")
    ax5.set_xlabel("Bujur (°E)")
    ax5.set_ylabel("Kecepatan rata-rata (m/s)")
    ax5.legend(fontsize=8)
    ax5.grid(alpha=0.18)

    # 6. Summary panel.
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis("off")

    hotspot = summary["hotspot"]
    direction_label = direction_label_pretty(summary["dominant_direction_label"])
    hotspot_dir = direction_label_pretty(hotspot.get("direction_label"))

    text = (
        "RINGKASAN ANALISIS\n\n"
        f"Tanggal  : {date}\n"
        f"Domain   : 1–7°N, 92–99°E\n"
        f"Kedalaman: {summary.get('depth_m', 'surface')} m\n\n"
        "Kecepatan Arus:\n"
        f"  Rata-rata : {stats['mean']:.3f} m/s\n"
        f"  Maksimum  : {stats['max']:.3f} m/s\n"
        f"  Std Dev   : {stats['std']:.3f} m/s\n\n"
        "Arah Dominan:\n"
        f"  {direction_label}\n"
        f"  uo mean: {summary['vector_mean']['uo_mean_ms']:.3f} m/s\n"
        f"  vo mean: {summary['vector_mean']['vo_mean_ms']:.3f} m/s\n\n"
        "Hotspot Kecepatan:\n"
        f"  {hotspot.get('lat'):.2f}°N, {hotspot.get('lon'):.2f}°E\n"
        f"  {hotspot.get('speed_ms'):.3f} m/s → {hotspot_dir}\n\n"
        "Konteks Perikanan:\n"
        "  Arus membantu transport massa air,\n"
        "  plankton, dan koridor pelagis.\n"
        "  Baca bersama FGI, SST, CHL,\n"
        "  front, dan keselamatan melaut."
    )

    ax6.text(
        0.02,
        0.98,
        text,
        va="top",
        ha="left",
        fontsize=9,
        linespacing=1.25,
        color="#e5edf7",
    )

    ax6.text(
        0.98,
        0.02,
        "nelaya-ai.com",
        va="bottom",
        ha="right",
        fontsize=9,
        color="#3fb5d8",
        style="italic",
    )

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="NELAYA-AI-LAB root.")
    parser.add_argument("--date", default=None, help="Date YYYY-MM-DD. Default: latest available current file.")
    parser.add_argument("--days-back", type=int, default=10)
    parser.add_argument("--no-png", action="store_true", help="Skip PNG dashboard generation.")
    parser.add_argument("--hotspot-threshold", type=float, default=None, help="Speed threshold for GeoJSON hotspots. Default: P90.")
    parser.add_argument("--max-hotspots", type=int, default=500)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    cur_dir = root / CUR_DIR
    out_dir = root / OUT_DIR
    history_dir = root / HISTORY_DIR

    out_dir.mkdir(parents=True, exist_ok=True)

    current_file = find_latest_current_file(cur_dir, days_back=args.days_back, date=args.date)
    snapshot_date = extract_date_from_filename(current_file) or args.date or datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d")

    print("=" * 78)
    print("NELAYA-AI Daily Current Analysis Builder")
    print("=" * 78)
    print(f"Input file    : {current_file}")
    print(f"Snapshot date : {snapshot_date}")

    ds = open_dataset_any(current_file)

    lat_name = detect_coord(ds, ["lat", "latitude", "y"])
    lon_name = detect_coord(ds, ["lon", "longitude", "x"])
    u_name = detect_var(ds, ["uo", "u", "eastward_current", "eastward_sea_water_velocity"])
    v_name = detect_var(ds, ["vo", "v", "northward_current", "northward_sea_water_velocity"])

    if not lat_name or not lon_name:
        raise SystemExit(f"Could not detect lat/lon coordinates. coords={list(ds.coords)} dims={list(ds.dims)}")
    if not u_name or not v_name:
        raise SystemExit(f"Could not detect uo/vo variables. vars={list(ds.data_vars)}")

    u_da = squeeze_to_2d(ds[u_name], lat_name, lon_name)
    v_da = squeeze_to_2d(ds[v_name], lat_name, lon_name)

    lat = np.asarray(u_da["lat"].values, dtype=float)
    lon = np.asarray(u_da["lon"].values, dtype=float)
    u = np.asarray(u_da.values, dtype=float)
    v = np.asarray(v_da.values, dtype=float)

    speed = np.sqrt(u ** 2 + v ** 2)
    direction = vector_bearing_deg(u, v)

    stats = safe_stats(speed)
    u_stats = safe_stats(u)
    v_stats = safe_stats(v)

    u_mean = safe_float(np.nanmean(u))
    v_mean = safe_float(np.nanmean(v))
    mean_direction = vector_mean_direction_deg(u, v)
    mean_direction_label = direction_label_id(mean_direction)

    hotspot = find_hotspot(lat, lon, speed, u, v)

    threshold = args.hotspot_threshold
    if threshold is None:
        threshold = stats.get("p90") or 0.30

    geojson_out = out_dir / "current_analysis_latest.geojson"
    geojson_info = make_geojson_hotspots(
        lat=lat,
        lon=lon,
        speed=speed,
        u=u,
        v=v,
        out_file=geojson_out,
        threshold=float(threshold),
        max_points=args.max_hotspots,
    )

    profiles = build_profiles(lat, lon, u, v, speed)
    histogram = build_histogram(speed)
    rose = build_rose(direction, speed)

    classification = classify_current(stats.get("mean"))

    depth_value = None
    for dname in ["depth", "depthu", "depthv"]:
        if dname in ds.coords:
            try:
                depth_value = safe_float(np.asarray(ds[dname].values).ravel()[0])
                break
            except Exception:
                pass
        elif dname in ds.dims:
            try:
                depth_value = safe_float(np.asarray(ds[dname].values).ravel()[0])
                break
            except Exception:
                pass

    summary: Dict[str, Any] = {
        "module": "nelaya_ai_daily_current_analysis",
        "version": "0.1",
        "status": "ready",
        "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "snapshot_date": snapshot_date,
        "source": {
            "name": "Copernicus Marine CMEMS current NRT",
            "file": str(current_file),
            "dataset_hint": "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m",
            "variables": {
                "u": u_name,
                "v": v_name,
                "lat": lat_name,
                "lon": lon_name,
            },
        },
        "domain": {
            "region": "Aceh-Simeulue",
            "lat_min": float(np.nanmin(lat)),
            "lat_max": float(np.nanmax(lat)),
            "lon_min": float(np.nanmin(lon)),
            "lon_max": float(np.nanmax(lon)),
        },
        "depth_m": depth_value,
        "grid": {
            "lat_size": int(len(lat)),
            "lon_size": int(len(lon)),
            "cell_count": int(len(lat) * len(lon)),
        },
        "speed_stats": stats,
        "uo_stats": u_stats,
        "vo_stats": v_stats,
        "vector_mean": {
            "uo_mean_ms": u_mean,
            "vo_mean_ms": v_mean,
            "speed_from_mean_vector_ms": safe_float(math.sqrt((u_mean or 0) ** 2 + (v_mean or 0) ** 2)),
            "direction_deg": mean_direction,
            "direction_label": mean_direction_label,
        },
        "dominant_direction_deg": mean_direction,
        "dominant_direction_label": mean_direction_label,
        "classification": classification,
        "hotspot": hotspot,
        "histogram": histogram,
        "rose": rose,
        "profiles": profiles,
        "outputs": {
            "summary_json": str(out_dir / "current_analysis_today.json"),
            "dashboard_png": str(out_dir / "current_analysis_dashboard_today.png"),
            "hotspot_geojson": geojson_info,
        },
    }

    summary["narrative"] = build_narrative(
        date=snapshot_date,
        stats=stats,
        direction_label=mean_direction_label,
        hotspot=hotspot,
        classification=classification,
    )

    json_out = out_dir / "current_analysis_today.json"
    png_out = out_dir / "current_analysis_dashboard_today.png"

    json_out.write_text(json.dumps(to_builtin(summary), indent=2, ensure_ascii=False), encoding="utf-8")

    if not args.no_png:
        make_png_dashboard(
            out_png=png_out,
            date=snapshot_date,
            lat=lat,
            lon=lon,
            u=u,
            v=v,
            speed=speed,
            direction_deg=direction,
            summary=summary,
        )

    # Archive.
    y, m, d = snapshot_date.split("-")
    archive_dir = history_dir / y / m / d
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_json = archive_dir / f"current_analysis_{snapshot_date}.json"
    archive_png = archive_dir / f"current_dashboard_{snapshot_date}.png"

    shutil.copy2(json_out, archive_json)
    if png_out.exists():
        shutil.copy2(png_out, archive_png)

    index_file = history_dir / "index.json"
    if index_file.exists():
        try:
            index = json.loads(index_file.read_text(encoding="utf-8"))
        except Exception:
            index = {"entries": []}
    else:
        index = {"entries": []}

    entry = {
        "snapshot_date": snapshot_date,
        "source_file": str(current_file),
        "summary_json": str(archive_json),
        "dashboard_png": str(archive_png) if archive_png.exists() else None,
        "mean_speed_ms": stats.get("mean"),
        "max_speed_ms": stats.get("max"),
        "dominant_direction_label": mean_direction_label,
        "dominant_direction_deg": mean_direction,
        "hotspot": hotspot,
    }

    entries = [e for e in index.get("entries", []) if e.get("snapshot_date") != snapshot_date]
    entries.append(entry)
    entries = sorted(entries, key=lambda e: e.get("snapshot_date", ""))

    index = {
        "module": "nelaya_ai_current_analysis_history_index",
        "updated_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "count": len(entries),
        "entries": entries,
    }

    index_file.write_text(json.dumps(to_builtin(index), indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 78)
    print("DONE")
    print("=" * 78)
    print(f"JSON    : {json_out}")
    print(f"PNG     : {png_out if png_out.exists() else 'SKIPPED'}")
    print(f"GeoJSON : {geojson_out}")
    print(f"Archive : {archive_dir}")
    print("")
    print("Summary:")
    print(json.dumps(to_builtin({
        "snapshot_date": snapshot_date,
        "mean_speed_ms": stats.get("mean"),
        "max_speed_ms": stats.get("max"),
        "dominant_direction_label": mean_direction_label,
        "dominant_direction_deg": mean_direction,
        "hotspot": hotspot,
        "classification": classification,
    }), indent=2, ensure_ascii=False))
    print("=" * 78)


if __name__ == "__main__":
    main()
