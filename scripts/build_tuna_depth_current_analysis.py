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
THERMAL_ROOT = ROOT / "data" / "raw" / "aceh_simeulue" / "thermal_depth_nrt"
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


def clip01(x: Any, default: float = 0.0) -> float:
    v = safe_float(x, default)
    if v is None:
        return default
    return float(max(0.0, min(1.0, v)))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return float(2 * r * math.asin(math.sqrt(max(0.0, min(1.0, a)))))


def build_vertical_diagnostics(layers: dict[str, Any]) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """
    v0.7.4:
    Membaca kestabilan vertikal lapisan 30–100 m:
    - speed_mean_30_100
    - vertical_shear_per_m
    - directional_coherence 0–1
    """
    keys = ["shallow_30m", "mid_50m", "deep_75m", "tuna_100m"]
    keys = [k for k in keys if k in layers]

    if len(keys) < 2:
        empty = np.full_like(next(iter(layers.values()))["speed"], np.nan, dtype=float)
        return {
            "status": "insufficient_layers",
            "depth_keys": keys,
            "message": "Lapisan kedalaman tidak cukup untuk diagnostik vertikal.",
        }, {
            "speed_mean_30_100": empty,
            "vertical_shear_per_m": empty,
            "directional_coherence": empty,
        }

    u_stack = np.stack([layers[k]["u"] for k in keys], axis=0).astype(float)
    v_stack = np.stack([layers[k]["v"] for k in keys], axis=0).astype(float)
    speed_stack = np.stack([layers[k]["speed"] for k in keys], axis=0).astype(float)
    depth_vals = np.array([layers[k]["actual_depth_m"] for k in keys], dtype=float)

    speed_mean = np.nanmean(speed_stack, axis=0)

    # Robust vertical shear:
    # Pakai pasangan kedalaman valid paling dangkal dan paling dalam per-grid.
    # Ini mencegah shear menjadi NaN hanya karena salah satu endpoint kosong.
    ny, nx = speed_stack.shape[1], speed_stack.shape[2]
    shear = np.full((ny, nx), np.nan, dtype=float)

    for ii in range(ny):
        for jj in range(nx):
            valid_k = np.where(
                np.isfinite(u_stack[:, ii, jj])
                & np.isfinite(v_stack[:, ii, jj])
                & np.isfinite(depth_vals)
            )[0]

            if valid_k.size < 2:
                continue

            k0 = int(valid_k[0])
            k1 = int(valid_k[-1])
            d_total = max(1e-6, float(abs(depth_vals[k1] - depth_vals[k0])))

            du = float(u_stack[k1, ii, jj] - u_stack[k0, ii, jj])
            dv = float(v_stack[k1, ii, jj] - v_stack[k0, ii, jj])
            shear[ii, jj] = math.sqrt(du ** 2 + dv ** 2) / d_total

    eps = 1e-9
    unit_u = np.where(speed_stack > eps, u_stack / np.maximum(speed_stack, eps), np.nan)
    unit_v = np.where(speed_stack > eps, v_stack / np.maximum(speed_stack, eps), np.nan)
    coherence = np.sqrt(np.nanmean(unit_u, axis=0) ** 2 + np.nanmean(unit_v, axis=0) ** 2)
    coherence = np.clip(coherence, 0.0, 1.0)
    coherence[~np.isfinite(speed_mean)] = np.nan

    maps = {
        "speed_mean_30_100": speed_mean,
        "vertical_shear_per_m": shear,
        "directional_coherence": coherence,
    }

    summary = {
        "status": "ready",
        "depth_keys": keys,
        "actual_depths_m": [safe_float(layers[k]["actual_depth_m"]) for k in keys],
        "speed_mean_30_100_stats": stats(speed_mean),
        "vertical_shear_per_m_stats": stats(shear),
        "directional_coherence_stats": stats(coherence),
        "interpretation": (
            "Directional coherence mendekati 1 berarti arah arus antar-kedalaman relatif sejalan. "
            "Vertical shear tinggi berarti lapisan arus lebih mudah berubah antar-kedalaman."
        ),
    }

    return summary, maps


