#!/usr/bin/env python3
"""
NELAYA-AI Daily Grid Ocean Scoring v0.1.0

Membaca ocean grid aktif, mengambil nilai variabel laut dari file NetCDF terbaru,
lalu menghasilkan skor awal fish-ground suitability berbasis grid cell.

Output:
- data/grid/daily/grid_scoring_YYYY-MM-DD.csv
- data/grid/daily/grid_scoring_YYYY-MM-DD_top.geojson
- data/grid/daily/grid_scoring_YYYY-MM-DD_summary.json

Catatan ilmiah:
Ini adalah experimental grid suitability layer.
Bukan estimasi biomassa ikan dan bukan Species Distribution Model final.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


VAR_CANDIDATES = {
    "sst": ["analysed_sst", "sst", "sea_surface_temperature", "thetao", "water_temp", "temperature"],
    "chl": ["CHL", "chl", "chlor_a", "chlorophyll", "mass_concentration_of_chlorophyll_a_in_sea_water"],
    "uo": ["uo", "eastward_sea_water_velocity", "u", "ugos"],
    "vo": ["vo", "northward_sea_water_velocity", "v", "vgos"],
    "salinity": ["so", "salinity", "sea_water_salinity"],
    "ssh": ["zos", "adt", "sla", "ssh", "sea_surface_height"],
    "u_wind": ["eastward_wind", "u10", "uwnd", "u"],
    "v_wind": ["northward_wind", "v10", "vwnd", "v"],
    "wave_height": ["VHM0", "swh", "hs", "significant_wave_height"],
}


SEARCH_GROUPS = {
    "sst": ["sst_nrt", "sst", "thetao"],
    "chl": ["chl_nrt", "chlorophyll", "chl"],
    "current": ["phy", "cur", "current", "uo", "vo"],
    "salinity": ["sal_anfc", "salinity", "so"],
    "ssh": ["ssh_anfc", "zos", "ssh", "phy"],
    "wind": ["wind_nrt", "wind", "u10", "v10"],
    "wave": ["wave_anfc", "wave", "VHM0", "swh"],
}


def latest_nc_for_group(group: str) -> Optional[Path]:
    roots = [
        Path("data/raw/aceh_simeulue"),
        Path("data/raw"),
        Path("data/processed"),
    ]

    keywords = SEARCH_GROUPS[group]
    candidates: List[Path] = []

    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.nc"):
            low = str(p).lower()
            if any(k.lower() in low for k in keywords):
                candidates.append(p)

    if not candidates:
        return None

    # File terbaru berdasarkan modified time. Ini paling cocok untuk operasional harian.
    candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def guess_lon_lat_names(ds):
    lon_names = ["lon", "longitude", "x"]
    lat_names = ["lat", "latitude", "y"]

    lon_name = next((n for n in lon_names if n in ds.coords or n in ds.variables), None)
    lat_name = next((n for n in lat_names if n in ds.coords or n in ds.variables), None)

    return lon_name, lat_name


def find_var(ds, names: List[str]) -> Optional[str]:
    lower_map = {v.lower(): v for v in list(ds.variables)}
    for name in names:
        if name in ds.variables:
            return name
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def reduce_to_2d(da):
    # Ambil waktu terbaru jika ada.
    for tname in ["time", "valid_time"]:
        if tname in da.dims:
            da = da.isel({tname: -1})

    # Ambil lapisan permukaan jika ada depth/depth-like.
    for dname in ["depth", "deptht", "lev", "level"]:
        if dname in da.dims:
            da = da.isel({dname: 0})

    # Kalau masih ada dimensi lain yang bukan lat/lon, ambil index pertama.
    for dim in list(da.dims):
        if dim.lower() not in ["lat", "latitude", "y", "lon", "longitude", "x"]:
            da = da.isel({dim: 0})

    return da


def sample_var(path: Path, var_names: List[str], lons: np.ndarray, lats: np.ndarray) -> Tuple[np.ndarray, Optional[str]]:
    import xarray as xr

    ds = xr.open_dataset(path)
    lon_name, lat_name = guess_lon_lat_names(ds)

    if lon_name is None or lat_name is None:
        ds.close()
        return np.full(len(lons), np.nan), None

    var_name = find_var(ds, var_names)
    if var_name is None:
        ds.close()
        return np.full(len(lons), np.nan), None

    da = reduce_to_2d(ds[var_name])

    try:
        lon_da = xr.DataArray(lons, dims="cell")
        lat_da = xr.DataArray(lats, dims="cell")
        vals = da.interp({lon_name: lon_da, lat_name: lat_da}, method="linear").values
        vals = np.asarray(vals, dtype=float).reshape(-1)
    except Exception:
        vals = []
        for lon, lat in zip(lons, lats):
            try:
                v = da.sel({lon_name: float(lon), lat_name: float(lat)}, method="nearest").values
                vals.append(float(np.asarray(v).squeeze()))
            except Exception:
                vals.append(np.nan)
        vals = np.array(vals, dtype=float)

    ds.close()
    return vals, var_name


def safe_minmax_score(x, good_min, good_max, hard_min, hard_max):
    if np.isnan(x):
        return np.nan

    x = float(x)

    if x <= hard_min or x >= hard_max:
        return 0.0

    if good_min <= x <= good_max:
        return 1.0

    if hard_min < x < good_min:
        return (x - hard_min) / (good_min - hard_min)

    if good_max < x < hard_max:
        return (hard_max - x) / (hard_max - good_max)

    return 0.0


def chl_score(chl):
    if np.isnan(chl) or chl <= 0:
        return np.nan

    # CHL sangat skewed; pakai log10 agar nilai ekstrem tidak mendominasi.
    lx = math.log10(float(chl))

    # Kisaran tropis operasional yang moderat. Ini heuristic awal.
    # 0.05 mg/m3 -> -1.30, 0.2 -> -0.70, 2.0 -> 0.30, 8.0 -> 0.90
    return safe_minmax_score(lx, -0.70, 0.30, -1.30, 0.90)


def depth_score(depth):
    if np.isnan(depth):
        return np.nan

    d = float(depth)

    # FGI umum pelagis: shelf-slope lebih diberi bobot,
    # laut sangat dangkal dan sangat dalam tidak langsung dinilai nol.
    if d < 20:
        return 0.25
    if d < 50:
        return 0.45
    if d < 200:
        return 0.85
    if d < 1000:
        return 1.00
    if d < 3000:
        return 0.65
    return 0.45


def classify_safety(wave, wind, current_speed):
    labels = []
    risks = []

    if not np.isnan(wave):
        if wave >= 2.5:
            labels.append("unsafe")
            risks.append("wave_high")
        elif wave >= 1.5:
            labels.append("watch")
            risks.append("wave_moderate")

    if not np.isnan(wind):
        if wind >= 12.0:
            labels.append("unsafe")
            risks.append("wind_high")
        elif wind >= 8.0:
            labels.append("watch")
            risks.append("wind_moderate")

    if not np.isnan(current_speed):
        if current_speed >= 1.5:
            labels.append("unsafe")
            risks.append("current_strong")
        elif current_speed >= 0.9:
            labels.append("watch")
            risks.append("current_moderate")

    if "unsafe" in labels:
        return "unsafe", ",".join(risks)
    if "watch" in labels:
        return "watch", ",".join(risks)

    return "favorable", "none"


def fgi_grid_score(row):
    scores = {}

    scores["sst"] = safe_minmax_score(row.get("sst_c", np.nan), 27.0, 30.5, 24.0, 33.0)
    scores["chl"] = chl_score(row.get("chl", np.nan))
    scores["current"] = safe_minmax_score(row.get("current_speed", np.nan), 0.10, 0.80, 0.00, 1.60)
    scores["depth"] = depth_score(row.get("depth_m", np.nan))
    scores["ssh"] = safe_minmax_score(abs(row.get("ssh", np.nan)), 0.00, 0.35, 0.00, 1.00)

    weights = {
        "sst": 0.25,
        "chl": 0.25,
        "current": 0.20,
        "depth": 0.20,
        "ssh": 0.10,
    }

    numerator = 0.0
    denominator = 0.0

    for k, w in weights.items():
        v = scores[k]
        if not np.isnan(v):
            numerator += w * v
            denominator += w

    if denominator == 0:
        return np.nan, 0.0

    return round(numerator / denominator, 4), round(denominator / sum(weights.values()), 3)


def classify_fgi(score):
    if np.isnan(score):
        return "unknown"
    if score >= 0.75:
        return "high"
    if score >= 0.60:
        return "moderate_high"
    if score >= 0.45:
        return "moderate"
    if score >= 0.30:
        return "low_moderate"
    return "low"


def to_top_geojson(df: pd.DataFrame, out_path: Path, top_n: int = 500) -> None:
    top = df.sort_values("fgi_grid_score", ascending=False).head(top_n).copy()

    features = []
    for _, r in top.iterrows():
        x0 = float(r["lon_min"])
        x1 = float(r["lon_max"])
        y0 = float(r["lat_min"])
        y1 = float(r["lat_max"])

        props = {}
        keep_cols = [
            "cell_id", "grid_i", "grid_j",
            "lon_center", "lat_center", "depth_m", "depth_class",
            "sst_c", "chl", "current_speed", "salinity", "ssh",
            "wind_speed", "wave_height",
            "fgi_grid_score", "fgi_grid_label",
            "safety_label", "safety_risk",
            "confidence", "rank_overall"
        ]

        for col in keep_cols:
            val = r.get(col, None)
            if pd.isna(val):
                val = None
            elif isinstance(val, np.integer):
                val = int(val)
            elif isinstance(val, np.floating):
                val = float(val)
            props[col] = val

        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [x0, y0],
                    [x1, y0],
                    [x1, y1],
                    [x0, y1],
                    [x0, y0],
                ]]
            }
        })

    geojson = {
        "type": "FeatureCollection",
        "name": f"NELAYA-AI Top {top_n} Daily Grid Scoring",
        "features": features,
    }

    out_path.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--grid", default="data/grid/master/aceh_grid_0083_ocean.csv")
    parser.add_argument("--top-n", type=int, default=500)
    args = parser.parse_args()

    grid_path = Path(args.grid)
    if not grid_path.exists():
        raise FileNotFoundError(f"Ocean grid tidak ditemukan: {grid_path}")

    out_dir = Path("data/grid/daily")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(grid_path)
    lons = df["lon_center"].to_numpy(dtype=float)
    lats = df["lat_center"].to_numpy(dtype=float)

    sources: Dict[str, Optional[str]] = {}
    used_vars: Dict[str, Optional[str]] = {}

    print("=== NELAYA-AI Daily Grid Ocean Scoring v0.1.0 ===")
    print(f"Date       : {args.date}")
    print(f"Ocean cells : {len(df):,}")

    # SST
    sst_path = latest_nc_for_group("sst")
    sources["sst"] = str(sst_path) if sst_path else None
    if sst_path:
        vals, var = sample_var(sst_path, VAR_CANDIDATES["sst"], lons, lats)
        # Kelvin to Celsius jika perlu
        vals = np.where(vals > 100, vals - 273.15, vals)
        df["sst_c"] = np.round(vals, 3)
        used_vars["sst"] = var
    else:
        df["sst_c"] = np.nan
        used_vars["sst"] = None

    # CHL
    chl_path = latest_nc_for_group("chl")
    sources["chl"] = str(chl_path) if chl_path else None
    if chl_path:
        vals, var = sample_var(chl_path, VAR_CANDIDATES["chl"], lons, lats)
        df["chl"] = np.round(vals, 5)
        used_vars["chl"] = var
    else:
        df["chl"] = np.nan
        used_vars["chl"] = None

    # Current uo/vo
    cur_path = latest_nc_for_group("current")
    sources["current"] = str(cur_path) if cur_path else None
    if cur_path:
        u, var_u = sample_var(cur_path, VAR_CANDIDATES["uo"], lons, lats)
        v, var_v = sample_var(cur_path, VAR_CANDIDATES["vo"], lons, lats)
        df["uo"] = np.round(u, 4)
        df["vo"] = np.round(v, 4)
        df["current_speed"] = np.round(np.sqrt(u*u + v*v), 4)
        used_vars["uo"] = var_u
        used_vars["vo"] = var_v
    else:
        df["uo"] = np.nan
        df["vo"] = np.nan
        df["current_speed"] = np.nan
        used_vars["uo"] = None
        used_vars["vo"] = None

    # Salinity
    sal_path = latest_nc_for_group("salinity")
    sources["salinity"] = str(sal_path) if sal_path else None
    if sal_path:
        vals, var = sample_var(sal_path, VAR_CANDIDATES["salinity"], lons, lats)
        df["salinity"] = np.round(vals, 3)
        used_vars["salinity"] = var
    else:
        df["salinity"] = np.nan
        used_vars["salinity"] = None

    # SSH
    ssh_path = latest_nc_for_group("ssh")
    sources["ssh"] = str(ssh_path) if ssh_path else None
    if ssh_path:
        vals, var = sample_var(ssh_path, VAR_CANDIDATES["ssh"], lons, lats)
        df["ssh"] = np.round(vals, 4)
        used_vars["ssh"] = var
    else:
        df["ssh"] = np.nan
        used_vars["ssh"] = None

    # Wind
    wind_path = latest_nc_for_group("wind")
    sources["wind"] = str(wind_path) if wind_path else None
    if wind_path:
        u, var_u = sample_var(wind_path, VAR_CANDIDATES["u_wind"], lons, lats)
        v, var_v = sample_var(wind_path, VAR_CANDIDATES["v_wind"], lons, lats)
        df["u_wind"] = np.round(u, 3)
        df["v_wind"] = np.round(v, 3)
        df["wind_speed"] = np.round(np.sqrt(u*u + v*v), 3)
        used_vars["u_wind"] = var_u
        used_vars["v_wind"] = var_v
    else:
        df["u_wind"] = np.nan
        df["v_wind"] = np.nan
        df["wind_speed"] = np.nan
        used_vars["u_wind"] = None
        used_vars["v_wind"] = None

    # Wave
    wave_path = latest_nc_for_group("wave")
    sources["wave"] = str(wave_path) if wave_path else None
    if wave_path:
        vals, var = sample_var(wave_path, VAR_CANDIDATES["wave_height"], lons, lats)
        df["wave_height"] = np.round(vals, 3)
        used_vars["wave_height"] = var
    else:
        df["wave_height"] = np.nan
        used_vars["wave_height"] = None

    # Scores
    results = df.apply(fgi_grid_score, axis=1, result_type="expand")
    df["fgi_grid_score"] = results[0]
    df["confidence"] = results[1]
    df["fgi_grid_label"] = df["fgi_grid_score"].apply(classify_fgi)

    safety = df.apply(
        lambda r: classify_safety(
            r.get("wave_height", np.nan),
            r.get("wind_speed", np.nan),
            r.get("current_speed", np.nan),
        ),
        axis=1,
        result_type="expand",
    )
    df["safety_label"] = safety[0]
    df["safety_risk"] = safety[1]

    # Ranking: utamakan score tinggi, confidence tinggi, dan tidak unsafe.
    safety_bonus = df["safety_label"].map({"favorable": 1.0, "watch": 0.85, "unsafe": 0.45}).fillna(0.5)
    df["operational_score"] = np.round(df["fgi_grid_score"].fillna(0) * df["confidence"].fillna(0) * safety_bonus, 4)
    df["rank_overall"] = df["operational_score"].rank(ascending=False, method="first").astype(int)

    df["scoring_date"] = args.date
    df["module"] = "nelaya_ai_grid_daily_scoring"
    df["version"] = "0.1.0-experimental"
    df["generated_at_utc"] = datetime.now(timezone.utc).isoformat()

    out_csv = out_dir / f"grid_scoring_{args.date}.csv"
    out_geojson = out_dir / f"grid_scoring_{args.date}_top.geojson"
    out_summary = out_dir / f"grid_scoring_{args.date}_summary.json"

    df.to_csv(out_csv, index=False)
    to_top_geojson(df, out_geojson, top_n=args.top_n)

    summary = {
        "module": "nelaya_ai_grid_daily_scoring",
        "version": "0.1.0-experimental",
        "date": args.date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ocean_cells": int(len(df)),
        "sources": sources,
        "used_vars": used_vars,
        "label_counts": df["fgi_grid_label"].value_counts(dropna=False).to_dict(),
        "safety_counts": df["safety_label"].value_counts(dropna=False).to_dict(),
        "confidence_mean": float(np.nanmean(df["confidence"])),
        "score_mean": float(np.nanmean(df["fgi_grid_score"])),
        "top_cells": df.sort_values("operational_score", ascending=False)[
            ["cell_id", "lon_center", "lat_center", "depth_m", "fgi_grid_score", "operational_score", "confidence", "safety_label"]
        ].head(20).to_dict(orient="records"),
        "scientific_note": (
            "Experimental grid suitability layer. "
            "Not biomass estimation and not final species distribution model. "
            "Requires field validation with standardized catch/effort/species data."
        ),
    }

    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=== Sources Detected ===")
    for k, v in sources.items():
        print(f"{k:10s}: {v}")

    print()
    print("=== Variables Used ===")
    for k, v in used_vars.items():
        print(f"{k:12s}: {v}")

    print()
    print("=== Output ===")
    print(f"CSV     : {out_csv}")
    print(f"GeoJSON : {out_geojson}")
    print(f"Summary : {out_summary}")

    print()
    print("=== Label counts ===")
    print(df["fgi_grid_label"].value_counts(dropna=False).to_string())

    print()
    print("=== Safety counts ===")
    print(df["safety_label"].value_counts(dropna=False).to_string())

    print()
    print("=== Top 15 operational cells ===")
    print(
        df.sort_values("operational_score", ascending=False)[
            ["rank_overall", "cell_id", "lon_center", "lat_center", "depth_m", "fgi_grid_score", "operational_score", "confidence", "safety_label"]
        ].head(15).to_string(index=False)
    )


if __name__ == "__main__":
    main()
