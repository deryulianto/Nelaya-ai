#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import xarray as xr

os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT = Path(".")
IN_ROOT = ROOT / "data" / "raw" / "aceh_simeulue" / "cur_depth_nrt"
OUT_DIR = ROOT / "data" / "physics"
HISTORY_DIR = OUT_DIR / "history_ns_ocean_diagnostics"

DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")

TARGET_DEPTHS = {
    "surface": 0.5,
    "shallow_30m": 30.0,
    "tuna_100m": 100.0,
}

OMEGA = 7.2921159e-5  # rad/s


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


def safe_float(x: Any, default=None):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def extract_date(path: Path) -> str | None:
    m = DATE_RE.search(path.name)
    return m.group(1) if m else None


def latest_file(date: str | None = None) -> Path:
    if date:
        y, m, _ = date.split("-")
        p = IN_ROOT / y / m / f"current_depth_nrt_aceh_{date}.nc"
        if not p.exists():
            raise FileNotFoundError(f"File tidak ditemukan: {p}")
        return p

    files = sorted(IN_ROOT.glob("20??/??/current_depth_nrt_aceh_20??-??-??.nc"))
    if not files:
        raise FileNotFoundError(f"Tidak ada file current depth di {IN_ROOT}")
    return files[-1]


def open_dataset_any(path: Path) -> xr.Dataset:
    errors = []
    for engine in ["scipy", "netcdf4", "h5netcdf", None]:
        try:
            if engine is None:
                return xr.open_dataset(path, cache=False, decode_times=False)
            return xr.open_dataset(path, engine=engine, cache=False, decode_times=False)
        except Exception as exc:
            errors.append(f"{engine}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Gagal membuka dataset: " + " | ".join(errors))


def detect_coord(ds: xr.Dataset, names: list[str]) -> str | None:
    for n in names:
        if n in ds.coords or n in ds.dims:
            return n
    return None


def detect_var(ds: xr.Dataset, names: list[str]) -> str | None:
    for n in names:
        if n in ds.data_vars:
            return n
    return None


def nearest_depth(depths: np.ndarray, target: float) -> tuple[int, float]:
    idx = int(np.nanargmin(np.abs(depths - target)))
    return idx, float(depths[idx])


def squeeze_depth_2d(
    da: xr.DataArray,
    depth_name: str,
    lat_name: str,
    lon_name: str,
    depth_index: int,
) -> xr.DataArray:
    da = da.squeeze(drop=True)

    if depth_name in da.dims:
        da = da.isel({depth_name: depth_index}, drop=True)

    for dim in list(da.dims):
        if dim not in {lat_name, lon_name}:
            da = da.isel({dim: 0}, drop=True)

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
    )


def stats(arr: np.ndarray) -> dict[str, Any]:
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return {
            "count": 0,
            "nan_ratio": 1.0,
            "min": None,
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
        "nan_ratio": float(1 - valid.size / arr.size),
        "min": float(np.nanmin(valid)),
        "p25": float(np.nanpercentile(valid, 25)),
        "p50": float(np.nanpercentile(valid, 50)),
        "p75": float(np.nanpercentile(valid, 75)),
        "p90": float(np.nanpercentile(valid, 90)),
        "p95": float(np.nanpercentile(valid, 95)),
        "max": float(np.nanmax(valid)),
        "mean": float(np.nanmean(valid)),
        "std": float(np.nanstd(valid)),
    }


def normalize01_by_percentile(arr: np.ndarray, p_low: float = 10, p_high: float = 90) -> np.ndarray:
    a = np.asarray(arr, dtype=float)
    out = np.full_like(a, np.nan, dtype=float)

    valid = a[np.isfinite(a)]
    if valid.size == 0:
        return out

    lo = float(np.nanpercentile(valid, p_low))
    hi = float(np.nanpercentile(valid, p_high))

    if hi <= lo:
        out[np.isfinite(a)] = 0.5
        return out

    out = (a - lo) / (hi - lo)
    out = np.clip(out, 0.0, 1.0)
    out[~np.isfinite(a)] = np.nan
    return out


