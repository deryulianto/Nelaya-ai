#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np
import xarray as xr


ROOT = Path(__file__).resolve().parents[1]

OUT_GEOJSON = ROOT / "data/coastline/aceh_coastline_proxy_gebco.geojson"
OUT_SUMMARY = ROOT / "data/coastline/aceh_coastline_proxy_gebco_summary.json"


def now_jakarta() -> str:
    return datetime.now(ZoneInfo("Asia/Jakarta")).isoformat()


def find_default_gebco() -> Path:
    patterns = [
        "data/**/GEBCO*.nc",
        "data/**/*gebco*.nc",
        "data/**/*bathymetry*.nc",
        "data/**/*batimetri*.nc",
    ]

    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(ROOT.glob(pattern))

    candidates = sorted(set(candidates))

    if not candidates:
        raise FileNotFoundError(
            "File GEBCO NetCDF belum ditemukan. Jalankan dengan --gebco <path_file.nc>"
        )

    # Pilih file paling besar sebagai kandidat utama.
    candidates = sorted(candidates, key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0]


def pick_name(names: list[str], candidates: list[str]) -> Optional[str]:
    lower_map = {name.lower(): name for name in names}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    parts = [float(x.strip()) for x in text.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox harus format: min_lon,min_lat,max_lon,max_lat")
    return parts[0], parts[1], parts[2], parts[3]


def subset_coord(coord, min_v: float, max_v: float):
    vals = coord.values
    if vals[0] <= vals[-1]:
        return slice(min_v, max_v)
    return slice(max_v, min_v)


def estimate_zero_crossing(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    Fraksi dari a ke b saat elevasi memotong 0.
    Jika gagal, pakai 0.5.
    """
    denom = np.abs(a) + np.abs(b)
    frac = np.where(denom > 0, np.abs(a) / denom, 0.5)
    return np.clip(frac, 0.0, 1.0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Aceh coastline proxy from GEBCO zero-crossing."
    )
    parser.add_argument("--gebco", default=None, help="Path file GEBCO .nc")
    parser.add_argument(
        "--bbox",
        default="90,1,102,7",
        help="min_lon,min_lat,max_lon,max_lat. Default Aceh broad bbox.",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=50000,
        help="Maksimum titik coastline proxy yang disimpan.",
    )
    parser.add_argument(
        "--var",
        default=None,
        help="Nama variable elevasi/bathymetry. Jika kosong, auto-detect.",
    )

    args = parser.parse_args()

    gebco_path = Path(args.gebco) if args.gebco else find_default_gebco()
    if not gebco_path.is_absolute():
        gebco_path = ROOT / gebco_path

    if not gebco_path.exists():
        raise FileNotFoundError(f"File GEBCO tidak ditemukan: {gebco_path}")

    min_lon, min_lat, max_lon, max_lat = parse_bbox(args.bbox)

    ds = xr.open_dataset(gebco_path, decode_times=False)

    lon_name = pick_name(list(ds.coords), ["lon", "longitude", "x"])
    lat_name = pick_name(list(ds.coords), ["lat", "latitude", "y"])

    if lon_name is None or lat_name is None:
        raise ValueError(f"Tidak bisa mendeteksi koordinat lon/lat. Coords: {list(ds.coords)}")

    if args.var:
        var_name = args.var
    else:
        var_name = pick_name(list(ds.data_vars), ["elevation", "z", "Band1", "band_data"])

    if var_name is None:
        raise ValueError(f"Tidak bisa mendeteksi variable elevasi. Data vars: {list(ds.data_vars)}")

    sub = ds.sel(
        {
            lon_name: subset_coord(ds[lon_name], min_lon, max_lon),
            lat_name: subset_coord(ds[lat_name], min_lat, max_lat),
        }
    )

    da = sub[var_name]

    # Pastikan urutan dim lat, lon.
    da = da.transpose(lat_name, lon_name)

    lats = sub[lat_name].values.astype(float)
    lons = sub[lon_name].values.astype(float)
    z = da.values.astype(float)

    if z.ndim != 2:
        raise ValueError(f"Variable {var_name} harus 2D setelah subset, ndim={z.ndim}")

    valid = np.isfinite(z)
    land = z >= 0

    points: list[tuple[float, float]] = []

    # Horizontal sign changes: antar kolom lon
    h_mask = valid[:, :-1] & valid[:, 1:] & (land[:, :-1] != land[:, 1:])
    h_rows, h_cols = np.where(h_mask)

    if len(h_rows):
        z1 = z[h_rows, h_cols]
        z2 = z[h_rows, h_cols + 1]
        frac = estimate_zero_crossing(z1, z2)

        lon1 = lons[h_cols]
        lon2 = lons[h_cols + 1]
        lat = lats[h_rows]

        lon_zero = lon1 + frac * (lon2 - lon1)

        points.extend((float(lon), float(la)) for lon, la in zip(lon_zero, lat))

    # Vertical sign changes: antar baris lat
    v_mask = valid[:-1, :] & valid[1:, :] & (land[:-1, :] != land[1:, :])
    v_rows, v_cols = np.where(v_mask)

    if len(v_rows):
        z1 = z[v_rows, v_cols]
        z2 = z[v_rows + 1, v_cols]
        frac = estimate_zero_crossing(z1, z2)

        lat1 = lats[v_rows]
        lat2 = lats[v_rows + 1]
        lon = lons[v_cols]

        lat_zero = lat1 + frac * (lat2 - lat1)

        points.extend((float(lo), float(lat)) for lo, lat in zip(lon, lat_zero))

    # Deduplicate kasar agar file tidak terlalu besar.
    seen = set()
    unique_points: list[tuple[float, float]] = []

    for lon, lat in points:
        key = (round(lon, 5), round(lat, 5))
        if key in seen:
            continue
        seen.add(key)
        unique_points.append((key[0], key[1]))

    total_before_downsample = len(unique_points)

    if args.max_points > 0 and len(unique_points) > args.max_points:
        step = math.ceil(len(unique_points) / args.max_points)
        unique_points = unique_points[::step]

    feature = {
        "type": "Feature",
        "properties": {
            "name": "Aceh coastline proxy from GEBCO",
            "source": str(gebco_path.relative_to(ROOT)),
            "method": "zero_crossing_elevation_0m",
            "note": "Coastline proxy untuk prototype Legal-Aware FGI; bukan garis pantai resmi/legal.",
        },
        "geometry": {
            "type": "MultiPoint",
            "coordinates": [[lon, lat] for lon, lat in unique_points],
        },
    }

    geojson = {
        "type": "FeatureCollection",
        "module": "aceh_coastline_proxy_gebco",
        "version": "0.1",
        "generated_at": now_jakarta(),
        "source_file": str(gebco_path.relative_to(ROOT)),
        "bbox": [min_lon, min_lat, max_lon, max_lat],
        "variable": var_name,
        "grid_shape": {
            "lat": int(len(lats)),
            "lon": int(len(lons)),
        },
        "point_count": len(unique_points),
        "point_count_before_downsample": total_before_downsample,
        "limitations": [
            "Diturunkan dari GEBCO elevasi 0m, bukan coastline resmi.",
            "Tidak cocok sebagai dasar keputusan hukum final.",
            "Untuk zona 0–4 mil nelayan kecil, perlu diganti dengan garis pantai resmi/lebih detail.",
            "Akurasi menurun di muara, mangrove, pantai landai, dan pulau kecil.",
        ],
        "features": [feature],
    }

    summary = {
        "module": "aceh_coastline_proxy_gebco_summary",
        "version": "0.1",
        "generated_at": geojson["generated_at"],
        "source_file": geojson["source_file"],
        "output_geojson": str(OUT_GEOJSON.relative_to(ROOT)),
        "bbox": geojson["bbox"],
        "variable": var_name,
        "grid_shape": geojson["grid_shape"],
        "point_count": geojson["point_count"],
        "point_count_before_downsample": geojson["point_count_before_downsample"],
        "message": "Coastline proxy GEBCO berhasil dibuat. Gunakan untuk prototype Legal-Aware FGI, bukan keputusan hukum final.",
        "limitations": geojson["limitations"],
    }

    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)

    with OUT_GEOJSON.open("w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    with OUT_SUMMARY.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"OK: wrote {OUT_GEOJSON}")
    print(f"OK: wrote {OUT_SUMMARY}")
    print(f"INFO: source={gebco_path}")
    print(f"INFO: var={var_name}")
    print(f"INFO: points={len(unique_points)}")
    print("WARNING: Ini coastline proxy dari GEBCO, bukan garis pantai resmi/legal.")


if __name__ == "__main__":
    main()
