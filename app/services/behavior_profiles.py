from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class SpeciesProfile:
    name: str
    sst_opt_min: float
    sst_opt_max: float
    chl_opt_min: float
    chl_opt_max: float
    wind_opt_min: float
    wind_opt_max: float
    wave_opt_min: float
    wave_opt_max: float
    sal_opt_min: float
    sal_opt_max: float
    ssh_abs_limit_cm: float

    # Bobot komponen
    w_sst: float
    w_chl: float
    w_wind: float
    w_wave: float
    w_sal: float
    w_ssh: float
    w_front: float
    w_stability: float


SPECIES_PROFILES: Dict[str, SpeciesProfile] = {
    "large_pelagic": SpeciesProfile(
        name="large_pelagic",
        sst_opt_min=26.0,
        sst_opt_max=30.0,
        chl_opt_min=0.10,
        chl_opt_max=0.60,
        wind_opt_min=3.0,
        wind_opt_max=8.0,
        wave_opt_min=0.3,
        wave_opt_max=2.5,
        sal_opt_min=32.0,
        sal_opt_max=35.5,
        ssh_abs_limit_cm=25.0,
        w_sst=0.20,
        w_chl=0.10,
        w_wind=0.08,
        w_wave=0.07,
        w_sal=0.08,
        w_ssh=0.10,
        w_front=0.25,
        w_stability=0.12,
    ),
    "medium_pelagic": SpeciesProfile(
        name="medium_pelagic",
        sst_opt_min=27.0,
        sst_opt_max=31.0,
        chl_opt_min=0.15,
        chl_opt_max=0.80,
        wind_opt_min=2.0,
        wind_opt_max=7.0,
        wave_opt_min=0.2,
        wave_opt_max=2.0,
        sal_opt_min=31.0,
        sal_opt_max=35.5,
        ssh_abs_limit_cm=30.0,
        w_sst=0.18,
        w_chl=0.16,
        w_wind=0.09,
        w_wave=0.08,
        w_sal=0.08,
        w_ssh=0.08,
        w_front=0.20,
        w_stability=0.13,
    ),
    "small_pelagic": SpeciesProfile(
        name="small_pelagic",
        sst_opt_min=26.0,
        sst_opt_max=32.0,
        chl_opt_min=0.20,
        chl_opt_max=1.20,
        wind_opt_min=3.0,
        wind_opt_max=8.0,
        wave_opt_min=0.1,
        wave_opt_max=1.5,
        sal_opt_min=28.0,
        sal_opt_max=35.5,
        ssh_abs_limit_cm=35.0,
        w_sst=0.14,
        w_chl=0.24,
        w_wind=0.10,
        w_wave=0.10,
        w_sal=0.08,
        w_ssh=0.06,
        w_front=0.15,
        w_stability=0.13,
    ),
}
