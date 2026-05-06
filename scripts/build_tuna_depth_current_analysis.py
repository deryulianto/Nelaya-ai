#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

import numpy as np
import xarray as xr

os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT = Path(".")
IN_ROOT = ROOT / "data" / "raw" / "aceh_simeulue" / "cur_depth_nrt"
OUT_DIR = ROOT / "data" / "physics"
HISTORY_DIR = OUT_DIR / "history_tuna_depth_current"

DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


TARGET_DEPTHS = {
    "surface": 0.5,
    "shallow_30m": 30.0,
    "mid_50m": 50.0,
    "deep_75m": 75.0,
    "tuna_100m": 100.0,
}

SPECIES_RULES = {
    "cakalang_surface": {
        "label": "Cakalang / Skipjack surface signal",
        "depth_keys": ["surface", "shallow_30m"],
        "speed_min": 0.05,
        "speed_max": 0.35,
        "note": "Sinyal arus pendukung pelagis permukaan; bukan klaim keberadaan ikan.",
    },
    "yellowfin": {
        "label": "Yellowfin tuna current corridor",
        "depth_keys": ["shallow_30m", "mid_50m", "deep_75m"],
        "speed_min": 0.05,
        "speed_max": 0.35,
        "note": "Sinyal koridor arus pada lapisan 30–75 m.",
    },
    "bigeye_initial": {
        "label": "Bigeye early-depth signal",
        "depth_keys": ["deep_75m", "tuna_100m"],
        "speed_min": 0.03,
        "speed_max": 0.25,
        "note": "Sinyal awal untuk pelagis besar lebih dalam; bigeye dewasa idealnya butuh lapisan lebih dalam lagi.",
    },
}


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


