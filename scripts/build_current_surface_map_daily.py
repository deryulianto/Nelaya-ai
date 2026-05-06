#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
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


def safe_float(x, default=None):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def extract_date(path: Path):
    m = DATE_RE.search(path.name)
    return m.group(1) if m else None


def find_latest_current_file(root: Path, days_back: int = 10, date: str | None = None) -> Path:
    if date:
        y, m, _ = date.split("-")
        p = root / y / m / f"current_nrt_aceh_{date}.nc"
        if not p.exists():
            raise FileNotFoundError(f"File current tidak ditemukan: {p}")
        return p

    files = sorted(root.glob("20??/??/current_nrt_aceh_20??-??-??.nc"))
    if not files:
        raise FileNotFoundError(f"Tidak ada file current di {root}")

    today = datetime.now(ZoneInfo("Asia/Jakarta")).date()
    min_date = today - timedelta(days=days_back)

    candidates = []
    for f in files:
        d = extract_date(f)
        if not d:
            continue
        try:
            dd = datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
            continue
        if dd >= min_date:
            candidates.append(f)

    return candidates[-1] if candidates else files[-1]


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


def squeeze_to_2d(da: xr.DataArray, lat_name: str, lon_name: str) -> xr.DataArray:
    da = da.squeeze(drop=True)

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


def vector_mean_direction(u: np.ndarray, v: np.ndarray) -> tuple[float | None, str | None]:
    um = safe_float(np.nanmean(u))
    vm = safe_float(np.nanmean(v))
    if um is None or vm is None:
        return None, None
    deg = (math.degrees(math.atan2(um, vm)) + 360.0) % 360.0
    return deg, direction_label(deg)


def find_hotspot(lat: np.ndarray, lon: np.ndarray, speed: np.ndarray, u: np.ndarray, v: np.ndarray):
    if not np.any(np.isfinite(speed)):
        return None

    idx = int(np.nanargmax(speed))
    ny, nx = speed.shape
    i = idx // nx
    j = idx % nx

    d = safe_float(direction_deg(np.array([[u[i, j]]]), np.array([[v[i, j]]]))[0, 0])

    return {
        "lat": float(lat[i]),
        "lon": float(lon[j]),
        "speed_ms": safe_float(speed[i, j]),
        "direction_deg": d,
        "direction_label": direction_label(d),
    }


