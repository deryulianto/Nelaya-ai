from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import numpy as np
import xarray as xr

from app.services.behavior_fgi import compute_behavior_fgi


RAW_BASE = Path("data/raw/aceh_simeulue")


@dataclass(frozen=True)
class RawFieldSpec:
    kind: str
    filename_prefix: str
    variable_candidates: Tuple[str, ...]


FIELD_SPECS: Dict[str, RawFieldSpec] = {
    "sst": RawFieldSpec(
        kind="sst_nrt",
        filename_prefix="sst_nrt_aceh_",
        variable_candidates=("thetao", "analysed_sst", "sst", "sea_surface_temperature"),
    ),
    "chl": RawFieldSpec(
        kind="chl_nrt",
        filename_prefix="chl_nrt_aceh_",
        variable_candidates=("CHL", "chlor_a", "chl", "chlorophyll"),
    ),
    "wind": RawFieldSpec(
        kind="wind_nrt",
        filename_prefix="wind_nrt_aceh_",
        variable_candidates=("wind_speed", "windspeed", "ws", "speed"),
    ),
    "wave": RawFieldSpec(
        kind="wave_anfc",
        filename_prefix="wave_aceh_",
        variable_candidates=("VHM0", "swh", "wave_height", "hs"),
    ),
    "ssh": RawFieldSpec(
        kind="ssh_anfc",
        filename_prefix="ssh_aceh_",
        variable_candidates=("zos", "adt", "sla", "ssh"),
    ),
    "salinity": RawFieldSpec(
        kind="sal_anfc",
        filename_prefix="sal_aceh_",
        variable_candidates=("so", "salinity", "sss"),
    ),
}


LAT_CANDIDATES = ("latitude", "lat", "nav_lat", "y")
LON_CANDIDATES = ("longitude", "lon", "nav_lon", "x")


def _date_parts(date_str: str) -> Tuple[str, str, str]:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return str(dt.year), f"{dt.month:02d}", dt.strftime("%Y-%m-%d")


def _find_file(spec: RawFieldSpec, date_str: str, base_dir: Path = RAW_BASE) -> Path:
    year, month, ymd = _date_parts(date_str)
    path = base_dir / spec.kind / year / month / f"{spec.filename_prefix}{ymd}.nc"
    if not path.exists():
        raise FileNotFoundError(f"Missing file for {spec.kind}: {path}")
    return path


def _find_coord_name(ds: xr.Dataset, candidates: Iterable[str]) -> Optional[str]:
    for name in candidates:
        if name in ds.coords:
            return name
        if name in ds.dims:
            return name
    return None


def _pick_existing_name(ds: xr.Dataset, names: Iterable[str]) -> Optional[str]:
    for name in names:
        if name in ds.variables:
            return name
    return None


def _pick_main_variable(ds: xr.Dataset, candidates: Iterable[str]) -> str:
    direct = _pick_existing_name(ds, candidates)
    if direct:
        return direct

    for name, da in ds.data_vars.items():
        if np.issubdtype(da.dtype, np.number) and da.ndim >= 2:
            return name

    raise KeyError(
        f"Could not find variable. Candidates={tuple(candidates)} available={list(ds.data_vars)}"
    )


def _drop_to_2d(da: xr.DataArray) -> xr.DataArray:
    """
    Turunkan variable menjadi 2D lat-lon:
    - pilih indeks pertama untuk dim non-spasial
    - squeeze dim singleton
    - transpose ke [lat, lon]
    """
    lat_name = _find_coord_name(da.to_dataset(name="tmp"), LAT_CANDIDATES)
    lon_name = _find_coord_name(da.to_dataset(name="tmp"), LON_CANDIDATES)

    if lat_name is None or lon_name is None:
        raise ValueError(f"Lat/lon coordinates not found for variable {da.name}")

    keep_dims = {lat_name, lon_name}
    indexers: Dict[str, int] = {}

    for dim in da.dims:
        if dim not in keep_dims and da.sizes[dim] > 0:
            indexers[dim] = 0

    if indexers:
        da = da.isel(indexers)

    da = da.squeeze(drop=True)

    if set((lat_name, lon_name)).issubset(da.dims):
        da = da.transpose(lat_name, lon_name)

    return da


def _compute_wind_speed_from_components(ds: xr.Dataset) -> Optional[xr.DataArray]:
    u_candidates = ("u10", "eastward_wind", "uwnd", "u", "uo_wind")
    v_candidates = ("v10", "northward_wind", "vwnd", "v", "vo_wind")

    u_name = _pick_existing_name(ds, u_candidates)
    v_name = _pick_existing_name(ds, v_candidates)

    if not u_name or not v_name:
        return None

    u = _drop_to_2d(ds[u_name])
    v = _drop_to_2d(ds[v_name])
    return np.hypot(u, v).rename("wind_speed")


