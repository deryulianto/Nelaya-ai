from __future__ import annotations

from typing import Any, Dict, Optional

from app.utils.rumpon import compute_rumpon_influence


FORMULA_VERSION = "FGI-R_v1_202603"


def to_band(p: float) -> str:
    return "High" if p >= 0.75 else ("Medium" if p >= 0.50 else "Low")


def clamp01(x: float) -> float:
    return float(max(0.0, min(1.0, float(x))))


def blend_fgi_r(
    fgi_env: float,
    rumpon_influence: float,
    *,
    w_env: float = 0.85,
    w_rumpon: float = 0.15,
) -> float:
    s = (w_env * float(fgi_env)) + (w_rumpon * float(rumpon_influence))
    return clamp01(s)


def enrich_feature_with_rumpon(
    feature: Dict[str, Any],
    rumpon_points,
    *,
    lambda_km: float = 15.0,
    radius_km: float = 20.0,
    n_ref: int = 3,
    w_distance: float = 0.7,
    w_density: float = 0.2,
    w_legal: float = 0.1,
    w_env: float = 0.85,
    w_rumpon: float = 0.15,
    mode: str = "full",  # full | env_only
) -> Optional[Dict[str, Any]]:
    geom = feature.get("geometry") or {}
    if geom.get("type") != "Point":
        return None

    coords = geom.get("coordinates") or []
    if not isinstance(coords, list) or len(coords) < 2:
        return None

    lon = float(coords[0])
    lat = float(coords[1])

    props = feature.get("properties") or {}
    fgi_env = props.get("score")
    if fgi_env is None:
        return None

    fgi_env = float(fgi_env)

    # komponen env yg sekarang memang tersedia di pipeline v1
    env_components = {
        "sst_c": props.get("sst_c"),
        "sal_psu": props.get("sal_psu"),
        "chl_mg_m3": props.get("chl_mg_m3"),
    }

    ri = compute_rumpon_influence(
        lat,
        lon,
        rumpon_points,
        lambda_km=lambda_km,
        radius_km=radius_km,
        n_ref=n_ref,
        w_distance=w_distance,
        w_density=w_density,
        w_legal=w_legal,
    )

    if mode == "env_only":
        fgi_r = clamp01(fgi_env)
        band_r = to_band(fgi_r)
    else:
        fgi_r = blend_fgi_r(
            fgi_env,
            float(ri["rumpon_influence"]),
            w_env=w_env,
            w_rumpon=w_rumpon,
        )
        band_r = to_band(fgi_r)

    out = dict(feature)
    out_props = dict(props)

    out_props.update(
        {
            "fgi_env": round(float(fgi_env), 6),
            "fgi_r": round(float(fgi_r), 6),
            "band_r": band_r,

            # explainability
            "formula_version": FORMULA_VERSION,
            "mode": mode,
            "fgi_env_components": env_components,
            "rumpon_components": {
                "nearest_rumpon_id": ri["nearest_rumpon_id"],
                "nearest_rumpon_km": ri["nearest_rumpon_km"],
                "rumpon_count_radius": ri["rumpon_count_radius"],
                "distance_score": ri["distance_score"],
                "density_score": ri["density_score"],
                "legal_score": ri["legal_score"],
                "rumpon_influence": ri["rumpon_influence"],
            },

            # flat fields (biar frontend lama tetap enak)
            "nearest_rumpon_id": ri["nearest_rumpon_id"],
            "nearest_rumpon_km": ri["nearest_rumpon_km"],
            "rumpon_count_radius": ri["rumpon_count_radius"],
            "distance_score": ri["distance_score"],
            "density_score": ri["density_score"],
            "legal_score": ri["legal_score"],
            "rumpon_influence": ri["rumpon_influence"],
        }
    )

    out["properties"] = out_props
    return out


def enrich_spot_dict_with_rumpon(
    spot: Dict[str, Any],
    rumpon_points,
    *,
    lambda_km: float = 15.0,
    radius_km: float = 20.0,
    n_ref: int = 3,
    w_distance: float = 0.7,
    w_density: float = 0.2,
    w_legal: float = 0.1,
    w_env: float = 0.85,
    w_rumpon: float = 0.15,
    mode: str = "full",
) -> Dict[str, Any]:
    lat = float(spot["lat"])
    lon = float(spot["lon"])
    fgi_env = float(spot["fgi"])

    ri = compute_rumpon_influence(
        lat,
        lon,
        rumpon_points,
        lambda_km=lambda_km,
        radius_km=radius_km,
        n_ref=n_ref,
        w_distance=w_distance,
        w_density=w_density,
        w_legal=w_legal,
    )

    if mode == "env_only":
        fgi_r = clamp01(fgi_env)
    else:
        fgi_r = blend_fgi_r(
            fgi_env,
            float(ri["rumpon_influence"]),
            w_env=w_env,
            w_rumpon=w_rumpon,
        )

    out = dict(spot)
    out.update(
        {
            "fgi_env": round(fgi_env, 6),
            "fgi_r": round(fgi_r, 6),
            "band_r": to_band(fgi_r),
            "formula_version": FORMULA_VERSION,
            "mode": mode,
            "nearest_rumpon_id": ri["nearest_rumpon_id"],
            "nearest_rumpon_km": ri["nearest_rumpon_km"],
            "rumpon_count_radius": ri["rumpon_count_radius"],
            "distance_score": ri["distance_score"],
            "density_score": ri["density_score"],
            "legal_score": ri["legal_score"],
            "rumpon_influence": ri["rumpon_influence"],
        }
    )
    return out