def edge_penalty_mask(lat: np.ndarray, lon: np.ndarray, margin_deg: float = 0.15) -> np.ndarray:
    lat2d, lon2d = np.meshgrid(lat, lon, indexing="ij")
    safe = (
        (lat2d > float(np.nanmin(lat)) + margin_deg)
        & (lat2d < float(np.nanmax(lat)) - margin_deg)
        & (lon2d > float(np.nanmin(lon)) + margin_deg)
        & (lon2d < float(np.nanmax(lon)) - margin_deg)
    )
    return safe.astype(float)


def grid_spacing_m(lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    dlat = abs(float(np.nanmedian(np.diff(lat)))) if len(lat) > 1 else 0.083333
    dlon = abs(float(np.nanmedian(np.diff(lon)))) if len(lon) > 1 else 0.083333

    dy = dlat * 111_320.0
    dx_by_lat = dlon * 111_320.0 * np.cos(np.deg2rad(lat))
    dx_by_lat = np.maximum(dx_by_lat, 1.0)

    dy2d = np.full((len(lat), len(lon)), dy, dtype=float)
    dx2d = np.repeat(dx_by_lat[:, None], len(lon), axis=1)

    return dx2d, dy2d


def gradient_xy(field: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    dx2d, dy2d = grid_spacing_m(lat, lon)

    d_field_dj = np.gradient(field, axis=1)
    d_field_di = np.gradient(field, axis=0)

    dfdx = d_field_dj / dx2d
    dfdy = d_field_di / dy2d

    dfdx[~np.isfinite(field)] = np.nan
    dfdy[~np.isfinite(field)] = np.nan

    return dfdx, dfdy


def direction_deg(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    return (np.degrees(np.arctan2(u, v)) + 360.0) % 360.0


def direction_label(deg: float | None) -> str | None:
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


def vector_mean(u: np.ndarray, v: np.ndarray) -> dict[str, Any]:
    um = safe_float(np.nanmean(u))
    vm = safe_float(np.nanmean(v))

    if um is None or vm is None:
        return {
            "uo_mean_ms": None,
            "vo_mean_ms": None,
            "speed_from_mean_vector_ms": None,
            "direction_deg": None,
            "direction_label": None,
        }

    deg = (math.degrees(math.atan2(um, vm)) + 360.0) % 360.0

    return {
        "uo_mean_ms": um,
        "vo_mean_ms": vm,
        "speed_from_mean_vector_ms": math.sqrt(um ** 2 + vm ** 2),
        "direction_deg": deg,
        "direction_label": direction_label(deg),
    }


def compute_layer_diagnostics(u: np.ndarray, v: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> dict[str, Any]:
    speed = np.sqrt(u ** 2 + v ** 2)
    kinetic_energy = 0.5 * speed ** 2

    du_dx, du_dy = gradient_xy(u, lat, lon)
    dv_dx, dv_dy = gradient_xy(v, lat, lon)

    vorticity = dv_dx - du_dy
    divergence = du_dx + dv_dy
    convergence = -divergence

    normal_strain = du_dx - dv_dy
    shear_strain = dv_dx + du_dy
    strain_mag = np.sqrt(normal_strain ** 2 + shear_strain ** 2)

    adv_u = u * du_dx + v * du_dy
    adv_v = u * dv_dx + v * dv_dy
    advection_mag = np.sqrt(adv_u ** 2 + adv_v ** 2)

    lat2d, _ = np.meshgrid(lat, lon, indexing="ij")
    coriolis_f = 2.0 * OMEGA * np.sin(np.deg2rad(lat2d))
    coriolis_mag = np.abs(coriolis_f) * speed

    vorticity_score = normalize01_by_percentile(np.abs(vorticity), 10, 95)
    convergence_positive = np.where(convergence > 0, convergence, 0.0)
    convergence_score = normalize01_by_percentile(convergence_positive, 10, 95)
    strain_score = normalize01_by_percentile(strain_mag, 10, 95)
    kinetic_score = normalize01_by_percentile(kinetic_energy, 10, 95)
    advection_score = normalize01_by_percentile(advection_mag, 10, 95)

    dynamics_score = (
        0.25 * convergence_score
        + 0.22 * vorticity_score
        + 0.20 * strain_score
        + 0.18 * kinetic_score
        + 0.15 * advection_score
    )

    edge_safe = edge_penalty_mask(lat, lon, margin_deg=0.15)
    dynamics_rank_score = np.clip(dynamics_score * edge_safe, 0.0, 1.0)
    dynamics_rank_score[~np.isfinite(speed)] = np.nan

    return {
        "u": u,
        "v": v,
        "speed": speed,
        "kinetic_energy": kinetic_energy,
        "vorticity": vorticity,
        "divergence": divergence,
        "convergence": convergence,
        "strain_mag": strain_mag,
        "advection_mag": advection_mag,
        "coriolis_mag": coriolis_mag,
        "vorticity_score": vorticity_score,
        "convergence_score": convergence_score,
        "strain_score": strain_score,
        "kinetic_score": kinetic_score,
        "advection_score": advection_score,
        "dynamics_score": dynamics_score,
        "dynamics_rank_score": dynamics_rank_score,
    }


def find_hotspot(lat: np.ndarray, lon: np.ndarray, score: np.ndarray, speed: np.ndarray) -> dict[str, Any] | None:
    if not np.any(np.isfinite(score)):
        return None

    idx = int(np.nanargmax(score))
    ny, nx = score.shape
    i = idx // nx
    j = idx % nx

    return {
        "lat": float(lat[i]),
        "lon": float(lon[j]),
        "score": safe_float(score[i, j]),
        "speed_ms": safe_float(speed[i, j]),
    }


def make_geojson(
    out_file: Path,
    lat: np.ndarray,
    lon: np.ndarray,
    score: np.ndarray,
    speed: np.ndarray,
    threshold: float,
    max_points: int,
):
    rows = []
    for i in range(score.shape[0]):
        for j in range(score.shape[1]):
            sc = safe_float(score[i, j])
            if sc is None or sc < threshold:
                continue
            rows.append(
                {
                    "lat": float(lat[i]),
                    "lon": float(lon[j]),
                    "score": sc,
                    "speed_ms": safe_float(speed[i, j]),
                }
            )

    rows = sorted(rows, key=lambda r: r["score"], reverse=True)[:max_points]

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
            "properties": {
                "score": r["score"],
                "speed_ms": r["speed_ms"],
                "label": "NS-informed ocean dynamics candidate",
                "scientific_caution": "Diagnostic signal from current derivatives, not a deterministic ocean forecast.",
            },
        }
        for r in rows
    ]

    geojson = {
        "type": "FeatureCollection",
        "name": "NELAYA-AI NS-informed Ocean Diagnostics Candidates",
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


def build_layers(ds: xr.Dataset) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    lat_name = detect_coord(ds, ["lat", "latitude", "y"])
    lon_name = detect_coord(ds, ["lon", "longitude", "x"])
    depth_name = detect_coord(ds, ["depth", "depthu", "depthv", "lev"])
    u_name = detect_var(ds, ["uo", "u", "eastward_current", "eastward_sea_water_velocity"])
    v_name = detect_var(ds, ["vo", "v", "northward_current", "northward_sea_water_velocity"])

    if not lat_name or not lon_name:
        raise SystemExit(f"Lat/lon tidak terdeteksi. coords={list(ds.coords)} dims={list(ds.dims)}")
    if not depth_name:
        raise SystemExit(f"Depth tidak terdeteksi. coords={list(ds.coords)} dims={list(ds.dims)}")
    if not u_name or not v_name:
        raise SystemExit(f"uo/vo tidak terdeteksi. vars={list(ds.data_vars)}")

    depths = np.asarray(ds[depth_name].values, dtype=float).ravel()

    layers: dict[str, Any] = {}
    lat = None
    lon = None

    for key, target_depth in TARGET_DEPTHS.items():
        depth_idx, actual_depth = nearest_depth(depths, target_depth)

        u_da = squeeze_depth_2d(ds[u_name], depth_name, lat_name, lon_name, depth_idx)
        v_da = squeeze_depth_2d(ds[v_name], depth_name, lat_name, lon_name, depth_idx)

        if lat is None:
            lat = np.asarray(u_da["lat"].values, dtype=float)
            lon = np.asarray(u_da["lon"].values, dtype=float)

        u = np.asarray(u_da.values, dtype=float)
        v = np.asarray(v_da.values, dtype=float)

        diag = compute_layer_diagnostics(u, v, lat, lon)

        layers[key] = {
            "target_depth_m": target_depth,
            "actual_depth_m": actual_depth,
            "diagnostics": diag,
            "summary": {
                "speed_stats": stats(diag["speed"]),
                "vector_mean": vector_mean(u, v),
                "kinetic_energy_stats": stats(diag["kinetic_energy"]),
                "vorticity_abs_stats": stats(np.abs(diag["vorticity"])),
                "convergence_positive_stats": stats(np.where(diag["convergence"] > 0, diag["convergence"], np.nan)),
                "strain_stats": stats(diag["strain_mag"]),
                "advection_stats": stats(diag["advection_mag"]),
                "dynamics_rank_score_stats": stats(diag["dynamics_rank_score"]),
                "hotspot": find_hotspot(lat, lon, diag["dynamics_rank_score"], diag["speed"]),
            },
        }

    assert lat is not None and lon is not None
    return layers, lat, lon


def build_aggregate(layers: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    surface = layers["surface"]["diagnostics"]["dynamics_rank_score"]
    shallow = layers["shallow_30m"]["diagnostics"]["dynamics_rank_score"]
    tuna = layers["tuna_100m"]["diagnostics"]["dynamics_rank_score"]

    aggregate = np.nanmean(
        np.stack(
            [
                0.20 * surface,
                0.45 * shallow,
                0.35 * tuna,
            ],
            axis=0,
        ),
        axis=0,
    ) * 3.0

    aggregate = np.clip(aggregate, 0.0, 1.0)

    speed = np.nanmean(
        np.stack(
            [
                layers["surface"]["diagnostics"]["speed"],
                layers["shallow_30m"]["diagnostics"]["speed"],
                layers["tuna_100m"]["diagnostics"]["speed"],
            ],
            axis=0,
        ),
        axis=0,
    )

    return aggregate, speed


def make_dashboard_png(
    out_png: Path,
    date: str,
    lat: np.ndarray,
    lon: np.ndarray,
    layers: dict[str, Any],
    aggregate: np.ndarray,
):
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
    gs = fig.add_gridspec(2, 2, width_ratios=[1, 1], height_ratios=[1, 1], wspace=0.25, hspace=0.32)

    fig.suptitle(
         f"NELAYA-AI v0.8-alpha — Diagnostik Dinamika Laut Berbasis Fisika Laut\n"
         f"Navier–Stokes-informed Ocean Diagnostics · Perairan Aceh · Copernicus CMEMS · {date}",
         fontsize=14,
         fontweight="bold",
         y=0.98,
     )

    lon2d, lat2d = np.meshgrid(lon, lat)

    panels = [
        ("surface", "Surface Dynamics Rank"),
        ("shallow_30m", "30 m Dynamics Rank"),
        ("tuna_100m", "100 m Dynamics Rank"),
    ]

    for idx, (key, title) in enumerate(panels):
        ax = fig.add_subplot(gs[idx // 2, idx % 2])
        score = layers[key]["diagnostics"]["dynamics_rank_score"]
        u = layers[key]["diagnostics"]["u"]
        v = layers[key]["diagnostics"]["v"]

        im = ax.contourf(lon2d, lat2d, score, levels=np.linspace(0, 1, 21), cmap="turbo", vmin=0, vmax=1)

        step_y = max(1, len(lat) // 22)
        step_x = max(1, len(lon) // 34)
        ax.quiver(
            lon2d[::step_y, ::step_x],
            lat2d[::step_y, ::step_x],
            u[::step_y, ::step_x],
            v[::step_y, ::step_x],
            color="white",
            alpha=0.70,
            scale=6.5,
            width=0.0024,
        )

        actual_depth = layers[key]["actual_depth_m"]
        ax.set_title(f"{title}\nDepth ~{actual_depth:.1f} m", fontweight="bold")
        ax.set_xlim(92, 99)
        ax.set_ylim(1, 7)
        ax.set_xlabel("Bujur (°E)")
        ax.set_ylabel("Lintang (°N)")
        ax.grid(alpha=0.18, linestyle="--")

        cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
        cb.set_label("Score 0–1")

    ax4 = fig.add_subplot(gs[1, 1])
    im4 = ax4.contourf(lon2d, lat2d, aggregate, levels=np.linspace(0, 1, 21), cmap="turbo", vmin=0, vmax=1)
    u30 = layers["shallow_30m"]["diagnostics"]["u"]
    v30 = layers["shallow_30m"]["diagnostics"]["v"]
    step_y = max(1, len(lat) // 22)
    step_x = max(1, len(lon) // 34)
    ax4.quiver(
        lon2d[::step_y, ::step_x],
        lat2d[::step_y, ::step_x],
        u30[::step_y, ::step_x],
        v30[::step_y, ::step_x],
        color="white",
        alpha=0.70,
        scale=6.5,
        width=0.0024,
    )
    ax4.set_title("Aggregate Ocean Dynamics Rank\nsurface + 30 m + 100 m", fontweight="bold")
    ax4.set_xlim(92, 99)
    ax4.set_ylim(1, 7)
    ax4.set_xlabel("Bujur (°E)")
    ax4.set_ylabel("Lintang (°N)")
    ax4.grid(alpha=0.18, linestyle="--")
    cb4 = fig.colorbar(im4, ax=ax4, fraction=0.025, pad=0.02)
    cb4.set_label("Score 0–1")

    fig.text(
        0.015,
        0.02,
        "Catatan: diagnostic layer dari turunan medan arus; bukan solver Navier–Stokes penuh dan bukan prediksi pasti.",
        ha="left",
        fontsize=8,
        color="#fde68a",
        style="italic",
    )
    fig.text(0.985, 0.02, "nelaya-ai.com", ha="right", fontsize=9, color="#38bdf8", style="italic")

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)


def narrative(date: str, summary: dict[str, Any]) -> dict[str, Any]:
    agg = summary["aggregate"]
    hotspot = agg.get("hotspot") or {}
    score_stats = agg.get("score_stats", {})
    mean_score = score_stats.get("mean")
    max_score = score_stats.get("max")

    return {
        "short": (
            f"Pada {date}, diagnostic layer v0.8-alpha membaca struktur gerak laut dengan "
            f"skor dinamika rata-rata {mean_score:.3f} dan maksimum {max_score:.3f}."
            if mean_score is not None and max_score is not None
            else "Diagnostic layer v0.8-alpha belum lengkap."
        ),
        "interpretation": [
            "Layer ini membaca vorticity, convergence, strain, kinetic energy, dan advection proxy dari medan arus multi-kedalaman.",
            "Sinyal tinggi menunjukkan area dengan struktur dinamika laut yang lebih aktif, bukan kepastian keberadaan ikan.",
            (
                f"Kandidat dinamika terkuat berada sekitar {hotspot.get('lat'):.2f}°N, "
                f"{hotspot.get('lon'):.2f}°E dengan skor {hotspot.get('score'):.3f}."
                if hotspot
                else "Kandidat hotspot dinamika belum tersedia."
            ),
        ],
        "scientific_caution": (
            "Ini adalah Navier–Stokes-informed diagnostics, bukan full Navier–Stokes solver. "
            "Hasil harus dibaca bersama FGI, Tuna Depth Layer, SST, CHL, SSH, bathymetry, dan validasi lapangan."
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--geojson-threshold", type=float, default=0.70)
    parser.add_argument("--max-points", type=int, default=300)
    parser.add_argument("--no-png", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    f = latest_file(args.date)
    date = extract_date(f) or args.date or datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d")

    print("=" * 78)
    print("NELAYA-AI v0.8-alpha Navier-Stokes-informed Ocean Diagnostics")
    print("=" * 78)
    print(f"Input : {f}")
    print(f"Date  : {date}")

    ds = open_dataset_any(f)
    layers, lat, lon = build_layers(ds)
    aggregate, aggregate_speed = build_aggregate(layers)

    aggregate_hotspot = find_hotspot(lat, lon, aggregate, aggregate_speed)

    layer_summary = {}
    for key, item in layers.items():
        layer_summary[key] = {
            "target_depth_m": item["target_depth_m"],
            "actual_depth_m": item["actual_depth_m"],
            "summary": item["summary"],
        }

    geojson_out = OUT_DIR / "ns_ocean_diagnostics_latest.geojson"
    geojson_info = make_geojson(
        out_file=geojson_out,
        lat=lat,
        lon=lon,
        score=aggregate,
        speed=aggregate_speed,
        threshold=args.geojson_threshold,
        max_points=args.max_points,
    )

    summary = {
        "module": "nelaya_ai_ns_ocean_diagnostics",
        "version": "0.8-alpha",
        "status": "ready",
        "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "snapshot_date": date,
        "source_file": str(f),
        "data_type": "Copernicus CMEMS current multi-depth uo/vo",
        "scientific_position": (
            "Navier–Stokes-informed diagnostics from current derivatives; "
            "not a full numerical Navier–Stokes solver."
        ),
        "diagnostic_terms": [
            "speed",
            "kinetic_energy",
            "vorticity",
            "divergence",
            "convergence",
            "strain",
            "advection_proxy",
            "coriolis_proxy",
        ],
        "domain": {
            "region": "Aceh-Simeulue",
            "lat_min": float(np.nanmin(lat)),
            "lat_max": float(np.nanmax(lat)),
            "lon_min": float(np.nanmin(lon)),
            "lon_max": float(np.nanmax(lon)),
        },
        "target_depths": TARGET_DEPTHS,
        "layers": layer_summary,
        "aggregate": {
            "description": "Weighted NS-informed ocean dynamics rank from surface, 30 m, and 100 m layers.",
            "weights": {
                "surface": 0.20,
                "shallow_30m": 0.45,
                "tuna_100m": 0.35,
            },
            "score_stats": stats(aggregate),
            "hotspot": aggregate_hotspot,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "ns_ocean_diagnostics_today.json"),
            "dashboard_png": str(OUT_DIR / "ns_ocean_diagnostics_dashboard_today.png"),
            "geojson": geojson_info,
        },
    }

    summary["narrative"] = narrative(date, summary)

    json_out = OUT_DIR / "ns_ocean_diagnostics_today.json"
    png_out = OUT_DIR / "ns_ocean_diagnostics_dashboard_today.png"

    json_out.write_text(json.dumps(to_builtin(summary), indent=2, ensure_ascii=False), encoding="utf-8")

    if not args.no_png:
        make_dashboard_png(
            out_png=png_out,
            date=date,
            lat=lat,
            lon=lon,
            layers=layers,
            aggregate=aggregate,
        )

    y, m, d = date.split("-")
    archive_dir = HISTORY_DIR / y / m / d
    archive_dir.mkdir(parents=True, exist_ok=True)

    (archive_dir / f"ns_ocean_diagnostics_{date}.json").write_text(
        json.dumps(to_builtin(summary), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if png_out.exists():
        (archive_dir / f"ns_ocean_diagnostics_dashboard_{date}.png").write_bytes(
            png_out.read_bytes()
        )

    print("=" * 78)
    print("DONE")
    print("=" * 78)
    print(f"JSON    : {json_out}")
    print(f"PNG     : {png_out}")
    print(f"GeoJSON : {geojson_out}")
    print(json.dumps(to_builtin({
        "version": summary["version"],
        "snapshot_date": date,
        "aggregate": summary["aggregate"],
        "narrative": summary["narrative"],
    }), indent=2, ensure_ascii=False))
    print("=" * 78)


if __name__ == "__main__":
    main()
