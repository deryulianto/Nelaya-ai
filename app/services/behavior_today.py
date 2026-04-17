from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Set

from app.services.behavior_from_raw import FIELD_SPECS, RAW_BASE, extract_behavior_hotspots


def _available_dates_for_spec(base_dir: Path, kind: str, prefix: str) -> Set[str]:
    kind_dir = base_dir / kind
    if not kind_dir.exists():
        return set()

    out: Set[str] = set()

    for path in kind_dir.rglob("*.nc"):
        name = path.name
        if not name.startswith(prefix) or not name.endswith(".nc"):
            continue

        raw = name[len(prefix):-3]  # strip prefix and .nc
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d")
            out.add(dt.strftime("%Y-%m-%d"))
        except ValueError:
            continue

    return out


def _latest_common_date(base_dir: Path = RAW_BASE) -> str:
    """
    Cari tanggal terbaru yang tersedia lengkap untuk semua field wajib.
    """
    date_sets = []

    for spec in FIELD_SPECS.values():
        dates = _available_dates_for_spec(
            base_dir=base_dir,
            kind=spec.kind,
            prefix=spec.filename_prefix,
        )
        if not dates:
            raise FileNotFoundError(
                f"No dated NetCDF files found for kind={spec.kind} in {base_dir / spec.kind}"
            )
        date_sets.append(dates)

    common = set.intersection(*date_sets)
    if not common:
        raise FileNotFoundError(
            "No common available date found across required raw inputs "
            "(sst, chl, wind, wave, ssh, salinity)."
        )

    return max(common)


def get_behavior_today(
    *,
    species: str = "medium_pelagic",
    hotspot_threshold: float = 0.55,
    top_k: int = 50,
    base_dir: Path = RAW_BASE,
    target_field: str = "sst",
) -> Dict:
    latest_date = _latest_common_date(base_dir=base_dir)

    return extract_behavior_hotspots(
        date_str=latest_date,
        species=species,
        base_dir=base_dir,
        target_field=target_field,
        hotspot_threshold=hotspot_threshold,
        top_k=top_k,
    )