def _open_field(spec: RawFieldSpec, date_str: str, base_dir: Path = RAW_BASE) -> xr.DataArray:
    path = _find_file(spec, date_str, base_dir=base_dir)

    engines = ["h5netcdf", "netcdf4"]
    last_error: Exception | None = None

    for engine in engines:
        try:
            with xr.open_dataset(
                path,
                engine=engine,
                decode_cf=True,
                mask_and_scale=True,
                cache=False,
            ) as ds:

                # 🔥 CRITICAL: buang attrs (biang crash HDF5)
                try:
                    ds.attrs = {}
                except Exception:
                    pass

                if spec.kind == "wind_nrt":
                    wind_speed = _compute_wind_speed_from_components(ds)
                    if wind_speed is not None:
                        out = wind_speed.load()
                        try:
                            out.attrs = {}
                        except Exception:
                            pass
                        return out

                var_name = _pick_main_variable(ds, spec.variable_candidates)
                da = _drop_to_2d(ds[var_name]).load()

                try:
                    da.attrs = {}
                except Exception:
                    pass

                return da

        except Exception as e:
            last_error = e
            print(f"[WARN] Failed open {path} with {engine}: {e}")
            continue

    raise RuntimeError(
        f"FAILED opening file {path} for {spec.kind}. Last error: {last_error}"
    )


def _interp_like(source: xr.DataArray, target: xr.DataArray) -> xr.DataArray:
    src_lat = _find_coord_name(source.to_dataset(name="tmp"), LAT_CANDIDATES)
    src_lon = _find_coord_name(source.to_dataset(name="tmp"), LON_CANDIDATES)
    tgt_lat = _find_coord_name(target.to_dataset(name="tmp"), LAT_CANDIDATES)
    tgt_lon = _find_coord_name(target.to_dataset(name="tmp"), LON_CANDIDATES)

    if None in (src_lat, src_lon, tgt_lat, tgt_lon):
        raise ValueError("Could not identify lat/lon coordinates for interpolation.")

    rename_map: Dict[str, str] = {}
    if src_lat != tgt_lat:
        rename_map[src_lat] = tgt_lat
    if src_lon != tgt_lon:
        rename_map[src_lon] = tgt_lon

    if rename_map:
        source = source.rename(rename_map)

    return source.interp(
        {
            tgt_lat: target[tgt_lat],
            tgt_lon: target[tgt_lon],
        },
        method="linear",
    )


def _to_numpy(da: xr.DataArray) -> np.ndarray:
    arr = da.values.astype(float)

    finite_mask = np.isfinite(arr)
    if not np.any(finite_mask):
        return arr

    finite_vals = arr[finite_mask]

    # Kelvin -> Celsius untuk SST
    if np.nanmean(finite_vals) > 200:
        arr = arr - 273.15
        finite_vals = arr[np.isfinite(arr)]

    # Meter -> cm untuk SSH
    if da.name in {"zos", "adt", "sla", "ssh"}:
        if np.nanmax(np.abs(finite_vals)) < 10:
            arr = arr * 100.0

    return arr


def _json_safe_2d(arr: np.ndarray) -> list[list[float | None]]:
    arr = np.asarray(arr, dtype=float)
    out: list[list[float | None]] = []

    for row in arr:
        out_row: list[float | None] = []
        for v in row:
            if np.isfinite(v):
                out_row.append(float(v))
            else:
                out_row.append(None)
        out.append(out_row)

    return out


def _json_safe_bool_2d(arr: np.ndarray) -> list[list[bool]]:
    return np.asarray(arr, dtype=bool).tolist()


def load_behavior_inputs_from_raw(
    *,
    date_str: str,
    base_dir: Path = RAW_BASE,
    target_field: str = "sst",
) -> Dict[str, Any]:
    """
    Load semua field dari file raw harian dan samakan grid ke target_field.
    """
    opened: Dict[str, xr.DataArray] = {}
    for key, spec in FIELD_SPECS.items():
        opened[key] = _open_field(spec, date_str, base_dir=base_dir)

    if target_field not in opened:
        raise ValueError(f"Unknown target_field={target_field}")

    target = opened[target_field]

    aligned: Dict[str, xr.DataArray] = {}
    for key, da in opened.items():
        aligned[key] = da if key == target_field else _interp_like(da, target)

    lat_name = _find_coord_name(target.to_dataset(name="tmp"), LAT_CANDIDATES)
    lon_name = _find_coord_name(target.to_dataset(name="tmp"), LON_CANDIDATES)
    if lat_name is None or lon_name is None:
        raise ValueError("Target field does not expose recognizable lat/lon coordinates.")

    return {
        "date": date_str,
        "lat_name": lat_name,
        "lon_name": lon_name,
        "lat": target[lat_name].values.tolist(),
        "lon": target[lon_name].values.tolist(),
        "sst": _to_numpy(aligned["sst"]),
        "chl": _to_numpy(aligned["chl"]),
        "wind": _to_numpy(aligned["wind"]),
        "wave": _to_numpy(aligned["wave"]),
        "salinity": _to_numpy(aligned["salinity"]),
        "ssh_cm": _to_numpy(aligned["ssh"]),
    }