def build_audit(
    ds: xr.Dataset,
    source_file: Path,
    date: str,
    layers: dict[str, Any],
    lat: np.ndarray,
    lon: np.ndarray,
    composite: np.ndarray,
    candidate_rank_score: np.ndarray,
    thermal_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    depth_name = detect_coord(ds, ["depth", "depthu", "depthv", "lev"])
    depth_vals: list[float] = []
    if depth_name:
        vals = np.asarray(ds[depth_name].values, dtype=float).ravel()
        depth_vals = [float(x) for x in vals if np.isfinite(x)]

    rank_valid = np.isfinite(candidate_rank_score)
    composite_valid = np.isfinite(composite)

    target_actuals = {
        k: safe_float(v.get("actual_depth_m"))
        for k, v in layers.items()
    }

    speed_keys = [k for k in ["shallow_30m", "mid_50m", "deep_75m", "tuna_100m"] if k in layers]
    if speed_keys:
        speed_stack = np.stack([layers[k]["speed"] for k in speed_keys], axis=0)
        mean_speed_30_100 = np.nanmean(speed_stack, axis=0)
    else:
        mean_speed_30_100 = np.full_like(composite, np.nan, dtype=float)

    grid_count = int(len(lat) * len(lon))
    valid_grid_count = int(np.sum(rank_valid))

    file_size_mb = None
    try:
        file_size_mb = round(source_file.stat().st_size / (1024 * 1024), 3)
    except Exception:
        pass

    return {
        "status": "ready",
        "data_date": date,
        "generated_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "source_nc": str(source_file),
        "source_nc_size_mb": file_size_mb,
        "dataset_dims": {str(k): int(v) for k, v in ds.sizes.items()},
        "data_vars": list(ds.data_vars),
        "grid_shape": {
            "lat": int(len(lat)),
            "lon": int(len(lon)),
            "cells": grid_count,
        },
        "available_depth_count": len(depth_vals),
        "available_depth_min_m": safe_float(np.nanmin(depth_vals)) if depth_vals else None,
        "available_depth_max_m": safe_float(np.nanmax(depth_vals)) if depth_vals else None,
        "available_depths_m": depth_vals,
        "target_depths_requested_m": TARGET_DEPTHS,
        "target_depths_actual_m": target_actuals,
        "target_depth_coverage_fraction": safe_float(len(target_actuals) / max(1, len(TARGET_DEPTHS))),
        "valid_grid_count": valid_grid_count,
        "missing_fraction_rank": safe_float(1.0 - valid_grid_count / max(1, grid_count)),
        "valid_composite_count": int(np.sum(composite_valid)),
        "speed_30_100_stats": stats(mean_speed_30_100),
        "rank_score_stats": stats(candidate_rank_score),
        "note": (
            "Audit ini memeriksa kesiapan data uo/vo multi-kedalaman dan kualitas sinyal fisik. "
            "Audit belum berarti kepastian ekologis atau hasil tangkapan."
        ),
    }


def build_confidence_breakdown(
    audit: dict[str, Any],
    vertical_diagnostics: dict[str, Any],
    composite: np.ndarray,
    candidate_rank_score: np.ndarray,
    thermal_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing = safe_float(audit.get("missing_fraction_rank"), 1.0)
    data_availability = clip01(1.0 - (missing or 0.0))

    depth_coverage = clip01(audit.get("target_depth_coverage_fraction"), 0.0)

    rank_mean = safe_float(stats(candidate_rank_score).get("mean"), 0.0) or 0.0
    rank_p90 = safe_float(stats(candidate_rank_score).get("p90"), 0.0) or 0.0
    coherence_mean = safe_float(
        (vertical_diagnostics.get("directional_coherence_stats") or {}).get("mean"),
        0.0,
    ) or 0.0

    physical_signal = clip01(0.45 * rank_mean + 0.25 * rank_p90 + 0.30 * coherence_mean)

    thermal_diagnostics = thermal_diagnostics or {}
    thermal_ready = thermal_diagnostics.get("status") == "ready"
    thermal_valid_fraction = safe_float(thermal_diagnostics.get("valid_fraction"), 0.0) or 0.0
    thermal_score_mean = safe_float(
        (thermal_diagnostics.get("thermal_score_stats") or {}).get("mean"),
        0.0,
    ) or 0.0

    if thermal_ready:
        ecological_confidence = clip01(0.35 + 0.15 * thermal_valid_fraction + 0.15 * thermal_score_mean)
    else:
        ecological_confidence = 0.35

    # v0.8.0 belum mengunci gate keselamatan dari wave/wind/operational limits.
    safety_confidence = 0.50

    overall = clip01(
        0.25 * data_availability
        + 0.20 * depth_coverage
        + 0.30 * physical_signal
        + 0.15 * ecological_confidence
        + 0.10 * safety_confidence
    )

    return {
        "data_availability_confidence": round(data_availability, 3),
        "depth_coverage_confidence": round(depth_coverage, 3),
        "physical_signal_confidence": round(physical_signal, 3),
        "ecological_confidence": round(ecological_confidence, 3),
        "safety_confidence": round(safety_confidence, 3),
        "overall_confidence": round(overall, 3),
        "confidence_label": (
            "tinggi" if overall >= 0.75 else
            "sedang" if overall >= 0.55 else
            "awal/perlu validasi"
        ),
        "notes": [
            "Confidence fisik membaca data arus multi-kedalaman dan koherensi vertikal.",
            "Confidence ekologis sengaja ditahan karena suhu bawah permukaan, oksigen terlarut, CHL/BGC, SSH/front, dan validasi tangkapan belum masuk.",
            "Confidence keselamatan sengaja ditahan karena wave/wind gate belum digabungkan di layer ini.",
        ],
    }


def build_clustered_candidates(
    lat: np.ndarray,
    lon: np.ndarray,
    score: np.ndarray,
    speed: np.ndarray,
    threshold: float,
    max_clusters: int = 7,
    radius_km: float = 35.0,
    max_points_scan: int = 500,
    vertical_maps: dict[str, np.ndarray] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for i in range(score.shape[0]):
        for j in range(score.shape[1]):
            sc = safe_float(score[i, j])
            if sc is None or sc < threshold:
                continue
            rows.append({
                "i": i,
                "j": j,
                "lat": float(lat[i]),
                "lon": float(lon[j]),
                "score": sc,
                "speed_ms": safe_float(speed[i, j]),
                "coherence": safe_float((vertical_maps or {}).get("directional_coherence", np.full_like(score, np.nan))[i, j]) if vertical_maps else None,
                "shear_per_m": safe_float((vertical_maps or {}).get("vertical_shear_per_m", np.full_like(score, np.nan))[i, j]) if vertical_maps else None,
            })

    rows = sorted(rows, key=lambda r: r["score"], reverse=True)[:max_points_scan]

    clusters: list[dict[str, Any]] = []

    for r in rows:
        chosen = None
        chosen_dist = None

        for c in clusters:
            dist = haversine_km(r["lat"], r["lon"], c["centroid_lat"], c["centroid_lon"])
            if dist <= radius_km and (chosen_dist is None or dist < chosen_dist):
                chosen = c
                chosen_dist = dist

        if chosen is None:
            if len(clusters) >= max_clusters:
                continue

            clusters.append({
                "cluster_id": len(clusters) + 1,
                "centroid_lat": r["lat"],
                "centroid_lon": r["lon"],
                "max_score": r["score"],
                "mean_score": r["score"],
                "mean_speed_ms": r["speed_ms"],
                "top_lat": r["lat"],
                "top_lon": r["lon"],
                "top_speed_ms": r["speed_ms"],
                "top_directional_coherence": r["coherence"],
                "top_vertical_shear_per_m": r["shear_per_m"],
                "member_count": 1,
                "_sum_score": r["score"],
                "_sum_speed": r["speed_ms"] or 0.0,
                "_sum_weight": r["score"],
                "_max_distance_km": 0.0,
            })
            continue

        w_old = chosen["_sum_weight"]
        w_new = max(1e-6, r["score"])
        chosen["centroid_lat"] = (chosen["centroid_lat"] * w_old + r["lat"] * w_new) / (w_old + w_new)
        chosen["centroid_lon"] = (chosen["centroid_lon"] * w_old + r["lon"] * w_new) / (w_old + w_new)
        chosen["_sum_weight"] += w_new
        chosen["_sum_score"] += r["score"]
        chosen["_sum_speed"] += r["speed_ms"] or 0.0
        chosen["member_count"] += 1
        chosen["mean_score"] = chosen["_sum_score"] / chosen["member_count"]
        chosen["mean_speed_ms"] = chosen["_sum_speed"] / chosen["member_count"]
        chosen["_max_distance_km"] = max(chosen["_max_distance_km"], chosen_dist or 0.0)

        if r["score"] > chosen["max_score"]:
            chosen["max_score"] = r["score"]
            chosen["top_lat"] = r["lat"]
            chosen["top_lon"] = r["lon"]
            chosen["top_speed_ms"] = r["speed_ms"]
            chosen["top_directional_coherence"] = r["coherence"]
            chosen["top_vertical_shear_per_m"] = r["shear_per_m"]

    clusters = sorted(clusters, key=lambda c: c["max_score"], reverse=True)

    clean = []
    for idx, c in enumerate(clusters, start=1):
        clean.append({
            "cluster_id": idx,
            "label": f"Koridor kandidat #{idx}",
            "centroid_lat": safe_float(c["centroid_lat"]),
            "centroid_lon": safe_float(c["centroid_lon"]),
            "top_lat": safe_float(c["top_lat"]),
            "top_lon": safe_float(c["top_lon"]),
            "max_score": safe_float(c["max_score"]),
            "mean_score": safe_float(c["mean_score"]),
            "mean_speed_ms": safe_float(c["mean_speed_ms"]),
            "top_speed_ms": safe_float(c["top_speed_ms"]),
            "member_count": int(c["member_count"]),
            "radius_km_est": safe_float(c["_max_distance_km"]),
            "top_directional_coherence": safe_float(c["top_directional_coherence"]),
            "top_vertical_shear_per_m": safe_float(c["top_vertical_shear_per_m"]),
            "interpretation": (
                "Klaster kandidat koridor arus kedalaman 30–100 m. "
                "Gunakan bersama SST, CHL, SSH/front, bathymetry, FGI, cuaca, keselamatan, dan pengalaman nelayan."
            ),
        })

    return clean


def nearest_cluster_id(
    lat0: float,
    lon0: float,
    clustered_candidates: list[dict[str, Any]] | None,
    max_km: float = 45.0,
) -> int | None:
    if not clustered_candidates:
        return None

    best_id = None
    best_dist = None
    for c in clustered_candidates:
        clat = safe_float(c.get("centroid_lat"))
        clon = safe_float(c.get("centroid_lon"))
        if clat is None or clon is None:
            continue
        d = haversine_km(lat0, lon0, clat, clon)
        if best_dist is None or d < best_dist:
            best_dist = d
            best_id = c.get("cluster_id")

    if best_dist is not None and best_dist <= max_km:
        return int(best_id)
    return None


def candidate_reason(score: float | None, speed_ms: float | None, coherence: float | None, shear: float | None) -> str:
    parts = []

    if score is not None and score >= 0.85:
        parts.append("Skor ranking kuat untuk koridor arus kedalaman.")
    elif score is not None and score >= 0.72:
        parts.append("Skor ranking masuk kandidat observasi.")
    else:
        parts.append("Sinyal masih perlu dibaca hati-hati.")

    if speed_ms is not None:
        parts.append(f"Kecepatan rata-rata lapisan kandidat sekitar {speed_ms:.3f} m/s.")

    if coherence is not None:
        if coherence >= 0.75:
            parts.append("Arah arus antar-kedalaman cukup koheren.")
        elif coherence >= 0.50:
            parts.append("Koherensi arah arus sedang.")
        else:
            parts.append("Arah arus antar-kedalaman relatif berubah.")

    if shear is not None:
        if shear <= 0.004:
            parts.append("Vertical shear relatif rendah.")
        elif shear <= 0.008:
            parts.append("Vertical shear sedang.")
        else:
            parts.append("Vertical shear cukup tinggi sehingga perlu kehati-hatian interpretasi.")

    return " ".join(parts)



def habitat_score_v080(
    rank_score: float | None,
    thermal_score: float | None,
    directional_coherence: float | None,
) -> float | None:
    """
    v0.8.1 thermal-aware habitat score.

    This is still a probabilistic corridor score, not a fish-location claim.
    Weighted from current-depth ranking, thermal gate, and vertical coherence.
    """
    rs = safe_float(rank_score)
    ts = safe_float(thermal_score)
    coh = safe_float(directional_coherence)

    if rs is None:
        return None

    # If thermal is missing, keep score current-aware but do not over-penalize.
    if ts is None:
        ts = 0.50

    if coh is None:
        coh = 0.50

    return round(clip01(0.65 * rs + 0.25 * ts + 0.10 * coh), 6)


def enrich_clustered_candidates_with_thermal(
    lat: np.ndarray,
    lon: np.ndarray,
    score: np.ndarray,
    vertical_maps: dict[str, np.ndarray] | None,
    thermal_maps: dict[str, np.ndarray] | None,
    clustered_candidates: list[dict[str, Any]],
    threshold: float,
    default_radius_km: float = 35.0,
) -> list[dict[str, Any]]:
    """
    Add thermal-aware summaries to each candidate corridor cluster.
    """
    if not clustered_candidates:
        return clustered_candidates

    thermal_maps = thermal_maps or {}
    vertical_maps = vertical_maps or {}

    thermal_score_map = thermal_maps.get("thermal_score")
    temp_map = thermal_maps.get("temperature_mean_30_100_c")
    coh_map = vertical_maps.get("directional_coherence")

    if thermal_score_map is None and temp_map is None:
        for c in clustered_candidates:
            c["thermal_status"] = "missing"
            c["habitat_score_v080_mean"] = habitat_score_v080(
                c.get("mean_score"),
                None,
                c.get("top_directional_coherence"),
            )
        return clustered_candidates

    lon2d, lat2d = np.meshgrid(lon, lat)

    enriched = []
    for c in clustered_candidates:
        clat = safe_float(c.get("centroid_lat"))
        clon = safe_float(c.get("centroid_lon"))

        if clat is None or clon is None:
            enriched.append(c)
            continue

        radius = safe_float(c.get("radius_km_est"), default_radius_km) or default_radius_km
        radius = max(default_radius_km, radius)

        # Fast approximate distance is enough for cluster summary in small Aceh ROI.
        km_y = (lat2d - clat) * 111.0
        km_x = (lon2d - clon) * 111.0 * math.cos(math.radians(clat))
        dist = np.sqrt(km_x ** 2 + km_y ** 2)

        mask = (dist <= radius) & np.isfinite(score) & (score >= threshold)

        if thermal_score_map is not None:
            ts_vals = np.asarray(thermal_score_map, dtype=float)[mask]
            ts_vals = ts_vals[np.isfinite(ts_vals)]
            mean_thermal = safe_float(np.nanmean(ts_vals)) if ts_vals.size else None
        else:
            mean_thermal = None

        if temp_map is not None:
            temp_vals = np.asarray(temp_map, dtype=float)[mask]
            temp_vals = temp_vals[np.isfinite(temp_vals)]
            mean_temp = safe_float(np.nanmean(temp_vals)) if temp_vals.size else None
        else:
            mean_temp = None

        if coh_map is not None:
            coh_vals = np.asarray(coh_map, dtype=float)[mask]
            coh_vals = coh_vals[np.isfinite(coh_vals)]
            mean_coh = safe_float(np.nanmean(coh_vals)) if coh_vals.size else safe_float(c.get("top_directional_coherence"))
        else:
            mean_coh = safe_float(c.get("top_directional_coherence"))

        habitat_vals = []
        if np.any(mask):
            rows, cols = np.where(mask)
            for ii, jj in zip(rows, cols):
                rs = safe_float(score[ii, jj])
                ts = safe_float(thermal_score_map[ii, jj]) if thermal_score_map is not None else None
                coh = safe_float(coh_map[ii, jj]) if coh_map is not None else mean_coh
                hs = habitat_score_v080(rs, ts, coh)
                if hs is not None:
                    habitat_vals.append(hs)

        mean_habitat = safe_float(np.nanmean(habitat_vals)) if habitat_vals else habitat_score_v080(
            c.get("mean_score"),
            mean_thermal,
            mean_coh,
        )

        # top point thermal lookup
        top_lat = safe_float(c.get("top_lat"))
        top_lon = safe_float(c.get("top_lon"))
        top_thermal = None
        top_temp = None
        top_habitat = None

        if top_lat is not None and top_lon is not None:
            ii = int(np.nanargmin(np.abs(lat - top_lat)))
            jj = int(np.nanargmin(np.abs(lon - top_lon)))
            top_thermal = safe_float(thermal_score_map[ii, jj]) if thermal_score_map is not None else None
            top_temp = safe_float(temp_map[ii, jj]) if temp_map is not None else None
            top_habitat = habitat_score_v080(c.get("max_score"), top_thermal, c.get("top_directional_coherence"))

        c = dict(c)
        c.update({
            "thermal_status": "ready" if mean_thermal is not None or mean_temp is not None else "missing",
            "mean_thermal_score": mean_thermal,
            "mean_temperature_30_100_c": mean_temp,
            "mean_directional_coherence": mean_coh,
            "habitat_score_v080_mean": mean_habitat,
            "top_thermal_score": top_thermal,
            "top_temperature_30_100_c": top_temp,
            "top_habitat_score_v080": top_habitat,
            "interpretation": (
                "Klaster kandidat koridor arus 30–100 m yang kini dibaca bersama thermal gate bawah permukaan. "
                "Tetap gunakan bersama SST, CHL, SSH/front, bathymetry, cuaca, keselamatan, dan pengalaman nelayan."
            ),
        })
        enriched.append(c)

    return enriched


def make_geojson(
    out_file: Path,
    lat: np.ndarray,
    lon: np.ndarray,
    score: np.ndarray,
    speed: np.ndarray,
    threshold: float,
    max_points: int,
    vertical_maps: dict[str, np.ndarray] | None = None,
    clustered_candidates: list[dict[str, Any]] | None = None,
    thermal_maps: dict[str, np.ndarray] | None = None,
    ssh_maps: dict[str, np.ndarray] | None = None,
    safety_maps: dict[str, np.ndarray] | None = None,
):
    rows = []
    vertical_maps = vertical_maps or {}
    thermal_maps = thermal_maps or {}
    ssh_maps = ssh_maps or {}
    safety_maps = safety_maps or {}

    coh_map = vertical_maps.get("directional_coherence")
    shear_map = vertical_maps.get("vertical_shear_per_m")

    thermal_score_map = thermal_maps.get("thermal_score")
    temp_map = thermal_maps.get("temperature_mean_30_100_c")
    ssh_front_map = ssh_maps.get("ssh_front_score")
    ssh_grad_map = ssh_maps.get("ssh_gradient_m_per_m")
    safety_score_map = safety_maps.get("safety_score")
    risk_score_map = safety_maps.get("combined_risk_score")
    wave_map = safety_maps.get("wave_m")
    wind_map = safety_maps.get("wind_speed_ms")

    for i in range(score.shape[0]):
        for j in range(score.shape[1]):
            sc = safe_float(score[i, j])
            if sc is None or sc < threshold:
                continue

            coherence = safe_float(coh_map[i, j]) if coh_map is not None else None
            shear = safe_float(shear_map[i, j]) if shear_map is not None else None
            sp = safe_float(speed[i, j])

            thermal_score = safe_float(thermal_score_map[i, j]) if thermal_score_map is not None else None
            temp_mean = safe_float(temp_map[i, j]) if temp_map is not None else None
            ssh_front = safe_float(ssh_front_map[i, j]) if ssh_front_map is not None else None
            ssh_grad = safe_float(ssh_grad_map[i, j]) if ssh_grad_map is not None else None
            habitat_score = habitat_score_v080(sc, thermal_score, coherence)
            habitat_score_082 = habitat_score_v082(sc, thermal_score, coherence, ssh_front)
            safety_score = safe_float(safety_score_map[i, j]) if safety_score_map is not None else None
            risk_score = safe_float(risk_score_map[i, j]) if risk_score_map is not None else None
            wave_val = safe_float(wave_map[i, j]) if wave_map is not None else None
            wind_val = safe_float(wind_map[i, j]) if wind_map is not None else None
            operational_score = operational_habitat_score_v083(habitat_score_082, safety_score)
            operational_decision = operational_decision_v084(
                operational_score,
                habitat_score_082,
                safety_score,
                wave_val,
                wind_val,
            )

            rows.append(
                {
                    "lat": float(lat[i]),
                    "lon": float(lon[j]),
                    "score": sc,
                    "speed_ms": sp,
                    "directional_coherence": coherence,
                    "vertical_shear_per_m": shear,
                    "thermal_score": thermal_score,
                    "temperature_mean_30_100_c": temp_mean,
                    "habitat_score_v080": habitat_score,
                    "habitat_score_v082": habitat_score_082,
                    "ssh_front_score": ssh_front,
                    "ssh_gradient_m_per_m": ssh_grad,
                    "safety_score": safety_score,
                    "combined_risk_score": risk_score,
                    "wave_m": wave_val,
                    "wind_speed_ms": wind_val,
                    "operational_habitat_score_v083": operational_score,
                    "operational_decision_v084": operational_decision,
                }
            )

    rows = sorted(
        rows,
        key=lambda r: (
            r["operational_habitat_score_v083"] if r.get("operational_habitat_score_v083") is not None else (r["habitat_score_v082"] if r.get("habitat_score_v082") is not None else (r["habitat_score_v080"] if r["habitat_score_v080"] is not None else r["score"]))
        ),
        reverse=True,
    )[:max_points]

    features = []
    for r in rows:
        cluster_id = nearest_cluster_id(r["lat"], r["lon"], clustered_candidates)

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
                "properties": {
                    "score": r["score"],
                    "rank_score": r["score"],
                    "habitat_score_v080": r["habitat_score_v080"],
                    "habitat_score_v082": r.get("habitat_score_v082"),
                    "ssh_front_score": r.get("ssh_front_score"),
                    "ssh_gradient_m_per_m": r.get("ssh_gradient_m_per_m"),
                    "safety_score": r.get("safety_score"),
                    "combined_risk_score": r.get("combined_risk_score"),
                    "wave_m": r.get("wave_m"),
                    "wind_speed_ms": r.get("wind_speed_ms"),
                    "operational_habitat_score_v083": r.get("operational_habitat_score_v083"),
                    "operational_decision_v084": r.get("operational_decision_v084"),
                    "speed_ms": r["speed_ms"],
                    "directional_coherence": r["directional_coherence"],
                    "vertical_shear_per_m": r["vertical_shear_per_m"],
                    "thermal_score": r["thermal_score"],
                    "temperature_mean_30_100_c": r["temperature_mean_30_100_c"],
                    "cluster_id": cluster_id,
                    "candidate_type": "current_depth_thermal_corridor",
                    "depth_band": "30–100 m",
                    "label": "Tuna depth current + thermal suitability candidate",
                    "physical_reason": candidate_reason(
                        r["score"],
                        r["speed_ms"],
                        r["directional_coherence"],
                        r["vertical_shear_per_m"],
                    ),
                    "thermal_reason": (
                        f"Thermal gate mendukung dengan suhu rata-rata 30–100 m sekitar "
                        f"{r['temperature_mean_30_100_c']:.2f} °C dan thermal score {r['thermal_score']:.2f}."
                        if r["temperature_mean_30_100_c"] is not None and r["thermal_score"] is not None
                        else "Thermal gate belum tersedia untuk titik ini."
                    ),
                    "ssh_front_reason": (
                        f"SSH/front support terbaca {r.get('ssh_front_score'):.2f} dari gradien muka laut."
                        if r.get("ssh_front_score") is not None
                        else "SSH/front support belum tersedia untuk titik ini."
                    ),
                    "safety_reason": (
                        f"Safety Gate terbaca {r.get('safety_score'):.2f}; gelombang sekitar {r.get('wave_m'):.2f} m dan angin sekitar {r.get('wind_speed_ms'):.2f} m/s."
                        if r.get("safety_score") is not None and r.get("wave_m") is not None and r.get("wind_speed_ms") is not None
                        else (
                            f"Safety Gate terbaca {r.get('safety_score'):.2f}; gelombang sekitar {r.get('wave_m'):.2f} m. Data angin lokal titik ini belum lengkap."
                            if r.get("safety_score") is not None and r.get("wave_m") is not None
                            else "Safety Gate belum lengkap untuk titik ini."
                        )
                    ),
                    "scientific_caution": (
                        "Probabilistic current-depth and thermal signal, not a fish-location guarantee. "
                        "Read together with SST, CHL, SSH/front, bathymetry, FGI, weather, safety, and fisher knowledge."
                    ),
                },
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "name": "NELAYA-AI Tuna Depth Current Candidates",
        "version": "0.8.4-alpha.1",
        "features": features,
    }

    out_file.write_text(json.dumps(to_builtin(geojson), indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "created": True,
        "file": str(out_file),
        "threshold": threshold,
        "point_count": len(features),
        "max_points": max_points,
        "cluster_count": len(clustered_candidates or []),
        "thermal_aware": thermal_score_map is not None or temp_map is not None,
        "ssh_front_aware": ssh_front_map is not None,
        "safety_aware": safety_score_map is not None,
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



def thermal_file_for_date(date: str) -> Path:
    y, m, _ = date.split("-")
    return THERMAL_ROOT / y / m / f"thermal_depth_nrt_aceh_{date}.nc"


def read_thermal_h5(path: Path) -> dict[str, Any]:
    """
    Read CMEMS thetao NetCDF/HDF5 directly with h5py.

    Why h5py?
    Some thetao files trigger HDF5 dimension-scale errors when opened
    through xarray/h5netcdf on this server:
    RuntimeError: H5DSget_num_scales.
    Direct h5py reading avoids dimension-scale parsing.
    """
    
    with h5py.File(path, "r") as f:
        required = ["thetao", "depth", "latitude", "longitude"]
        missing = [k for k in required if k not in f]
        if missing:
            raise RuntimeError(f"Missing thermal datasets: {missing}. keys={list(f.keys())}")

        thetao = np.asarray(f["thetao"][...], dtype=float)
        depth = np.asarray(f["depth"][...], dtype=float).ravel()
        lat = np.asarray(f["latitude"][...], dtype=float).ravel()
        lon = np.asarray(f["longitude"][...], dtype=float).ravel()

        attrs = {}
        try:
            attrs = {k: v.decode() if isinstance(v, bytes) else v for k, v in f["thetao"].attrs.items()}
        except Exception:
            attrs = {}

    return {
        "thetao": thetao,
        "depth": depth,
        "lat": lat,
        "lon": lon,
        "attrs": attrs,
    }



def clean_temperature_c(temp: np.ndarray, attrs: dict[str, Any] | None = None) -> np.ndarray:
    """
    Clean CMEMS thetao temperature array.

    Some NetCDF/HDF5 files store missing values as very large fill values
    around 1e20–1e36. These must be masked before statistics and scoring.
    """
    attrs = attrs or {}
    arr = np.asarray(temp, dtype=float).copy()

    fill_candidates = []
    for key in ["_FillValue", "missing_value"]:
        if key in attrs:
            try:
                fill_candidates.append(float(attrs[key]))
            except Exception:
                pass

    for fv in fill_candidates:
        arr[np.isclose(arr, fv, rtol=1e-6, atol=0.0)] = np.nan

    # Physical sanity mask for ocean temperature in degrees Celsius.
    # This removes CMEMS fill values even when attrs are not decoded cleanly.
    arr[(arr < -5.0) | (arr > 45.0)] = np.nan

    return arr


def thermal_suitability_score(temp_c: np.ndarray) -> np.ndarray:
    """
    Broad tropical large-pelagic thermal gate for v0.8.0-alpha.1.

    Interpretation:
    - This is not species-specific tuna habitat certainty.
    - It only checks whether 30–100 m temperature is physically plausible
      for tropical pelagic corridor reading.
    """
    t = clean_temperature_c(temp_c)
    out = np.zeros_like(t, dtype=float)

    cold0 = 12.0
    opt_lo = 20.0
    opt_hi = 29.5
    warm1 = 32.5

    m = (t >= cold0) & (t < opt_lo)
    out[m] = (t[m] - cold0) / max(1e-9, opt_lo - cold0)

    m = (t >= opt_lo) & (t <= opt_hi)
    out[m] = 1.0

    m = (t > opt_hi) & (t <= warm1)
    out[m] = 1.0 - (t[m] - opt_hi) / max(1e-9, warm1 - opt_hi)

    out[~np.isfinite(t)] = np.nan
    return np.clip(out, 0.0, 1.0)


def build_thermal_diagnostics(
    date: str,
    current_lat: np.ndarray,
    current_lon: np.ndarray,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """
    Optional v0.8.1 thermal layer.

    Reads prebuilt thermal diagnostics from:
    - data/physics/thermal_depth_diagnostics_today.json
    - data/physics/thermal_depth_maps_today.npz

    This avoids mixing h5py/HDF5 with xarray/netCDF4/matplotlib in the main builder.
    """
    diag_path = OUT_DIR / "thermal_depth_diagnostics_today.json"
    map_path = OUT_DIR / "thermal_depth_maps_today.npz"

    empty = {
        "thermal_score": np.full((len(current_lat), len(current_lon)), np.nan, dtype=float),
        "temperature_mean_30_100_c": np.full((len(current_lat), len(current_lon)), np.nan, dtype=float),
    }

    if not diag_path.exists() or not map_path.exists():
        return {
            "status": "missing",
            "version": "0.8.4-alpha.1",
            "source_file": str(diag_path),
            "map_file": str(map_path),
            "message": "Thermal diagnostics/map belum dibangun; jalankan scripts/build_thermal_depth_diagnostics.py lebih dulu.",
        }, empty

    try:
        diag = json.loads(diag_path.read_text(encoding="utf-8"))

        if diag.get("snapshot_date") != date:
            return {
                "status": "stale",
                "version": "0.8.4-alpha.1",
                "snapshot_date": diag.get("snapshot_date"),
                "expected_date": date,
                "source_file": diag.get("source_file"),
                "map_file": str(map_path),
                "message": "Thermal diagnostics tersedia tetapi tanggalnya tidak sama dengan current-depth snapshot.",
            }, empty

        maps_npz = np.load(map_path)
        thermal_lat = np.asarray(maps_npz["lat"], dtype=float)
        thermal_lon = np.asarray(maps_npz["lon"], dtype=float)
        thermal_score = np.asarray(maps_npz["thermal_score"], dtype=float)
        temp_mean = np.asarray(maps_npz["temperature_mean_30_100_c"], dtype=float)

        if len(thermal_lat) != len(current_lat) or len(thermal_lon) != len(current_lon):
            diag = dict(diag)
            diag.update({
                "status": "grid_mismatch",
                "thermal_grid_shape": {
                    "lat": int(len(thermal_lat)),
                    "lon": int(len(thermal_lon)),
                },
                "current_grid_shape": {
                    "lat": int(len(current_lat)),
                    "lon": int(len(current_lon)),
                },
                "message": "Grid thermal map tidak sama dengan current grid.",
            })
            return diag, empty

        diag = dict(diag)
        diag["status"] = "ready"

        return diag, {
            "thermal_score": thermal_score,
            "temperature_mean_30_100_c": temp_mean,
        }

    except Exception as exc:
        return {
            "status": "error",
            "version": "0.8.4-alpha.1",
            "source_file": str(diag_path),
            "map_file": str(map_path),
            "message": f"Gagal membaca thermal diagnostics/map: {type(exc).__name__}: {exc}",
        }, empty



def build_ssh_front_diagnostics(
    date: str,
    current_lat: np.ndarray,
    current_lon: np.ndarray,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """
    Optional v0.8.2 SSH/front layer.

    Reads prebuilt SSH/front diagnostics from:
    - data/physics/ssh_front_diagnostics_today.json
    - data/physics/ssh_front_maps_today.npz
    """
    diag_path = OUT_DIR / "ssh_front_diagnostics_today.json"
    map_path = OUT_DIR / "ssh_front_maps_today.npz"

    empty = {
        "ssh_front_score": np.full((len(current_lat), len(current_lon)), np.nan, dtype=float),
        "ssh_gradient_m_per_m": np.full((len(current_lat), len(current_lon)), np.nan, dtype=float),
        "ssh_m": np.full((len(current_lat), len(current_lon)), np.nan, dtype=float),
    }

    if not diag_path.exists() or not map_path.exists():
        return {
            "status": "missing",
            "version": "0.8.4-alpha.1",
            "source_file": str(diag_path),
            "map_file": str(map_path),
            "message": "SSH/front diagnostics/map belum dibangun.",
        }, empty

    try:
        diag = json.loads(diag_path.read_text(encoding="utf-8"))

        if diag.get("snapshot_date") != date:
            return {
                "status": "stale",
                "version": "0.8.4-alpha.1",
                "snapshot_date": diag.get("snapshot_date"),
                "expected_date": date,
                "source_file": diag.get("source_file"),
                "map_file": str(map_path),
                "message": "SSH/front diagnostics tersedia tetapi tanggalnya tidak sama dengan current-depth snapshot.",
            }, empty

        maps_npz = np.load(map_path)
        ssh_lat = np.asarray(maps_npz["lat"], dtype=float)
        ssh_lon = np.asarray(maps_npz["lon"], dtype=float)
        ssh_front_score = np.asarray(maps_npz["ssh_front_score"], dtype=float)
        ssh_gradient = np.asarray(maps_npz["ssh_gradient_m_per_m"], dtype=float)
        ssh_m = np.asarray(maps_npz["ssh_m"], dtype=float)

        if len(ssh_lat) != len(current_lat) or len(ssh_lon) != len(current_lon):
            diag = dict(diag)
            diag.update({
                "status": "grid_mismatch",
                "ssh_grid_shape": {
                    "lat": int(len(ssh_lat)),
                    "lon": int(len(ssh_lon)),
                },
                "current_grid_shape": {
                    "lat": int(len(current_lat)),
                    "lon": int(len(current_lon)),
                },
                "message": "Grid SSH/front tidak sama dengan current grid.",
            })
            return diag, empty

        diag = dict(diag)
        diag["status"] = "ready"

        return diag, {
            "ssh_front_score": ssh_front_score,
            "ssh_gradient_m_per_m": ssh_gradient,
            "ssh_m": ssh_m,
        }

    except Exception as exc:
        return {
            "status": "error",
            "version": "0.8.4-alpha.1",
            "source_file": str(diag_path),
            "map_file": str(map_path),
            "message": f"Gagal membaca SSH/front diagnostics/map: {type(exc).__name__}: {exc}",
        }, empty


def habitat_score_v082(
    rank_score: float | None,
    thermal_score: float | None,
    directional_coherence: float | None,
    ssh_front_score: float | None,
) -> float | None:
    """
    v0.8.2 habitat score:
    current-depth + thermal gate + vertical coherence + SSH/front support.
    """
    rs = safe_float(rank_score)
    ts = safe_float(thermal_score)
    coh = safe_float(directional_coherence)
    fs = safe_float(ssh_front_score)

    if rs is None:
        return None

    if ts is None:
        ts = 0.50
    if coh is None:
        coh = 0.50
    if fs is None:
        fs = 0.50

    return round(clip01(0.55 * rs + 0.25 * ts + 0.10 * coh + 0.10 * fs), 6)


def enrich_clustered_candidates_with_ssh_front(
    lat: np.ndarray,
    lon: np.ndarray,
    score: np.ndarray,
    vertical_maps: dict[str, np.ndarray] | None,
    thermal_maps: dict[str, np.ndarray] | None,
    ssh_maps: dict[str, np.ndarray] | None,
    clustered_candidates: list[dict[str, Any]],
    threshold: float,
    default_radius_km: float = 35.0,
) -> list[dict[str, Any]]:
    """
    Add SSH/front summaries and v0.8.2 habitat score to each cluster.
    """
    if not clustered_candidates:
        return clustered_candidates

    vertical_maps = vertical_maps or {}
    thermal_maps = thermal_maps or {}
    ssh_maps = ssh_maps or {}

    coh_map = vertical_maps.get("directional_coherence")
    thermal_score_map = thermal_maps.get("thermal_score")
    ssh_front_map = ssh_maps.get("ssh_front_score")
    ssh_grad_map = ssh_maps.get("ssh_gradient_m_per_m")

    if ssh_front_map is None:
        for c in clustered_candidates:
            c["ssh_front_status"] = "missing"
            c["habitat_score_v082_mean"] = habitat_score_v082(
                c.get("mean_score"),
                c.get("mean_thermal_score"),
                c.get("mean_directional_coherence") or c.get("top_directional_coherence"),
                None,
            )
        return clustered_candidates

    lon2d, lat2d = np.meshgrid(lon, lat)
    enriched = []

    for c in clustered_candidates:
        clat = safe_float(c.get("centroid_lat"))
        clon = safe_float(c.get("centroid_lon"))

        if clat is None or clon is None:
            enriched.append(c)
            continue

        radius = safe_float(c.get("radius_km_est"), default_radius_km) or default_radius_km
        radius = max(default_radius_km, radius)

        km_y = (lat2d - clat) * 111.0
        km_x = (lon2d - clon) * 111.0 * math.cos(math.radians(clat))
        dist = np.sqrt(km_x ** 2 + km_y ** 2)
        mask = (dist <= radius) & np.isfinite(score) & (score >= threshold)

        front_vals = np.asarray(ssh_front_map, dtype=float)[mask]
        front_vals = front_vals[np.isfinite(front_vals)]
        mean_front = safe_float(np.nanmean(front_vals)) if front_vals.size else None

        if ssh_grad_map is not None:
            grad_vals = np.asarray(ssh_grad_map, dtype=float)[mask]
            grad_vals = grad_vals[np.isfinite(grad_vals)]
            mean_grad = safe_float(np.nanmean(grad_vals)) if grad_vals.size else None
        else:
            mean_grad = None

        habitat_vals = []
        if np.any(mask):
            rows, cols = np.where(mask)
            for ii, jj in zip(rows, cols):
                rs = safe_float(score[ii, jj])
                ts = safe_float(thermal_score_map[ii, jj]) if thermal_score_map is not None else None
                coh = safe_float(coh_map[ii, jj]) if coh_map is not None else None
                fs = safe_float(ssh_front_map[ii, jj])
                hs = habitat_score_v082(rs, ts, coh, fs)
                if hs is not None:
                    habitat_vals.append(hs)

        mean_habitat_v082 = safe_float(np.nanmean(habitat_vals)) if habitat_vals else habitat_score_v082(
            c.get("mean_score"),
            c.get("mean_thermal_score"),
            c.get("mean_directional_coherence") or c.get("top_directional_coherence"),
            mean_front,
        )

        top_lat = safe_float(c.get("top_lat"))
        top_lon = safe_float(c.get("top_lon"))
        top_front = None
        top_grad = None
        top_habitat_v082 = None

        if top_lat is not None and top_lon is not None:
            ii = int(np.nanargmin(np.abs(lat - top_lat)))
            jj = int(np.nanargmin(np.abs(lon - top_lon)))
            top_front = safe_float(ssh_front_map[ii, jj])
            top_grad = safe_float(ssh_grad_map[ii, jj]) if ssh_grad_map is not None else None
            top_habitat_v082 = habitat_score_v082(
                c.get("max_score"),
                c.get("top_thermal_score"),
                c.get("top_directional_coherence"),
                top_front,
            )

        c = dict(c)
        c.update({
            "ssh_front_status": "ready" if mean_front is not None else "missing",
            "mean_ssh_front_score": mean_front,
            "mean_ssh_gradient_m_per_m": mean_grad,
            "habitat_score_v082_mean": mean_habitat_v082,
            "top_ssh_front_score": top_front,
            "top_ssh_gradient_m_per_m": top_grad,
            "top_habitat_score_v082": top_habitat_v082,
            "interpretation": (
                "Klaster kandidat koridor 30–100 m yang dibaca bersama arus, thermal gate, "
                "dan SSH/front support. Tetap gunakan bersama SST, CHL, bathymetry, cuaca, "
                "keselamatan, regulasi, dan pengalaman nelayan."
            ),
        })
        enriched.append(c)

    return enriched



def build_safety_gate_diagnostics(
    date: str,
    current_lat: np.ndarray,
    current_lon: np.ndarray,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """
    Optional v0.8.3 Safety Gate layer.

    Reads prebuilt safety diagnostics from:
    - data/physics/safety_gate_diagnostics_today.json
    - data/physics/safety_gate_maps_today.npz
    """
    diag_path = OUT_DIR / "safety_gate_diagnostics_today.json"
    map_path = OUT_DIR / "safety_gate_maps_today.npz"

    empty = {
        "safety_score": np.full((len(current_lat), len(current_lon)), np.nan, dtype=float),
        "combined_risk_score": np.full((len(current_lat), len(current_lon)), np.nan, dtype=float),
        "wave_m": np.full((len(current_lat), len(current_lon)), np.nan, dtype=float),
        "wind_speed_ms": np.full((len(current_lat), len(current_lon)), np.nan, dtype=float),
    }

    if not diag_path.exists() or not map_path.exists():
        return {
            "status": "missing",
            "version": "0.8.4-alpha.1",
            "source_file": str(diag_path),
            "map_file": str(map_path),
            "message": "Safety Gate diagnostics/map belum dibangun.",
        }, empty

    try:
        diag = json.loads(diag_path.read_text(encoding="utf-8"))

        if diag.get("snapshot_date") != date:
            return {
                "status": "stale",
                "version": "0.8.4-alpha.1",
                "snapshot_date": diag.get("snapshot_date"),
                "expected_date": date,
                "source_file": str(diag_path),
                "map_file": str(map_path),
                "message": "Safety Gate tersedia tetapi tanggal snapshot berbeda.",
            }, empty

        maps_npz = np.load(map_path)
        s_lat = np.asarray(maps_npz["lat"], dtype=float)
        s_lon = np.asarray(maps_npz["lon"], dtype=float)

        safety_score = np.asarray(maps_npz["safety_score"], dtype=float)
        combined_risk = np.asarray(maps_npz["combined_risk_score"], dtype=float)
        wave_m = np.asarray(maps_npz["wave_m"], dtype=float)
        wind_speed_ms = np.asarray(maps_npz["wind_speed_ms"], dtype=float)

        if len(s_lat) != len(current_lat) or len(s_lon) != len(current_lon):
            diag = dict(diag)
            diag.update({
                "status": "grid_mismatch",
                "safety_grid_shape": {
                    "lat": int(len(s_lat)),
                    "lon": int(len(s_lon)),
                },
                "current_grid_shape": {
                    "lat": int(len(current_lat)),
                    "lon": int(len(current_lon)),
                },
                "message": "Grid Safety Gate tidak sama dengan current grid.",
            })
            return diag, empty

        diag = dict(diag)
        diag["status"] = "ready"

        return diag, {
            "safety_score": safety_score,
            "combined_risk_score": combined_risk,
            "wave_m": wave_m,
            "wind_speed_ms": wind_speed_ms,
        }

    except Exception as exc:
        return {
            "status": "error",
            "version": "0.8.4-alpha.1",
            "source_file": str(diag_path),
            "map_file": str(map_path),
            "message": f"Gagal membaca Safety Gate diagnostics/map: {type(exc).__name__}: {exc}",
        }, empty


def operational_habitat_score_v083(
    habitat_score_v082_value: float | None,
    safety_score_value: float | None,
) -> float | None:
    """
    v0.8.3 operational habitat score.

    This is not a fish guarantee and not a sailing guarantee.
    It tempers habitat opportunity with small-fisher safety gate.
    """
    h = safe_float(habitat_score_v082_value)
    s = safe_float(safety_score_value)

    if h is None:
        return None

    if s is None:
        # Missing safety should reduce confidence gently, not erase habitat signal.
        s = 0.50

    return round(clip01(h * s), 6)


def enrich_clustered_candidates_with_safety_gate(
    lat: np.ndarray,
    lon: np.ndarray,
    score: np.ndarray,
    vertical_maps: dict[str, np.ndarray] | None,
    thermal_maps: dict[str, np.ndarray] | None,
    ssh_maps: dict[str, np.ndarray] | None,
    safety_maps: dict[str, np.ndarray] | None,
    clustered_candidates: list[dict[str, Any]],
    threshold: float,
    default_radius_km: float = 35.0,
) -> list[dict[str, Any]]:
    """
    Add Safety Gate summaries and operational score to each cluster.
    """
    if not clustered_candidates:
        return clustered_candidates

    vertical_maps = vertical_maps or {}
    thermal_maps = thermal_maps or {}
    ssh_maps = ssh_maps or {}
    safety_maps = safety_maps or {}

    safety_map = safety_maps.get("safety_score")
    risk_map = safety_maps.get("combined_risk_score")
    wave_map = safety_maps.get("wave_m")
    wind_map = safety_maps.get("wind_speed_ms")

    if safety_map is None:
        for c in clustered_candidates:
            c["safety_gate_status"] = "missing"
            c["operational_habitat_score_v083_mean"] = operational_habitat_score_v083(
                c.get("habitat_score_v082_mean"),
                None,
            )
        return clustered_candidates

    lon2d, lat2d = np.meshgrid(lon, lat)
    enriched = []

    for c in clustered_candidates:
        clat = safe_float(c.get("centroid_lat"))
        clon = safe_float(c.get("centroid_lon"))

        if clat is None or clon is None:
            enriched.append(c)
            continue

        radius = safe_float(c.get("radius_km_est"), default_radius_km) or default_radius_km
        radius = max(default_radius_km, radius)

        km_y = (lat2d - clat) * 111.0
        km_x = (lon2d - clon) * 111.0 * math.cos(math.radians(clat))
        dist = np.sqrt(km_x ** 2 + km_y ** 2)
        mask = (dist <= radius) & np.isfinite(score) & (score >= threshold)

        def masked_mean(m):
            if m is None:
                return None
            vals = np.asarray(m, dtype=float)[mask]
            vals = vals[np.isfinite(vals)]
            return safe_float(np.nanmean(vals)) if vals.size else None

        mean_safety = masked_mean(safety_map)
        mean_risk = masked_mean(risk_map)
        mean_wave = masked_mean(wave_map)
        mean_wind = masked_mean(wind_map)

        operational_vals = []
        if np.any(mask):
            rows, cols = np.where(mask)
            for ii, jj in zip(rows, cols):
                hs082 = habitat_score_v082(
                    safe_float(score[ii, jj]),
                    safe_float(thermal_maps.get("thermal_score")[ii, jj]) if thermal_maps.get("thermal_score") is not None else None,
                    safe_float(vertical_maps.get("directional_coherence")[ii, jj]) if vertical_maps.get("directional_coherence") is not None else None,
                    safe_float(ssh_maps.get("ssh_front_score")[ii, jj]) if ssh_maps.get("ssh_front_score") is not None else None,
                )
                op = operational_habitat_score_v083(
                    hs082,
                    safe_float(safety_map[ii, jj]),
                )
                if op is not None:
                    operational_vals.append(op)

        mean_operational = safe_float(np.nanmean(operational_vals)) if operational_vals else operational_habitat_score_v083(
            c.get("habitat_score_v082_mean"),
            mean_safety,
        )

        top_lat = safe_float(c.get("top_lat"))
        top_lon = safe_float(c.get("top_lon"))

        top_safety = None
        top_risk = None
        top_wave = None
        top_wind = None
        top_operational = None

        if top_lat is not None and top_lon is not None:
            ii = int(np.nanargmin(np.abs(lat - top_lat)))
            jj = int(np.nanargmin(np.abs(lon - top_lon)))

            top_safety = safe_float(safety_map[ii, jj])
            top_risk = safe_float(risk_map[ii, jj]) if risk_map is not None else None
            top_wave = safe_float(wave_map[ii, jj]) if wave_map is not None else None
            top_wind = safe_float(wind_map[ii, jj]) if wind_map is not None else None

            top_operational = operational_habitat_score_v083(
                c.get("top_habitat_score_v082"),
                top_safety,
            )

        c = dict(c)
        c.update({
            "safety_gate_status": "ready" if mean_safety is not None else "missing",
            "mean_safety_score": mean_safety,
            "mean_combined_risk_score": mean_risk,
            "mean_wave_m": mean_wave,
            "mean_wind_speed_ms": mean_wind,
            "operational_habitat_score_v083_mean": mean_operational,
            "top_safety_score": top_safety,
            "top_combined_risk_score": top_risk,
            "top_wave_m": top_wave,
            "top_wind_speed_ms": top_wind,
            "top_operational_habitat_score_v083": top_operational,
            "interpretation": (
                "Klaster kandidat koridor 30–100 m yang dibaca bersama arus, thermal gate, "
                "SSH/front support, dan Safety Gate. Peluang oseanografi tidak boleh dibaca "
                "terpisah dari gelombang, angin, keselamatan, regulasi, dan pengalaman nelayan."
            ),
        })
        enriched.append(c)

    return enriched



def operational_decision_v084(
    operational_score: float | None,
    habitat_score_v082_value: float | None,
    safety_score_value: float | None,
    wave_m: float | None,
    wind_ms: float | None,
) -> dict[str, Any]:
    """
    v0.8.4 operational decision label.

    This is not a command to sail and not a fish-location guarantee.
    It translates probabilistic habitat + safety into a cautious reading label.
    """
    op = safe_float(operational_score)
    hab = safe_float(habitat_score_v082_value)
    saf = safe_float(safety_score_value)
    wave = safe_float(wave_m)
    wind = safe_float(wind_ms)

    # Hard caution gates for small-fisher context.
    if (wave is not None and wave >= 2.5) or (wind is not None and wind >= 12.0) or (saf is not None and saf < 0.35):
        return {
            "label": "Tunda / risiko tinggi",
            "level": "high_risk",
            "color": "red",
            "note": "Sinyal oseanografi tidak boleh mengalahkan keselamatan. Gelombang/angin atau safety score menunjukkan risiko tinggi.",
        }

    if op is None:
        return {
            "label": "Belum cukup data",
            "level": "unknown",
            "color": "slate",
            "note": "Data operasional belum cukup untuk membuat label kehati-hatian.",
        }

    if op >= 0.60 and (saf is None or saf >= 0.65):
        return {
            "label": "Prioritas observasi hati-hati",
            "level": "priority_observation",
            "color": "emerald",
            "note": "Sinyal habitat dan safety relatif mendukung, tetapi tetap perlu validasi lapangan, cuaca terkini, dan keputusan nelayan.",
        }

    if hab is not None and hab >= 0.70 and saf is not None and saf < 0.55:
        return {
            "label": "Oseanografi menarik, safety perlu waspada",
            "level": "habitat_good_safety_watch",
            "color": "amber",
            "note": "Sinyal habitat cukup menarik, tetapi Safety Gate menahan interpretasi karena risiko operasional meningkat.",
        }

    if op >= 0.40:
        return {
            "label": "Observasi selektif",
            "level": "selective_observation",
            "color": "yellow",
            "note": "Koridor masih layak diamati secara selektif, bukan dibaca sebagai tujuan melaut langsung.",
        }

    return {
        "label": "Prioritas rendah / tunggu sinyal membaik",
        "level": "low_priority",
        "color": "slate",
        "note": "Gabungan habitat dan safety belum cukup kuat untuk menjadi prioritas observasi.",
    }


def add_operational_decision_to_clusters(clustered_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in clustered_candidates or []:
        c = dict(c)
        decision = operational_decision_v084(
            c.get("operational_habitat_score_v083_mean"),
            c.get("habitat_score_v082_mean"),
            c.get("mean_safety_score"),
            c.get("mean_wave_m"),
            c.get("mean_wind_speed_ms"),
        )
        top_decision = operational_decision_v084(
            c.get("top_operational_habitat_score_v083"),
            c.get("top_habitat_score_v082"),
            c.get("top_safety_score"),
            c.get("top_wave_m"),
            c.get("top_wind_speed_ms"),
        )
        c["operational_decision_v084"] = decision
        c["top_operational_decision_v084"] = top_decision
        out.append(c)
    return out


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
        f"NELAYA-AI — Tuna Depth Current Layer v0.8.4-alpha.1\nPerairan Aceh · Copernicus CMEMS · {date}",
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
    print("NELAYA-AI Tuna Depth Current Analysis v0.8.4")
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

    vertical_diagnostics, vertical_maps = build_vertical_diagnostics(layers)
    thermal_diagnostics, thermal_maps = build_thermal_diagnostics(
        date=date,
        current_lat=lat,
        current_lon=lon,
    )
    ssh_front_diagnostics, ssh_maps = build_ssh_front_diagnostics(
        date=date,
        current_lat=lat,
        current_lon=lon,
    )
    safety_gate_diagnostics, safety_maps = build_safety_gate_diagnostics(
        date=date,
        current_lat=lat,
        current_lon=lon,
    )
    audit = build_audit(
        ds=ds,
        source_file=f,
        date=date,
        layers=layers,
        lat=lat,
        lon=lon,
        composite=composite,
        candidate_rank_score=candidate_rank_score,
        thermal_diagnostics=thermal_diagnostics,
    )
    confidence_breakdown = build_confidence_breakdown(
        audit=audit,
        vertical_diagnostics=vertical_diagnostics,
        composite=composite,
        candidate_rank_score=candidate_rank_score,
        thermal_diagnostics=thermal_diagnostics,
    )
    clustered_candidates = build_clustered_candidates(
        lat=lat,
        lon=lon,
        score=candidate_rank_score,
        speed=composite_speed,
        threshold=args.geojson_threshold,
        max_clusters=7,
        radius_km=35.0,
        max_points_scan=args.max_points,
        vertical_maps=vertical_maps,
    )
    clustered_candidates = enrich_clustered_candidates_with_thermal(
        lat=lat,
        lon=lon,
        score=candidate_rank_score,
        vertical_maps=vertical_maps,
        thermal_maps=thermal_maps,
        clustered_candidates=clustered_candidates,
        threshold=args.geojson_threshold,
        default_radius_km=35.0,
    )
    clustered_candidates = enrich_clustered_candidates_with_ssh_front(
        lat=lat,
        lon=lon,
        score=candidate_rank_score,
        vertical_maps=vertical_maps,
        thermal_maps=thermal_maps,
        ssh_maps=ssh_maps,
        clustered_candidates=clustered_candidates,
        threshold=args.geojson_threshold,
        default_radius_km=35.0,
    )
    clustered_candidates = enrich_clustered_candidates_with_safety_gate(
        lat=lat,
        lon=lon,
        score=candidate_rank_score,
        vertical_maps=vertical_maps,
        thermal_maps=thermal_maps,
        ssh_maps=ssh_maps,
        safety_maps=safety_maps,
        clustered_candidates=clustered_candidates,
        threshold=args.geojson_threshold,
        default_radius_km=35.0,
    )
    clustered_candidates = add_operational_decision_to_clusters(clustered_candidates)

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
                   vertical_maps=vertical_maps,
                   clustered_candidates=clustered_candidates,
                   thermal_maps=thermal_maps,
                   ssh_maps=ssh_maps,
                   safety_maps=safety_maps,
          )

    summary = {
        "module": "nelaya_ai_tuna_depth_current_analysis",
        "version": "0.8.4-alpha.1",
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
        "audit": audit,
        "vertical_diagnostics": vertical_diagnostics,
        "thermal_diagnostics": thermal_diagnostics,
        "ssh_front_diagnostics": ssh_front_diagnostics,
        "safety_gate_diagnostics": safety_gate_diagnostics,
        "operational_decision_summary": {
            "version": "0.8.4-alpha.1",
            "main_message": "Tuna Depth kini membaca peluang oseanografi bersama Safety Gate. Label operasional adalah pembacaan kehati-hatian, bukan perintah melaut.",
            "top_cluster_decision": clustered_candidates[0].get("operational_decision_v084") if clustered_candidates else None,
        },
        "confidence_breakdown": confidence_breakdown,
        "clustered_candidates": clustered_candidates,
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
