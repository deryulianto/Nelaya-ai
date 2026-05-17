#!/usr/bin/env python3
"""
Plot LFI Alpha map as PNG.

Output:
- data/physics/lagrangian_front_today.png

This is a visual diagnostic map:
- LFI Alpha heatmap
- surface current vectors
- top LFI zones
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

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
    safe_gradient,
    robust_norm,
)


def compute_lfi(input_path: Path):
    ds = open_dataset_safely(input_path)

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

    speed = np.sqrt(u * u + v * v)
    mask = (
        np.isfinite(u)
        & np.isfinite(v)
        & np.isfinite(speed)
        & (np.abs(u) < 5.0)
        & (np.abs(v) < 5.0)
        & (speed < 5.0)
    )

    u2 = np.where(mask, u, np.nan)
    v2 = np.where(mask, v, np.nan)
    s2 = np.where(mask, speed, np.nan)

    du_dy, du_dx = safe_gradient(u2, lat, lon)
    dv_dy, dv_dx = safe_gradient(v2, lat, lon)
    ds_dy, ds_dx = safe_gradient(s2, lat, lon)

    divergence = du_dx + dv_dy
    convergence = -divergence
    convergence_pos = np.where(convergence > 0, convergence, 0.0)

    shear = np.sqrt((du_dx - dv_dy) ** 2 + (du_dy + dv_dx) ** 2)
    vorticity = dv_dx - du_dy
    speed_gradient = np.sqrt(ds_dx ** 2 + ds_dy ** 2)

    valid = (
        mask
        & np.isfinite(convergence_pos)
        & np.isfinite(shear)
        & np.isfinite(vorticity)
        & np.isfinite(speed_gradient)
    )

    conv_n = robust_norm(convergence_pos, valid)
    shear_n = robust_norm(shear, valid)
    vort_n = robust_norm(np.abs(vorticity), valid)
    spgrad_n = robust_norm(speed_gradient, valid)

    lfi = (
        0.40 * conv_n
        + 0.35 * shear_n
        + 0.15 * spgrad_n
        + 0.10 * vort_n
    )

    lfi = np.where(valid & np.isfinite(lfi), np.clip(lfi, 0.0, 1.0), np.nan)

    try:
        ds.close()
    except Exception:
        pass

    return lat, lon, u, v, speed, lfi


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--root", default="data/raw/aceh_simeulue/cur_nrt")
    parser.add_argument("--lfi-json", default="data/physics/lagrangian_front_today.json")
    parser.add_argument("--out-png", default="data/physics/lagrangian_front_today.png")
    args = parser.parse_args()

    input_path = latest_current_file(Path(args.root), args.date)
    lat, lon, u, v, speed, lfi = compute_lfi(input_path)

    top_zones = []
    lfi_json = Path(args.lfi_json)
    if lfi_json.exists():
        data = json.loads(lfi_json.read_text(encoding="utf-8"))
        top_zones = data.get("top_zones", [])[:10]
        title_date = data.get("date") or args.date or "latest"
        strength = (data.get("summary") or {}).get("front_strength_label", "—")
    else:
        title_date = args.date or "latest"
        strength = "—"

    lon2d, lat2d = np.meshgrid(lon, lat)

    fig, ax = plt.subplots(figsize=(11, 7))

    im = ax.pcolormesh(lon2d, lat2d, lfi, shading="auto", vmin=0, vmax=1)
    cbar = fig.colorbar(im, ax=ax, pad=0.015)
    cbar.set_label("LFI Alpha score")

    # Current vectors, decimated so the map stays readable
    step_y = max(1, len(lat) // 18)
    step_x = max(1, len(lon) // 20)

    ax.quiver(
        lon2d[::step_y, ::step_x],
        lat2d[::step_y, ::step_x],
        u[::step_y, ::step_x],
        v[::step_y, ::step_x],
        scale=8,
        width=0.0022,
        alpha=0.75,
    )

    if top_zones:
        xs = [z["lon"] for z in top_zones]
        ys = [z["lat"] for z in top_zones]
        ax.scatter(xs, ys, s=55, marker="o", edgecolor="black", linewidth=0.8)

        for z in top_zones[:8]:
            ax.annotate(
                f"#{z['rank']}",
                (z["lon"], z["lat"]),
                textcoords="offset points",
                xytext=(5, 5),
                fontsize=8,
                weight="bold",
            )

    ax.set_title(
        f"NELAYA-AI LFI Alpha — Lagrangian Front Proxy\n"
        f"{title_date} | Front strength: {strength}"
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_xlim(float(np.nanmin(lon)), float(np.nanmax(lon)))
    ax.set_ylim(float(np.nanmin(lat)), float(np.nanmax(lat)))
    ax.grid(True, alpha=0.25)

    subtitle = (
        "Heatmap = LFI Alpha; arrows = surface current; points = top front zones. "
        "Alpha proxy, not full FTLE/LCS."
    )
    fig.text(0.5, 0.015, subtitle, ha="center", fontsize=9)

    out = Path(args.out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)

    print(json.dumps({
        "ok": True,
        "input": str(input_path),
        "output": str(out),
        "top_zones": len(top_zones),
        "date": title_date,
        "front_strength": strength,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
