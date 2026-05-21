#!/usr/bin/env python3
"""
Particle Drift Beta v0.1 for NELAYA-AI.

Purpose:
- Simulate simple surface-water particle drift using daily current field.
- Produce drift tracks, retention/density hotspots, GeoJSON, and PNG map.

Scientific status:
- Beta / diagnostic.
- Uses a frozen daily surface-current field.
- Not yet full time-varying Lagrangian tracking or FTLE/LCS.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from build_lagrangian_front_alpha import (
    latest_current_file,
    open_dataset_safely,
    pick_uv_vars,
    pick_lat_lon,
    reduce_to_2d,
)

EARTH_RADIUS_M = 6_371_000.0


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_current(path: Path):
    ds = open_dataset_safely(path)
    u_var, v_var = pick_uv_vars(ds)
    lat_name, lon_name = pick_lat_lon(ds, ds[u_var])

    u_da = reduce_to_2d(ds[u_var], lat_name, lon_name)
    v_da = reduce_to_2d(ds[v_var], lat_name, lon_name)

    lat = np.asarray(ds[lat_name].values, dtype=float)
    lon = np.asarray(ds[lon_name].values, dtype=float)

    if lat.ndim == 2:
        lat = lat[:, 0]
    if lon.ndim == 2:
        lon = lon[0, :]

    u = np.asarray(u_da.values, dtype=float)
    v = np.asarray(v_da.values, dtype=float)

    try:
        ds.close()
    except Exception:
        pass

    return lat, lon, u, v, u_var, v_var


def bilinear_interp(lat: np.ndarray, lon: np.ndarray, field: np.ndarray, la: float, lo: float) -> Optional[float]:
    if la < lat.min() or la > lat.max() or lo < lon.min() or lo > lon.max():
        return None

    i = np.searchsorted(lat, la) - 1
    j = np.searchsorted(lon, lo) - 1

    if i < 0 or j < 0 or i >= len(lat) - 1 or j >= len(lon) - 1:
        return None

    lat0, lat1 = lat[i], lat[i + 1]
    lon0, lon1 = lon[j], lon[j + 1]

    q11 = field[i, j]
    q21 = field[i + 1, j]
    q12 = field[i, j + 1]
    q22 = field[i + 1, j + 1]

    if not np.all(np.isfinite([q11, q21, q12, q22])):
        return None

    if abs(lat1 - lat0) < 1e-12 or abs(lon1 - lon0) < 1e-12:
        return None

    fy = (la - lat0) / (lat1 - lat0)
    fx = (lo - lon0) / (lon1 - lon0)

    return float(
        q11 * (1 - fx) * (1 - fy)
        + q12 * fx * (1 - fy)
        + q21 * (1 - fx) * fy
        + q22 * fx * fy
    )


def step_particle(lat_grid, lon_grid, u, v, la: float, lo: float, dt_seconds: float) -> Optional[Tuple[float, float, float, float]]:
    uu = bilinear_interp(lat_grid, lon_grid, u, la, lo)
    vv = bilinear_interp(lat_grid, lon_grid, v, la, lo)

    if uu is None or vv is None:
        return None

    speed = math.sqrt(uu * uu + vv * vv)
    if not math.isfinite(speed) or speed > 5.0:
        return None

    dlat = (vv * dt_seconds / EARTH_RADIUS_M) * (180.0 / math.pi)
    coslat = max(0.05, math.cos(math.radians(la)))
    dlon = (uu * dt_seconds / (EARTH_RADIUS_M * coslat)) * (180.0 / math.pi)

    return la + dlat, lo + dlon, uu, vv


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def direction_label(bearing: float) -> str:
    dirs = [
        "utara", "timur laut", "timur", "tenggara",
        "selatan", "barat daya", "barat", "barat laut"
    ]
    idx = int((bearing + 22.5) // 45) % 8
    return dirs[idx]


def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = (
        math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
        - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
    )
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def simulate(lat, lon, u, v, seed_stride: int, hours: int, dt_hours: float):
    valid = np.isfinite(u) & np.isfinite(v) & (np.abs(u) < 5) & (np.abs(v) < 5)

    seed_indices = []
    for i in range(1, len(lat) - 1, seed_stride):
        for j in range(1, len(lon) - 1, seed_stride):
            if valid[i, j]:
                seed_indices.append((i, j))

    tracks = []
    dt_seconds = dt_hours * 3600.0
    steps = int(hours / dt_hours)

    for pid, (i, j) in enumerate(seed_indices, start=1):
        start_lat = float(lat[i])
        start_lon = float(lon[j])
        la, lo = start_lat, start_lon
        coords = [[round(lo, 5), round(la, 5)]]
        speeds = []
        active = True

        for _ in range(steps):
            nxt = step_particle(lat, lon, u, v, la, lo, dt_seconds)
            if nxt is None:
                active = False
                break
            la, lo, uu, vv = nxt
            if la < lat.min() or la > lat.max() or lo < lon.min() or lo > lon.max():
                active = False
                break
            coords.append([round(lo, 5), round(la, 5)])
            speeds.append(math.sqrt(uu * uu + vv * vv))

        end_lat, end_lon = la, lo
        dist_km = haversine_km(start_lat, start_lon, end_lat, end_lon)
        brg = bearing_deg(start_lat, start_lon, end_lat, end_lon)

        tracks.append({
            "id": pid,
            "start_lat": round(start_lat, 5),
            "start_lon": round(start_lon, 5),
            "end_lat": round(end_lat, 5),
            "end_lon": round(end_lon, 5),
            "distance_km": round(dist_km, 3),
            "bearing_deg": round(brg, 1),
            "direction_label": direction_label(brg),
            "mean_speed_ms": round(float(np.mean(speeds)), 4) if speeds else None,
            "active_full_duration": active,
            "point_count": len(coords),
            "coordinates": coords,
        })

    return tracks


def density_hotspots(tracks: List[Dict[str, Any]], lat, lon, top_k=15):
    ends = [(t["end_lat"], t["end_lon"]) for t in tracks if t.get("active_full_duration")]
    if not ends:
        return []

    end_lat = np.array([x[0] for x in ends], dtype=float)
    end_lon = np.array([x[1] for x in ends], dtype=float)

    lat_edges = np.linspace(float(lat.min()), float(lat.max()), 31)
    lon_edges = np.linspace(float(lon.min()), float(lon.max()), 36)

    H, yedges, xedges = np.histogram2d(end_lat, end_lon, bins=[lat_edges, lon_edges])
    max_count = float(np.max(H)) if H.size else 0.0
    if max_count <= 0:
        return []

    candidates = []
    for i in range(H.shape[0]):
        for j in range(H.shape[1]):
            c = H[i, j]
            if c <= 0:
                continue
            candidates.append({
                "lat": round(float((yedges[i] + yedges[i + 1]) / 2), 5),
                "lon": round(float((xedges[j] + xedges[j + 1]) / 2), 5),
                "particle_count": int(c),
                "retention_score": round(float(c / max_count), 4),
            })

    candidates.sort(key=lambda z: z["particle_count"], reverse=True)
    return candidates[:top_k]


def make_geojson(tracks, hotspots):
    features = []

    # keep GeoJSON moderate: top 250 tracks by distance
    sorted_tracks = sorted(tracks, key=lambda t: t["distance_km"], reverse=True)[:250]
    for t in sorted_tracks:
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": t["coordinates"]},
            "properties": {
                "kind": "particle_track",
                "id": t["id"],
                "distance_km": t["distance_km"],
                "bearing_deg": t["bearing_deg"],
                "direction_label": t["direction_label"],
                "mean_speed_ms": t["mean_speed_ms"],
                "active_full_duration": t["active_full_duration"],
            },
        })

    for rank, h in enumerate(hotspots, start=1):
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [h["lon"], h["lat"]]},
            "properties": {
                "kind": "retention_hotspot",
                "rank": rank,
                **h,
            },
        })

    return {
        "type": "FeatureCollection",
        "name": "particle_drift_beta_today",
        "features": features,
    }


def plot_png(lat, lon, u, v, tracks, hotspots, out_png: Path, title_date: str, hours: int):
    fig, ax = plt.subplots(figsize=(11, 7))

    speed = np.sqrt(u * u + v * v)
    lon2d, lat2d = np.meshgrid(lon, lat)

    im = ax.pcolormesh(lon2d, lat2d, speed, shading="auto")
    cbar = fig.colorbar(im, ax=ax, pad=0.015)
    cbar.set_label("Current speed (m/s)")

    # Plot subset tracks for readability
    for t in tracks[::max(1, len(tracks) // 250)]:
        coords = t["coordinates"]
        if len(coords) < 2:
            continue
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        ax.plot(xs, ys, linewidth=0.6, alpha=0.55)

    if hotspots:
        xs = [h["lon"] for h in hotspots[:10]]
        ys = [h["lat"] for h in hotspots[:10]]
        ax.scatter(xs, ys, s=65, marker="o", edgecolor="black", linewidth=0.8)
        for rank, h in enumerate(hotspots[:8], start=1):
            ax.annotate(f"R{rank}", (h["lon"], h["lat"]), textcoords="offset points", xytext=(5, 5), fontsize=8, weight="bold")

    ax.set_title(f"NELAYA-AI Particle Drift Beta — {hours}h Surface Drift\n{title_date} | Frozen daily current field")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_xlim(float(lon.min()), float(lon.max()))
    ax.set_ylim(float(lat.min()), float(lat.max()))
    ax.grid(True, alpha=0.25)

    fig.text(
        0.5,
        0.015,
        "Lines = virtual water-particle tracks; background = current speed; R points = retention-density hotspots. Beta diagnostic, not FTLE/LCS.",
        ha="center",
        fontsize=9,
    )

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--root", default="data/raw/aceh_simeulue/cur_nrt")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--dt-hours", type=float, default=1.0)
    parser.add_argument("--seed-stride", type=int, default=4)
    parser.add_argument("--out-json", default="data/physics/particle_drift_today.json")
    parser.add_argument("--out-geojson", default="data/physics/particle_drift_today.geojson")
    parser.add_argument("--out-png", default="data/physics/particle_drift_today.png")
    args = parser.parse_args()

    input_path = latest_current_file(Path(args.root), args.date)
    lat, lon, u, v, u_var, v_var = load_current(input_path)

    tracks = simulate(lat, lon, u, v, args.seed_stride, args.hours, args.dt_hours)
    hotspots = density_hotspots(tracks, lat, lon)

    active_tracks = [t for t in tracks if t["active_full_duration"]]
    dists = [t["distance_km"] for t in active_tracks]

    date_from_name = None
    stem = input_path.stem
    if stem.startswith("current_nrt_aceh_"):
        date_from_name = stem.replace("current_nrt_aceh_", "")

    result = {
        "version": "0.1-beta",
        "product": "Particle Drift Beta",
        "date": date_from_name,
        "created_at_utc": now_utc(),
        "method": "frozen_daily_surface_current_particle_tracking",
        "method_note": (
            "Virtual particles are advected using a frozen daily surface-current field. "
            "This is a drift diagnostic and not yet time-varying FTLE/LCS."
        ),
        "input": {
            "source_path": str(input_path),
            "u_variable": u_var,
            "v_variable": v_var,
            "grid_shape": {"lat": int(len(lat)), "lon": int(len(lon))},
            "bbox": {
                "lat_min": round(float(lat.min()), 5),
                "lat_max": round(float(lat.max()), 5),
                "lon_min": round(float(lon.min()), 5),
                "lon_max": round(float(lon.max()), 5),
            },
        },
        "settings": {
            "hours": args.hours,
            "dt_hours": args.dt_hours,
            "seed_stride": args.seed_stride,
            "particle_count": len(tracks),
            "active_full_duration_count": len(active_tracks),
        },
        "summary": {
            "mean_distance_km": round(float(np.mean(dists)), 3) if dists else None,
            "max_distance_km": round(float(np.max(dists)), 3) if dists else None,
            "median_distance_km": round(float(np.median(dists)), 3) if dists else None,
            "active_fraction": round(len(active_tracks) / len(tracks), 4) if tracks else None,
            "retention_hotspot_count": len(hotspots),
            "main_message": (
                f"Particle Drift Beta mensimulasikan jejak partikel air permukaan selama {args.hours} jam. "
                "Hasil ini menunjukkan arah transport massa air dan indikasi zona retensi relatif, "
                "bukan prediksi pasti lokasi ikan."
            ),
        },
        "retention_hotspots": hotspots,
        "sample_tracks": sorted(active_tracks, key=lambda t: t["distance_km"], reverse=True)[:25],
        "scientific_caution": (
            "Particle Drift Beta memakai medan arus harian beku. Belum memakai arus time-varying, tidal correction, "
            "land-boundary collision yang rinci, atau FTLE/LCS penuh. Gunakan sebagai diagnostik awal transport massa air."
        ),
        "next_step": [
            "Use multi-day/time-varying currents for 48-72h drift.",
            "Add land-mask aware particle stopping/reflection.",
            "Compute FTLE-lite from flow-map deformation.",
            "Compare drift/retention zones with LFI Alpha, CHL/SST fronts, and fishing trip validation.",
        ],
    }

    Path(args.out_json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.out_geojson).write_text(json.dumps(make_geojson(tracks, hotspots), indent=2, ensure_ascii=False), encoding="utf-8")
    plot_png(lat, lon, u, v, tracks, hotspots, Path(args.out_png), date_from_name or "latest", args.hours)

    print(json.dumps({
        "ok": True,
        "date": result["date"],
        "input": str(input_path),
        "summary": result["summary"],
        "first_hotspot": hotspots[0] if hotspots else None,
        "outputs": {
            "json": args.out_json,
            "geojson": args.out_geojson,
            "png": args.out_png,
        },
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