def speed_from_uv(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    return np.sqrt(u ** 2 + v ** 2)


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


def pretty(label: str | None) -> str:
    if not label:
        return "Belum tersedia"
    return " ".join(w.capitalize() for w in label.replace("_", " ").split())


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


def trapezoid_score(speed: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """
    0 outside broad range, 1 inside optimum band.
    Soft shoulders around optimum.
    """
    s = np.asarray(speed, dtype=float)
    out = np.zeros_like(s, dtype=float)

    shoulder = max(0.02, (hi - lo) * 0.35)
    low0 = max(0.0, lo - shoulder)
    high1 = hi + shoulder

    # ramp up
    m = (s >= low0) & (s < lo)
    out[m] = (s[m] - low0) / max(1e-9, lo - low0)

    # optimum
    m = (s >= lo) & (s <= hi)
    out[m] = 1.0

    # ramp down
    m = (s > hi) & (s <= high1)
    out[m] = 1.0 - (s[m] - hi) / max(1e-9, high1 - hi)

    out[~np.isfinite(s)] = np.nan
    return np.clip(out, 0, 1)


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
    """
    Penalize edge cells because domain boundaries often create artificial maxima.
    Returns 1 for safe interior, 0 for edge margin.
    """
    lat2d, lon2d = np.meshgrid(lat, lon, indexing="ij")

    safe = (
        (lat2d > float(np.nanmin(lat)) + margin_deg)
        & (lat2d < float(np.nanmax(lat)) - margin_deg)
        & (lon2d > float(np.nanmin(lon)) + margin_deg)
        & (lon2d < float(np.nanmax(lon)) - margin_deg)
    )

    return safe.astype(float)


def build_candidate_rank_score(
    composite: np.ndarray,
    composite_speed: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
) -> np.ndarray:
    """
    Ranking score for candidate map:
    - keeps composite current-depth suitability
    - adds relative current strength
    - penalizes domain-edge artifacts
    """
    speed_score = normalize01_by_percentile(composite_speed, 10, 90)
    edge_safe = edge_penalty_mask(lat, lon, margin_deg=0.15)

    rank = (
        0.75 * composite
        + 0.25 * speed_score
    )

    rank = rank * edge_safe
    rank[~np.isfinite(composite)] = np.nan

    return np.clip(rank, 0.0, 1.0)


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
                "label": "Tuna depth current suitability candidate",
                "scientific_caution": "Probabilistic current-depth signal, not a fish-location guarantee.",
            },
        }
        for r in rows
    ]

    geojson = {
        "type": "FeatureCollection",
        "name": "NELAYA-AI Tuna Depth Current Candidates",
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


def build_depth_layers(ds: xr.Dataset) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
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
        sp = speed_from_uv(u, v)

        layers[key] = {
            "target_depth_m": target_depth,
            "actual_depth_m": actual_depth,
            "u": u,
            "v": v,
            "speed": sp,
            "speed_stats": stats(sp),
            "vector_mean": vector_mean(u, v),
        }

    assert lat is not None and lon is not None
    return layers, lat, lon


def build_species_scores(layers: dict[str, Any]) -> dict[str, Any]:
    species = {}

    for key, rule in SPECIES_RULES.items():
        layer_scores = []
        layer_speeds = []

        for depth_key in rule["depth_keys"]:
            sp = layers[depth_key]["speed"]
            layer_scores.append(trapezoid_score(sp, rule["speed_min"], rule["speed_max"]))
            layer_speeds.append(sp)

        score = np.nanmean(np.stack(layer_scores, axis=0), axis=0)
        mean_speed = np.nanmean(np.stack(layer_speeds, axis=0), axis=0)

        species[key] = {
            "label": rule["label"],
            "depth_keys": rule["depth_keys"],
            "speed_min": rule["speed_min"],
            "speed_max": rule["speed_max"],
            "note": rule["note"],
            "score": score,
            "mean_speed": mean_speed,
            "score_stats": stats(score),
            "coverage_optimal_fraction": safe_float(np.nanmean(score >= 0.75)),
        }

    return species


def build_composite(species_scores: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    yft = species_scores["yellowfin"]["score"]
    bgt = species_scores["bigeye_initial"]["score"]
    skp = species_scores["cakalang_surface"]["score"]

    weights = {
        "yellowfin": 0.50,
        "bigeye_initial": 0.35,
        "cakalang_surface": 0.15,
    }

    stack = np.stack([yft, bgt, skp], axis=0)
    w = np.array(
        [
            weights["yellowfin"],
            weights["bigeye_initial"],
            weights["cakalang_surface"],
        ],
        dtype=float,
    )[:, None, None]

    valid = np.isfinite(stack)
    weighted = np.where(valid, stack * w, 0.0)
    weight_sum = np.sum(np.where(valid, w, 0.0), axis=0)

    composite = np.full_like(yft, np.nan, dtype=float)
    m = weight_sum > 0
    composite[m] = np.sum(weighted, axis=0)[m] / weight_sum[m]
    composite = np.clip(composite, 0.0, 1.0)

    speed_stack = np.stack(
        [
            species_scores["yellowfin"]["mean_speed"],
            species_scores["bigeye_initial"]["mean_speed"],
        ],
        axis=0,
    )

    composite_speed = np.nanmean(speed_stack, axis=0)

    return composite, composite_speed


def make_dashboard_png(
    out_png: Path,
    date: str,
    lat: np.ndarray,
    lon: np.ndarray,
    layers: dict[str, Any],
    species_scores: dict[str, Any],
    composite: np.ndarray,
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
    gs = fig.add_gridspec(2, 2, width_ratios=[0.95, 1.45], height_ratios=[1, 1], wspace=0.28, hspace=0.34)

    fig.suptitle(
        f"NELAYA-AI — Tuna Depth Current Layer v0.7.3\nPerairan Aceh · Copernicus CMEMS · {date}",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )

    # 1. Depth profile boxplot
    ax1 = fig.add_subplot(gs[0, 0])
    keys = ["surface", "shallow_30m", "tuna_100m"]
    labels = [
        f"{layers[k]['actual_depth_m']:.1f} m\n{ k.replace('_', ' ') }" for k in keys
    ]
    data = []
    for k in keys:
        sp = layers[k]["speed"]
        data.append(sp[np.isfinite(sp)].ravel())

    bp = ax1.boxplot(data, labels=labels, patch_artist=True, showfliers=False)
    for patch in bp["boxes"]:
        patch.set_alpha(0.65)

    ax1.axhspan(0.05, 0.35, color="#22c55e", alpha=0.13, label="Zona optimal YFT (0.05–0.35 m/s)")
    ax1.axhspan(0.03, 0.25, color="#facc15", alpha=0.10, label="Zona optimal Bigeye awal (0.03–0.25 m/s)")
    ax1.set_title("Profil Kecepatan per Kedalaman", fontweight="bold")
    ax1.set_ylabel("Kecepatan arus (m/s)")
    ax1.grid(alpha=0.18)
    ax1.legend(fontsize=7, loc="upper right")

    # 2. Cross-section by longitude at nearest 4N
    ax2 = fig.add_subplot(gs[0, 1])
    target_lat = 4.0
    lat_idx = int(np.nanargmin(np.abs(lat - target_lat)))

    available_keys = ["surface", "shallow_30m", "mid_50m", "deep_75m", "tuna_100m"]
    depth_vals = np.array([layers[k]["actual_depth_m"] for k in available_keys], dtype=float)
    cross = np.vstack([layers[k]["speed"][lat_idx, :] for k in available_keys])

    cf = ax2.contourf(lon, depth_vals, cross, levels=18, cmap="YlGnBu_r")
    ax2.invert_yaxis()
    ax2.axhline(30, color="#facc15", linestyle="--", linewidth=1.0)
    ax2.axhline(100, color="#fb923c", linestyle="--", linewidth=1.0)
    ax2.set_title(f"Cross-Section Zonal\n({lat[lat_idx]:.1f}°N — Perairan Aceh)", fontweight="bold")
    ax2.set_xlabel("Bujur (°E)")
    ax2.set_ylabel("Kedalaman (m)")
    cb = fig.colorbar(cf, ax=ax2, fraction=0.025, pad=0.02)
    cb.set_label("m/s")

    # 3. Coverage per species/depth summary
    ax3 = fig.add_subplot(gs[1, 0])
    names = ["Cakalang", "Yellowfin", "Bigeye awal"]
    vals = [
        100 * (species_scores["cakalang_surface"]["coverage_optimal_fraction"] or 0),
        100 * (species_scores["yellowfin"]["coverage_optimal_fraction"] or 0),
        100 * (species_scores["bigeye_initial"]["coverage_optimal_fraction"] or 0),
    ]
    ax3.bar(names, vals)
    ax3.set_ylim(0, 100)
    ax3.set_ylabel("% grid dengan skor ≥ 0.75")
    ax3.set_title("Coverage Zona Arus Mendukung", fontweight="bold")
    ax3.grid(axis="y", alpha=0.18)
    for i, v in enumerate(vals):
        ax3.text(i, v + 2, f"{v:.0f}%", ha="center", fontsize=8)

    # 4. Composite map
    ax4 = fig.add_subplot(gs[1, 1])
    lon2d, lat2d = np.meshgrid(lon, lat)
    im = ax4.contourf(lon2d, lat2d, composite, levels=np.linspace(0, 1, 21), cmap="turbo", vmin=0, vmax=1)

    # use 30m current arrows
    u = layers["shallow_30m"]["u"]
    v = layers["shallow_30m"]["v"]
    step_y = max(1, len(lat) // 22)
    step_x = max(1, len(lon) // 34)
    ax4.quiver(
        lon2d[::step_y, ::step_x],
        lat2d[::step_y, ::step_x],
        u[::step_y, ::step_x],
        v[::step_y, ::step_x],
        color="white",
        alpha=0.72,
        scale=6.5,
        width=0.0025,
    )

    ax4.set_title("Peta Komposit Sinyal Arus Pelagis Besar\n30–100 m · probabilistik, bukan klaim lokasi ikan", fontweight="bold")
    ax4.set_xlabel("Bujur (°E)")
    ax4.set_ylabel("Lintang (°N)")
    ax4.set_xlim(92, 99)
    ax4.set_ylim(1, 7)
    ax4.grid(alpha=0.18, linestyle="--")

    cb2 = fig.colorbar(im, ax=ax4, fraction=0.025, pad=0.02)
    cb2.set_label("Skor dukungan arus 0–1")

    ax4.text(
        92.15,
        1.1,
        "Catatan: layer ini membaca probabilitas koridor habitat,\nbukan janji keberadaan tuna.",
        fontsize=8,
        color="#fde68a",
        bbox=dict(boxstyle="round,pad=0.35", fc="#1f2937", ec="#facc15", alpha=0.82),
    )

    fig.text(0.985, 0.02, "nelaya-ai.com", ha="right", fontsize=9, color="#38bdf8", style="italic")

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)


def narrative(date: str, summary: dict[str, Any]) -> dict[str, Any]:
    comp = summary["composite"]
    hotspot = comp.get("hotspot") or {}

    raw_stats = comp.get("score_stats", {})
    rank_stats = comp.get("candidate_rank_score_stats") or raw_stats

    mean_rank = rank_stats.get("mean")
    max_rank = rank_stats.get("max")
    mean_raw = raw_stats.get("mean")

    return {
        "short": (
            f"Pada {date}, lapisan arus 30–100 m menunjukkan sinyal kandidat koridor pelagis besar "
            f"dengan skor ranking rata-rata {mean_rank:.3f} dan maksimum {max_rank:.3f}."
            if mean_rank is not None and max_rank is not None
            else "Sinyal arus multi-kedalaman belum lengkap."
        ),
        "interpretation": [
            "Layer ini membaca arus multi-kedalaman sebagai koridor kemungkinan habitat tuna/pelagis besar.",
            (
                f"Composite suitability arus masih luas dengan rata-rata {mean_raw:.3f}, "
                f"lalu dipersempit menjadi candidate ranking score agar kandidat tidak terlalu optimistis."
                if mean_raw is not None
                else "Composite suitability dihitung dari beberapa lapisan arus, lalu diranking ulang secara spasial."
            ),
            "Sinyal tertinggi bukan klaim lokasi ikan, tetapi kandidat area yang lebih layak diamati bersama SST, CHL, SSH, bathymetry, FGI, dan pengalaman nelayan.",
            (
                f"Kandidat terkuat berada sekitar {hotspot.get('lat'):.2f}°N, "
                f"{hotspot.get('lon'):.2f}°E dengan skor ranking {hotspot.get('score'):.3f}."
                if hotspot
                else "Kandidat hotspot belum tersedia."
            ),
        ],
        "ethical_note": "Laut tidak memberi janji; NELAYA-AI membaca probabilitas.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--geojson-threshold", type=float, default=0.72)
    parser.add_argument("--max-points", type=int, default=500)
    parser.add_argument("--no-png", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    f = latest_file(args.date)
    date = extract_date(f) or args.date or datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d")

    print("=" * 78)
    print("NELAYA-AI Tuna Depth Current Analysis v0.7.3")
    print("=" * 78)
    print(f"Input : {f}")
    print(f"Date  : {date}")

    ds = open_dataset_any(f)
    layers, lat, lon = build_depth_layers(ds)
    species_scores = build_species_scores(layers)
    composite, composite_speed = build_composite(species_scores)
    candidate_rank_score = build_candidate_rank_score(
                     composite=composite,
                    composite_speed=composite_speed,
                    lat=lat,
                    lon=lon,
          )

    comp_hotspot = find_hotspot(lat, lon, candidate_rank_score, composite_speed)

    layer_summary = {}
    for k, item in layers.items():
        layer_summary[k] = {
            "target_depth_m": item["target_depth_m"],
            "actual_depth_m": item["actual_depth_m"],
            "speed_stats": item["speed_stats"],
            "vector_mean": item["vector_mean"],
        }

    species_summary = {}
    for k, item in species_scores.items():
        hs = find_hotspot(lat, lon, item["score"], item["mean_speed"])
        species_summary[k] = {
            "label": item["label"],
            "depth_keys": item["depth_keys"],
            "speed_min": item["speed_min"],
            "speed_max": item["speed_max"],
            "note": item["note"],
            "score_stats": item["score_stats"],
            "coverage_optimal_fraction": item["coverage_optimal_fraction"],
            "hotspot": hs,
        }

    geojson_out = OUT_DIR / "tuna_depth_current_latest.geojson"
    geojson_info = make_geojson(
                     out_file=geojson_out,
                    lat=lat,
                    lon=lon,
                    score=candidate_rank_score,
                    speed=composite_speed,
                    threshold=args.geojson_threshold,
                   max_points=args.max_points,
          )

    summary = {
        "module": "nelaya_ai_tuna_depth_current_analysis",
        "version": "0.7.3-alpha.1",
        "status": "ready",
        "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "snapshot_date": date,
        "source_file": str(f),
        "data_type": "Copernicus CMEMS current multi-depth uo/vo",
        "scientific_position": "Probabilistic current-depth habitat corridor signal, not a fish-location claim.",
        "domain": {
            "region": "Aceh-Simeulue",
            "lat_min": float(np.nanmin(lat)),
            "lat_max": float(np.nanmax(lat)),
            "lon_min": float(np.nanmin(lon)),
            "lon_max": float(np.nanmax(lon)),
        },
        "target_depths": TARGET_DEPTHS,
        "layers": layer_summary,
        "species": species_summary,
        "composite": {
            "description": "Weighted current-depth support for large pelagic/tuna corridor",
            "weights": {
                "yellowfin": 0.50,
                "bigeye_initial": 0.35,
                "cakalang_surface": 0.15,
            },
            "score_stats": stats(composite),
            "candidate_rank_score_stats": stats(candidate_rank_score), 
            "hotspot": comp_hotspot,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "tuna_depth_current_today.json"),
            "dashboard_png": str(OUT_DIR / "tuna_depth_current_dashboard_today.png"),
            "geojson": geojson_info,
        },
    }

    summary["narrative"] = narrative(date, summary)

    json_out = OUT_DIR / "tuna_depth_current_today.json"
    png_out = OUT_DIR / "tuna_depth_current_dashboard_today.png"

    json_out.write_text(json.dumps(to_builtin(summary), indent=2, ensure_ascii=False), encoding="utf-8")

    if not args.no_png:
        make_dashboard_png(
            out_png=png_out,
            date=date,
            lat=lat,
            lon=lon,
            layers=layers,
            species_scores=species_scores,
            composite=composite,
        )

    y, m, d = date.split("-")
    archive_dir = HISTORY_DIR / y / m / d
    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(json_out, archive_dir / f"tuna_depth_current_{date}.json")
    if png_out.exists():
        shutil.copy2(png_out, archive_dir / f"tuna_depth_current_dashboard_{date}.png")

    print("=" * 78)
    print("DONE")
    print("=" * 78)
    print(f"JSON    : {json_out}")
    print(f"PNG     : {png_out}")
    print(f"GeoJSON : {geojson_out}")
    print(json.dumps(to_builtin({
        "snapshot_date": date,
        "composite": summary["composite"],
        "species": {
            k: {
                "coverage_optimal_fraction": v["coverage_optimal_fraction"],
                "hotspot": v["hotspot"],
            }
            for k, v in species_summary.items()
        },
    }), indent=2, ensure_ascii=False))
    print("=" * 78)


if __name__ == "__main__":
    main()
