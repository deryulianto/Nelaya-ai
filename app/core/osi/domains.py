from __future__ import annotations

from .config import DEFAULT_SCORES, DOMAIN_CEILINGS
from .schemas import OsiFeatures
from .scoring import clamp, inverse_trapezoid_score, trapezoid_score, weighted_sum


def _cap(name: str, value: float) -> float:
    return clamp(min(value, DOMAIN_CEILINGS[name]))


def compute_thermal_score(features: OsiFeatures) -> float:
    # Dibuat lebih ketat agar SST tropis hangat stabil tidak otomatis sangat tinggi
    s_sst = trapezoid_score(features.sst_c, 28.4, 29.0, 29.7, 30.6)

    s_sst_anom = (
        inverse_trapezoid_score(abs(features.sst_anom_c), 0.0, 0.0, 0.15, 0.7)
        if features.sst_anom_c is not None
        else DEFAULT_SCORES["sst_anom"]
    )

    s_sst_grad = (
        trapezoid_score(features.sst_gradient, 0.04, 0.10, 0.28, 0.80)
        if features.sst_gradient is not None
        else DEFAULT_SCORES["sst_grad"]
    )

    s_thermal_balance = (
        trapezoid_score(features.delta_t_0_200, 6.0, 8.5, 15.0, 22.0)
        if features.delta_t_0_200 is not None
        else DEFAULT_SCORES["thermal_balance"]
    )

    score = weighted_sum(
        [
            (0.36, s_sst),
            (0.26, s_sst_anom),
            (0.14, s_sst_grad),
            (0.24, s_thermal_balance),
        ]
    )
    return _cap("thermal", score)


def compute_productivity_score(features: OsiFeatures) -> float:
    chl = features.chl_mg_m3
    zone = features.zone_class

    # Shelf dibuat lebih konservatif:
    # CHL 0.24 dianggap moderat, bukan hampir maksimum
    if zone == "coastal":
        s_chl_level = trapezoid_score(chl, 0.10, 0.22, 0.45, 0.95)
    elif zone == "offshore":
        s_chl_level = trapezoid_score(chl, 0.04, 0.09, 0.18, 0.42)
    else:  # shelf
        s_chl_level = trapezoid_score(chl, 0.07, 0.16, 0.24, 0.55)

    s_chl_anom = (
        inverse_trapezoid_score(abs(features.chl_anom), 0.0, 0.0, 0.08, 0.35)
        if features.chl_anom is not None
        else DEFAULT_SCORES["chl_anom"]
    )

    s_chl_persistence = (
        clamp(100.0 * features.chl_persistence_3d)
        if features.chl_persistence_3d is not None
        else DEFAULT_SCORES["chl_persistence"]
    )

    s_chl_grad = (
        trapezoid_score(features.chl_gradient, 0.02, 0.05, 0.14, 0.35)
        if features.chl_gradient is not None
        else DEFAULT_SCORES["chl_grad"]
    )

    # Persistence diturunkan pengaruhnya agar tidak mengangkat terlalu banyak
    score = weighted_sum(
        [
            (0.50, s_chl_level),
            (0.18, s_chl_persistence),
            (0.14, s_chl_grad),
            (0.18, s_chl_anom),
        ]
    )
    return _cap("productivity", score)


def compute_dynamic_score(features: OsiFeatures) -> float:
    s_wave = trapezoid_score(features.wave_hs_m, 0.10, 0.35, 0.85, 1.60)
    s_wind = trapezoid_score(features.wind_ms, 1.0, 2.2, 4.8, 7.0)

    s_current = (
        trapezoid_score(features.current_ms, 0.04, 0.10, 0.24, 0.55)
        if features.current_ms is not None
        else DEFAULT_SCORES["current"]
    )

    s_ssh = (
        inverse_trapezoid_score(abs(features.ssh_anom_cm), 0.0, 0.0, 4.0, 12.0)
        if features.ssh_anom_cm is not None
        else DEFAULT_SCORES["ssh"]
    )

    raw = weighted_sum(
        [
            (0.30, s_wave),
            (0.30, s_wind),
            (0.22, s_current),
            (0.18, s_ssh),
        ]
    )

    # Balanced ocean ≠ extreme dynamic
    score = raw * 0.84
    return _cap("dynamic", score)


def compute_vertical_score(features: OsiFeatures) -> float:
    s_thermocline = (
        trapezoid_score(features.thermocline_depth_m, 18.0, 35.0, 90.0, 150.0)
        if features.thermocline_depth_m is not None
        else None
    )

    s_mld = (
        trapezoid_score(features.mld_m, 10.0, 18.0, 40.0, 75.0)
        if features.mld_m is not None
        else DEFAULT_SCORES["mld"]
    )

    if features.delta_t_0_200 is not None:
        s_strat = trapezoid_score(features.delta_t_0_200, 5.0, 8.0, 15.0, 22.0)
    elif features.stratification_index is not None:
        s_strat = trapezoid_score(features.stratification_index, 0.18, 0.35, 1.00, 2.20)
    else:
        s_strat = DEFAULT_SCORES["strat"]

    s_profile_shape = DEFAULT_SCORES["profile_shape"]

    if s_thermocline is not None:
        score = weighted_sum(
            [
                (0.34, s_thermocline),
                (0.26, s_mld),
                (0.28, s_strat),
                (0.12, s_profile_shape),
            ]
        )
    else:
        score = weighted_sum(
            [
                (0.60, s_mld),
                (0.28, s_strat),
                (0.12, s_profile_shape),
            ]
        )

    return _cap("vertical", score)


def compute_confidence_score(features: OsiFeatures) -> float:
    s_freshness = inverse_trapezoid_score(features.freshness_hours, 0.0, 0.0, 10.0, 48.0)
    s_complete = clamp(100.0 * features.completeness_ratio)

    s_spatial = (
        inverse_trapezoid_score(features.spatial_distance_km, 0.0, 0.0, 8.0, 30.0)
        if features.spatial_distance_km is not None
        else DEFAULT_SCORES["spatial"]
    )

    s_time_align = (
        clamp(100.0 * features.time_alignment_score)
        if features.time_alignment_score is not None
        else DEFAULT_SCORES["time_align"]
    )

    score = weighted_sum(
        [
            (0.30, s_freshness),
            (0.28, s_complete),
            (0.20, s_spatial),
            (0.22, s_time_align),
        ]
    )
    return _cap("data_confidence", score)