def make_map_png(
    out_png: Path,
    date: str,
    lat: np.ndarray,
    lon: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    speed: np.ndarray,
    hotspot: dict | None,
    mean_dir_label: str | None,
):
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "figure.facecolor": "#071528",
        "axes.facecolor": "#071528",
        "savefig.facecolor": "#071528",
        "text.color": "#e5edf7",
        "axes.labelcolor": "#e5edf7",
        "xtick.color": "#e5edf7",
        "ytick.color": "#e5edf7",
        "axes.edgecolor": "#2b8bb8",
        "font.size": 10,
    })

    fig, ax = plt.subplots(figsize=(15.5, 10.5), dpi=160)

    lon2d, lat2d = np.meshgrid(lon, lat)

    vmax = max(0.70, float(np.nanpercentile(speed, 99)) if np.any(np.isfinite(speed)) else 0.70)
    levels = np.linspace(0, vmax, 22)

    # Heatmap arus
    cf = ax.contourf(
        lon2d,
        lat2d,
        speed,
        levels=levels,
        cmap="turbo",
        extend="max",
        alpha=0.95,
    )

    # Area NaN dibuat gelap agar daratan/no-data terlihat sebagai siluet.
    nan_mask = ~np.isfinite(speed)
    if np.any(nan_mask):
        ax.contourf(
            lon2d,
            lat2d,
            nan_mask.astype(float),
            levels=[0.5, 1.5],
            colors=["#061225"],
            alpha=0.98,
        )

    # Panah arus
    step_y = max(1, len(lat) // 26)
    step_x = max(1, len(lon) // 32)

    q = ax.quiver(
        lon2d[::step_y, ::step_x],
        lat2d[::step_y, ::step_x],
        u[::step_y, ::step_x],
        v[::step_y, ::step_x],
        color="white",
        alpha=0.78,
        scale=7.0,
        width=0.0028,
        headwidth=3.7,
        headlength=4.8,
        headaxislength=4.2,
    )

    # Hotspot
    if hotspot:
        hx = hotspot["lon"]
        hy = hotspot["lat"]
        hs = hotspot["speed_ms"]
        hlabel = pretty(hotspot.get("direction_label"))

        ax.scatter([hx], [hy], s=60, color="white", edgecolor="#ef4444", linewidth=1.8, zorder=8)

        ax.annotate(
            f"Hotspot kecepatan max\n{hs:.2f} m/s\n({hy:.2f}°N, {hx:.2f}°E)",
            xy=(hx, hy),
            xytext=(hx + 0.85, hy + 0.95),
            fontsize=10,
            color="white",
            bbox=dict(boxstyle="round,pad=0.35", fc="#8b1d13", ec="white", lw=0.8, alpha=0.88),
            arrowprops=dict(arrowstyle="-", color="white", lw=1.3),
            zorder=10,
        )

    # Label wilayah
    ax.text(95.9, 4.0, "ACEH", fontsize=18, color="white", alpha=0.45, weight="bold")
    ax.text(95.55, 3.15, "SIMEULUE", fontsize=9, color="white", alpha=0.75, weight="bold")

    ax.text(
        97.15,
        5.25,
        "Selat Malaka\n(arus ← barat dominan)",
        fontsize=9,
        color="#fde047",
        bbox=dict(boxstyle="round,pad=0.35", fc="#071528", ec="#facc15", lw=0.9, alpha=0.85),
    )

    ax.text(
        93.25,
        2.75,
        "Samudra Hindia\nBarat Aceh\n(arus ↓ selatan)",
        fontsize=9,
        color="#a5f3fc",
        bbox=dict(boxstyle="round,pad=0.35", fc="#073042", ec="#38bdf8", lw=0.9, alpha=0.82),
    )

    # Axis
    ax.set_xlim(92, 99)
    ax.set_ylim(1, 7)
    ax.set_xlabel("Bujur (°E)", fontsize=12)
    ax.set_ylabel("Lintang (°N)", fontsize=12)
    ax.set_xticks(np.arange(92, 100, 1))
    ax.set_yticks(np.arange(1, 8, 1))
    ax.set_xticklabels([f"{x}°E" for x in range(92, 100)])
    ax.set_yticklabels([f"{y}°N" for y in range(1, 8)])
    ax.grid(color="white", alpha=0.18, linestyle="--", linewidth=0.6)

    title = "Peta Arus Laut Permukaan — Perairan Aceh"
    subtitle = f"NELAYA-AI · Copernicus CMEMS · {date} · Kedalaman ~0.5 m"
    ax.set_title(f"{title}\n{subtitle}", fontsize=16, weight="bold", pad=16)

    cbar = fig.colorbar(cf, ax=ax, shrink=0.86, pad=0.02)
    cbar.set_label("Kecepatan Arus (m/s)", fontsize=12)
    cbar.ax.tick_params(colors="#e5edf7")

    ax.text(
        0.995,
        -0.055,
        "nelaya-ai.com",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=10,
        color="#38bdf8",
        style="italic",
    )

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--date", default=None)
    parser.add_argument("--days-back", type=int, default=10)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    cur_dir = root / CUR_DIR
    out_dir = root / OUT_DIR
    history_dir = root / HISTORY_DIR

    current_file = find_latest_current_file(cur_dir, days_back=args.days_back, date=args.date)
    snapshot_date = extract_date(current_file) or args.date or datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d")

    print("=" * 78)
    print("NELAYA-AI Daily Current Surface Map Builder")
    print("=" * 78)
    print(f"Input file    : {current_file}")
    print(f"Snapshot date : {snapshot_date}")

    ds = open_dataset_any(current_file)

    lat_name = detect_coord(ds, ["lat", "latitude", "y"])
    lon_name = detect_coord(ds, ["lon", "longitude", "x"])
    u_name = detect_var(ds, ["uo", "u", "eastward_current", "eastward_sea_water_velocity"])
    v_name = detect_var(ds, ["vo", "v", "northward_current", "northward_sea_water_velocity"])

    if not lat_name or not lon_name:
        raise SystemExit(f"Lat/lon tidak terdeteksi. coords={list(ds.coords)} dims={list(ds.dims)}")
    if not u_name or not v_name:
        raise SystemExit(f"uo/vo tidak terdeteksi. vars={list(ds.data_vars)}")

    u_da = squeeze_to_2d(ds[u_name], lat_name, lon_name)
    v_da = squeeze_to_2d(ds[v_name], lat_name, lon_name)

    lat = np.asarray(u_da["lat"].values, dtype=float)
    lon = np.asarray(u_da["lon"].values, dtype=float)
    u = np.asarray(u_da.values, dtype=float)
    v = np.asarray(v_da.values, dtype=float)
    speed = np.sqrt(u ** 2 + v ** 2)

    mean_dir_deg, mean_dir_label = vector_mean_direction(u, v)
    hotspot = find_hotspot(lat, lon, speed, u, v)

    out_png = out_dir / "current_surface_map_today.png"
    make_map_png(
        out_png=out_png,
        date=snapshot_date,
        lat=lat,
        lon=lon,
        u=u,
        v=v,
        speed=speed,
        hotspot=hotspot,
        mean_dir_label=mean_dir_label,
    )

    y, m, d = snapshot_date.split("-")
    archive_dir = history_dir / y / m / d
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_png = archive_dir / f"current_surface_map_{snapshot_date}.png"
    archive_png.write_bytes(out_png.read_bytes())

    meta = {
        "module": "nelaya_ai_daily_current_surface_map",
        "version": "0.1",
        "created_at": datetime.now(ZoneInfo("Asia/Jakarta")).isoformat(),
        "snapshot_date": snapshot_date,
        "source_file": str(current_file),
        "output_png": str(out_png),
        "archive_png": str(archive_png),
        "mean_direction_deg": mean_dir_deg,
        "mean_direction_label": mean_dir_label,
        "hotspot": hotspot,
    }

    meta_file = out_dir / "current_surface_map_today.json"
    meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 78)
    print("DONE")
    print("=" * 78)
    print(f"PNG  : {out_png}")
    print(f"META : {meta_file}")
    print(f"ARCH : {archive_png}")
    print(json.dumps(meta, indent=2, ensure_ascii=False))
    print("=" * 78)


if __name__ == "__main__":
    main()