def compute_behavior_fgi_from_raw(
    *,
    date_str: str,
    species: str = "medium_pelagic",
    base_dir: Path = RAW_BASE,
    target_field: str = "sst",
    hotspot_threshold: float = 0.65,
) -> Dict[str, Any]:
    inputs = load_behavior_inputs_from_raw(
        date_str=date_str,
        base_dir=base_dir,
        target_field=target_field,
    )

    lat = np.asarray(inputs["lat"], dtype=float)
    lon = np.asarray(inputs["lon"], dtype=float)

    dx = 1.0
    dy = 1.0
    if lon.size >= 2:
        dx = float(np.nanmean(np.abs(np.diff(lon))))
    if lat.size >= 2:
        dy = float(np.nanmean(np.abs(np.diff(lat))))

    result = compute_behavior_fgi(
        sst=inputs["sst"],
        chl=inputs["chl"],
        wind=inputs["wind"],
        wave=inputs["wave"],
        salinity=inputs["salinity"],
        ssh_cm=inputs["ssh_cm"],
        species=species,
        dx=dx,
        dy=dy,
        hotspot_threshold=hotspot_threshold,
    )

    if result is None:
        raise ValueError("compute_behavior_fgi returned None")

    behavior_grid = np.asarray(result["behavior_score_grid"], dtype=float)
    hotspot_mask = np.asarray(result["hotspot_mask"], dtype=bool)

    return {
        "date": date_str,
        "species": species,
        "lat": [float(x) for x in inputs["lat"]],
        "lon": [float(x) for x in inputs["lon"]],
        "component_means": result["component_means"],
        "explanation": result["explanation"],
        "behavior_score_grid": _json_safe_2d(behavior_grid),
        "hotspot_mask": _json_safe_bool_2d(hotspot_mask),
        "components": result["components"],
        "meta": {
            "target_field": target_field,
            "grid_shape": list(behavior_grid.shape),
            "base_dir": str(base_dir),
        },
    }


def extract_behavior_hotspots(
    *,
    date_str: str,
    species: str = "medium_pelagic",
    base_dir: Path = RAW_BASE,
    target_field: str = "sst",
    hotspot_threshold: float = 0.55,
    top_k: int = 150,
) -> Dict[str, Any]:
    result = compute_behavior_fgi_from_raw(
        date_str=date_str,
        species=species,
        base_dir=base_dir,
        target_field=target_field,
        hotspot_threshold=hotspot_threshold,
    )

    if result is None:
        raise ValueError("compute_behavior_fgi_from_raw returned None")

    lat = np.asarray(result["lat"], dtype=float)
    lon = np.asarray(result["lon"], dtype=float)

    grid = np.asarray(
        [
            [np.nan if v is None else float(v) for v in row]
            for row in result["behavior_score_grid"]
        ],
        dtype=float,
    )
    hotspot_mask = np.asarray(result["hotspot_mask"], dtype=bool)

    if grid.ndim != 2:
        raise ValueError(f"behavior_score_grid must be 2D, got shape={grid.shape}")
    if hotspot_mask.shape != grid.shape:
        raise ValueError(
            f"hotspot_mask shape {hotspot_mask.shape} does not match grid shape {grid.shape}"
        )
    if lat.size != grid.shape[0]:
        raise ValueError(f"lat size {lat.size} does not match grid rows {grid.shape[0]}")
    if lon.size != grid.shape[1]:
        raise ValueError(f"lon size {lon.size} does not match grid cols {grid.shape[1]}")

    points: list[Dict[str, float]] = []

    nlat, nlon = grid.shape
    for i in range(nlat):
        for j in range(nlon):
            score = grid[i, j]
            if not np.isfinite(score):
                continue
            if hotspot_mask[i, j]:
                points.append(
                    {
                        "lat": float(lat[i]),
                        "lon": float(lon[j]),
                        "score": float(score),
                    }
                )

    points.sort(key=lambda x: x["score"], reverse=True)

    if top_k > 0:
        points = points[:top_k]

    return {
        "date": result["date"],
        "species": result["species"],
        "threshold": float(hotspot_threshold),
        "count": len(points),
        "points": points,
        "component_means": result["component_means"],
        "explanation": result["explanation"],
        "meta": {
            **result["meta"],
            "top_k": int(top_k),
        },
    }