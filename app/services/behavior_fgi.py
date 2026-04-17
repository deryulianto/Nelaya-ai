from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional, Tuple

import numpy as np

from app.services.behavior_profiles import SPECIES_PROFILES, SpeciesProfile


EPS = 1e-12


def _safe_array(x: Any) -> np.ndarray:
    arr = np.asarray(x, dtype=float)
    return arr


def _nanminmax_scale(x: np.ndarray) -> np.ndarray:
    x = _safe_array(x)
    xmin = np.nanmin(x)
    xmax = np.nanmax(x)
    if not np.isfinite(xmin) or not np.isfinite(xmax) or abs(xmax - xmin) < EPS:
        return np.zeros_like(x, dtype=float)
    return (x - xmin) / (xmax - xmin + EPS)


def _clip01(x: np.ndarray) -> np.ndarray:
    return np.clip(x, 0.0, 1.0)


def _mid_optimum_score(x: np.ndarray, vmin: float, vmax: float, softness: float = 0.35) -> np.ndarray:
    """
    Skor 0..1 berdasarkan kedekatan ke rentang optimum.
    Di tengah rentang skor ~1, lalu turun halus di luar rentang.
    """
    x = _safe_array(x)
    center = (vmin + vmax) / 2.0
    half = max((vmax - vmin) / 2.0, EPS)
    dist = np.abs(x - center) / half
    score = 1.0 - softness * np.maximum(dist - 1.0, 0.0) - 0.5 * np.minimum(dist, 1.0)
    return _clip01(score)


