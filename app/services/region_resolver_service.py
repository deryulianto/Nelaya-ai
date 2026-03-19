from __future__ import annotations

from pathlib import Path
import json
from typing import Dict, Any, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
GIS_FILE = ROOT / "data" / "gis" / "aceh_regions.json"


def _norm(s: str) -> str:
    return " ".join((s or "").lower().strip().split())


def _load_regions():
    if not GIS_FILE.exists():
        return []

    try:
        return json.loads(GIS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


REGIONS = _load_regions()


def resolve_region_from_gis(name: str) -> Optional[Dict[str, Any]]:
    q = _norm(name)

    for r in REGIONS:
        if _norm(r.get("name")) == q:
            return r

        # fuzzy match
        if q in _norm(r.get("name")):
            return r

    return None


def resolve_region_spatial(name: str) -> Optional[Dict[str, Any]]:
    """
    Return:
    {
      name,
      center: (lat, lon),
      bbox: [minx, miny, maxx, maxy]
    }
    """
    r = resolve_region_from_gis(name)
    if not r:
        return None

    center = r.get("center")
    bbox = r.get("bbox")

    if not center:
        return None

    return {
        "name": r.get("name"),
        "center": tuple(center),
        "bbox": bbox,
        "type": r.get("type"),
    }
