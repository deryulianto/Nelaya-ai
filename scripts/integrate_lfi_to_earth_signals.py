#!/usr/bin/env python3
"""
Integrate LFI Alpha into earth_signals_today.json as an experimental FGI shadow metric.

Adds:
- metrics.lfi_alpha
- metrics.fgi_lagrangian_aware

This does NOT replace existing FGI or fgi_current_aware.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def value_from_metric(x: Any) -> Optional[float]:
    if isinstance(x, dict):
        v = x.get("value")
    else:
        v = x

    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--earth", default="data/earth/earth_signals_today.json")
    parser.add_argument("--lfi", default="data/physics/lagrangian_front_today.json")
    parser.add_argument("--alpha", type=float, default=0.15, help="LFI weight for FGI shadow model")
    parser.add_argument("--backup", action="store_true", help="Write a backup before modifying earth file")
    args = parser.parse_args()

    earth_path = Path(args.earth)
    lfi_path = Path(args.lfi)

    earth = read_json(earth_path)
    lfi = read_json(lfi_path)

    metrics = earth.setdefault("metrics", {})

    fgi_current = value_from_metric(metrics.get("fgi_current_aware"))
    fgi_base = value_from_metric(metrics.get("fgi"))

    if fgi_current is None:
        if fgi_base is None:
            raise ValueError("Could not find metrics.fgi_current_aware.value or metrics.fgi.value")
        fgi_current = fgi_base

    summary = lfi.get("summary", {})
    mean_lfi = float(summary.get("mean_lfi") or 0.0)
    max_lfi = float(summary.get("max_lfi") or 0.0)
    top10_mean_lfi = float(summary.get("top10_mean_lfi") or 0.0)

    # Conservative support:
    # - mean_lfi keeps the regional background honest
    # - top10_mean_lfi captures localized front support
    # This prevents a few extreme cells from over-dominating the daily FGI value.
    lfi_regional_support = clip01((0.30 * mean_lfi) + (0.70 * top10_mean_lfi))

    # Hotspot support:
    # Useful later for map/recommendation pages where top zones matter more than the whole domain mean.
    lfi_hotspot_support = clip01(top10_mean_lfi)

    alpha = clip01(args.alpha)

    fgi_lagrangian_regional = clip01(((1.0 - alpha) * fgi_current) + (alpha * lfi_regional_support))
    fgi_lagrangian_hotspot = clip01(((1.0 - alpha) * fgi_current) + (alpha * lfi_hotspot_support))

    source_date = lfi.get("date") or metrics.get("current_source_date") or earth.get("date")

    metrics["lfi_alpha"] = {
        "value": round(lfi_regional_support, 6),
        "unit": "index",
        "source_kind": "lagrangian_front_index_alpha_v0_1",
        "source_date": source_date,
        "source_path": str(lfi_path),
        "band": summary.get("front_strength_label"),
        "note": "LFI Alpha derived from surface-current convergence, shear, vorticity, and speed-gradient proxy.",
        "inputs": {
            "mean_lfi": mean_lfi,
            "max_lfi": max_lfi,
            "top10_mean_lfi": top10_mean_lfi,
            "regional_support_formula": "0.30*mean_lfi + 0.70*top10_mean_lfi",
            "method": lfi.get("method"),
        },
        "scientific_caution": lfi.get("scientific_caution"),
    }

    metrics["fgi_lagrangian_aware"] = {
        "value": round(fgi_lagrangian_regional, 6),
        "unit": "index",
        "source_kind": "fgi_lagrangian_aware_v0_1_shadow",
        "source_date": source_date,
        "source_path": str(lfi_path),
        "band": (
            "high" if fgi_lagrangian_regional >= 0.70
            else "moderate" if fgi_lagrangian_regional >= 0.45
            else "low"
        ),
        "note": "Experimental shadow FGI adjusted with LFI Alpha. Does not replace operational FGI.",
        "inputs": {
            "fgi_current_aware": fgi_current,
            "lfi_regional_support": round(lfi_regional_support, 6),
            "lfi_hotspot_support": round(lfi_hotspot_support, 6),
            "lfi_weight_alpha": alpha,
            "regional_formula": "(1-alpha)*fgi_current_aware + alpha*lfi_regional_support",
            "hotspot_shadow_value": round(fgi_lagrangian_hotspot, 6),
            "hotspot_formula": "(1-alpha)*fgi_current_aware + alpha*lfi_hotspot_support",
        },
        "scientific_caution": (
            "FGI Lagrangian-aware is experimental. It should be interpreted as front-dynamics support, "
            "not as deterministic fish-location prediction."
        ),
    }

    earth.setdefault("metadata", {})
    earth["metadata"]["lfi_integrated_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    if args.backup:
        backup_path = earth_path.with_suffix(".before_lfi.json")
        write_json(backup_path, earth)
        print(f"Backup written: {backup_path}")

    write_json(earth_path, earth)

    print(json.dumps({
        "ok": True,
        "earth": str(earth_path),
        "lfi": str(lfi_path),
        "source_date": source_date,
        "fgi_current_aware": round(fgi_current, 6),
        "mean_lfi": mean_lfi,
        "top10_mean_lfi": top10_mean_lfi,
        "lfi_regional_support": round(lfi_regional_support, 6),
        "lfi_hotspot_support": round(lfi_hotspot_support, 6),
        "fgi_lagrangian_aware": round(fgi_lagrangian_regional, 6),
        "fgi_lagrangian_hotspot_shadow": round(fgi_lagrangian_hotspot, 6),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