def _range_score(x: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    """
    Skor 1 bila di dalam rentang, turun linier di luar rentang.
    """
    x = _safe_array(x)
    width = max(vmax - vmin, EPS)
    below = np.where(x < vmin, (vmin - x) / width, 0.0)
    above = np.where(x > vmax, (x - vmax) / width, 0.0)
    penalty = below + above
    return _clip01(1.0 - penalty)


def _stability_score(*arrays: np.ndarray) -> np.ndarray:
    z_list = []

    for arr in arrays:
        arr = _safe_array(arr)
        finite = np.isfinite(arr)

        if not np.any(finite):
            z = np.full_like(arr, np.nan)
        else:
            mu = np.nanmean(arr)
            sd = np.nanstd(arr)

            if not np.isfinite(sd) or sd < EPS:
                z = np.zeros_like(arr)
                z[~finite] = np.nan
            else:
                z = np.abs((arr - mu) / (sd + EPS))
                z[~finite] = np.nan

        z_list.append(z)

    stack = np.stack(z_list, axis=0)

    valid_mask = np.any(np.isfinite(stack), axis=0)

    z_mean = np.full(stack.shape[1:], np.nan)
    z_mean[valid_mask] = np.nanmean(stack[:, valid_mask], axis=0)

    return _clip01(1.0 - _nanminmax_scale(z_mean))


def _robust_scale(x: np.ndarray, q_low: float = 5.0, q_high: float = 95.0) -> np.ndarray:
    x = _safe_array(x)
    valid = x[np.isfinite(x)]
    if valid.size == 0:
        return np.zeros_like(x, dtype=float)

    lo = np.nanpercentile(valid, q_low)
    hi = np.nanpercentile(valid, q_high)

    if not np.isfinite(lo) or not np.isfinite(hi) or abs(hi - lo) < EPS:
        return np.zeros_like(x, dtype=float)

    out = (x - lo) / (hi - lo + EPS)
    return _clip01(out)


def _gradient_front_score(
    sst: np.ndarray,
    chl: np.ndarray,
    dx: float = 1.0,
    dy: float = 1.0,
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """
    Front score yang lebih sensitif:
    - gradien SST dan CHL dihitung
    - ditransformasi log1p agar front halus tetap muncul
    - dinormalisasi robust pakai percentile
    """
    sst = _safe_array(sst)
    chl = _safe_array(chl)

    sst_gy, sst_gx = np.gradient(sst, dy, dx)
    chl_gy, chl_gx = np.gradient(chl, dy, dx)

    sst_grad = np.hypot(sst_gx, sst_gy)
    chl_grad = np.hypot(chl_gx, chl_gy)

    # log transform agar gradien kecil-menengah tetap terbaca
    sst_grad_log = np.log1p(np.where(np.isfinite(sst_grad), sst_grad, 0.0))
    chl_grad_log = np.log1p(np.where(np.isfinite(chl_grad), chl_grad, 0.0))

    # robust scaling, lebih stabil daripada min-max mentah
    sst_grad_n = _robust_scale(sst_grad_log, q_low=10.0, q_high=95.0)
    chl_grad_n = _robust_scale(chl_grad_log, q_low=10.0, q_high=95.0)

    # untuk pelagis tropis, front CHL sering sangat penting
    front_score = 0.45 * sst_grad_n + 0.55 * chl_grad_n
    front_score = _clip01(front_score)

    return front_score, {
        "sst_gradient": sst_grad,
        "chl_gradient": chl_grad,
        "sst_gradient_log": sst_grad_log,
        "chl_gradient_log": chl_grad_log,
        "sst_gradient_norm": sst_grad_n,
        "chl_gradient_norm": chl_grad_n,
    }


def _ssh_score(ssh_cm: np.ndarray, abs_limit_cm: float) -> np.ndarray:
    """
    SSH moderat masih dianggap baik.
    Penalti dibuat halus, tidak langsung mematikan seluruh domain.
    """
    ssh_cm = _safe_array(ssh_cm)
    ratio = np.abs(ssh_cm) / max(abs_limit_cm, EPS)

    # penalti halus
    score = 1.0 - 0.6 * ratio
    return _clip01(score)


def _explanation_from_means(means: Dict[str, float], species: str) -> str:
    parts = [f"Behavior-based FGI untuk {species} menunjukkan respons gabungan terhadap sinyal laut."]
    sst = means.get("sst_score", np.nan)
    chl = means.get("chl_score", np.nan)
    front = means.get("front_score", np.nan)
    wind = means.get("wind_score", np.nan)
    wave = means.get("wave_score", np.nan)
    stability = means.get("stability_score", np.nan)

    if np.isfinite(front):
        if front >= 0.70:
            parts.append("Front oseanografi terlihat kuat, yang biasanya mendukung agregasi ikan.")
        elif front >= 0.45:
            parts.append("Front oseanografi sedang, masih cukup mendukung pencarian makan.")
        else:
            parts.append("Front oseanografi lemah, sehingga peluang agregasi bisa lebih menyebar.")

    if np.isfinite(sst):
        if sst >= 0.70:
            parts.append("Suhu laut berada dekat rentang optimum perilaku target.")
        elif sst < 0.40:
            parts.append("Suhu laut relatif kurang ideal untuk perilaku optimum target.")

    if np.isfinite(chl):
        if chl >= 0.70:
            parts.append("Produktivitas perairan mendukung ketersediaan rantai makanan.")
        elif chl < 0.40:
            parts.append("Produktivitas relatif rendah untuk mendukung konsentrasi mangsa.")

    if np.isfinite(wind) and np.isfinite(wave):
        if wind < 0.35 or wave < 0.35:
            parts.append("Kondisi angin/gelombang kurang ideal di sebagian area.")
        elif wind >= 0.60 and wave >= 0.60:
            parts.append("Kondisi angin dan gelombang masih cukup sesuai untuk habitat target.")

    if np.isfinite(stability):
        if stability >= 0.70:
            parts.append("Kolom air relatif stabil untuk mendukung efisiensi gerak ikan.")
        elif stability < 0.40:
            parts.append("Variabilitas sinyal cukup tinggi, menandakan habitat cenderung kurang stabil.")

    return " ".join(parts)

def _safe_mean(arr: np.ndarray) -> float:
    arr = np.asarray(arr, dtype=float)
    if not np.any(np.isfinite(arr)):
        return 0.0
    return float(np.nanmean(arr))

def compute_behavior_fgi(
    *,
    sst: np.ndarray,
    chl: np.ndarray,
    wind: np.ndarray,
    wave: np.ndarray,
    salinity: np.ndarray,
    ssh_cm: np.ndarray,
    species: str = "medium_pelagic",
    dx: float = 1.0,
    dy: float = 1.0,
    hotspot_threshold: float = 0.65,
) -> Dict[str, Any]:
    if species not in SPECIES_PROFILES:
        raise ValueError(f"Unknown species profile: {species}")

    profile: SpeciesProfile = SPECIES_PROFILES[species]

    sst = _safe_array(sst)
    chl = _safe_array(chl)
    wind = _safe_array(wind)
    wave = _safe_array(wave)
    salinity = _safe_array(salinity)
    ssh_cm = _safe_array(ssh_cm)

    if not (sst.shape == chl.shape == wind.shape == wave.shape == salinity.shape == ssh_cm.shape):
        raise ValueError("All input arrays must have the same shape.")

    sst_score = _mid_optimum_score(sst, profile.sst_opt_min, profile.sst_opt_max)
    chl_score = _range_score(chl, profile.chl_opt_min, profile.chl_opt_max)
    wind_score = _range_score(wind, profile.wind_opt_min, profile.wind_opt_max)
    wave_score = _range_score(wave, profile.wave_opt_min, profile.wave_opt_max)
    sal_score = _range_score(salinity, profile.sal_opt_min, profile.sal_opt_max)
    ssh_score = _ssh_score(ssh_cm, profile.ssh_abs_limit_cm)

    front_score, front_meta = _gradient_front_score(sst=sst, chl=chl, dx=dx, dy=dy)
    stability_score = _stability_score(sst, chl, wind, salinity, ssh_cm)

    behavior_score = (
        profile.w_sst * sst_score
        + profile.w_chl * chl_score
        + profile.w_wind * wind_score
        + profile.w_wave * wave_score
        + profile.w_sal * sal_score
        + profile.w_ssh * ssh_score
        + profile.w_front * front_score
        + profile.w_stability * stability_score
    )

    behavior_score = _clip01(behavior_score)
    hotspot_mask = behavior_score >= hotspot_threshold

    component_means = {
         "sst_score": _safe_mean(sst_score),
         "chl_score": _safe_mean(chl_score),
         "wind_score": _safe_mean(wind_score),
         "wave_score": _safe_mean(wave_score),
         "salinity_score": _safe_mean(sal_score),
         "ssh_score": _safe_mean(ssh_score),
         "front_score": _safe_mean(front_score),
         "stability_score": _safe_mean(stability_score),
         "behavior_score": _safe_mean(behavior_score),
         "hotspot_fraction": _safe_mean(hotspot_mask.astype(float)),
    }

    explanation = _explanation_from_means(component_means, species)

    return {
        "species": species,
        "profile": asdict(profile),
        "component_means": component_means,
        "behavior_score_grid": behavior_score,
        "hotspot_mask": hotspot_mask,
        "components": {
            "sst_score": sst_score,
            "chl_score": chl_score,
            "wind_score": wind_score,
            "wave_score": wave_score,
            "salinity_score": sal_score,
            "ssh_score": ssh_score,
            "front_score": front_score,
            "stability_score": stability_score,
            **front_meta,
        },
        "explanation": explanation,
    }
