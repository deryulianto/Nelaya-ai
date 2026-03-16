from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[2]

CANDIDATE_FILES = {
    "small_islands": [
        ROOT / "data" / "reference" / "pulau_aceh.json",
        ROOT / "data" / "reference" / "pulau_kecil_aceh.json",
        ROOT / "data" / "pulau_aceh.json",
        ROOT / "data" / "pulau_kecil_aceh.json",
    ],
    "rumpon": [
        ROOT / "data" / "reference" / "rumpon_aceh.json",
        ROOT / "data" / "rumpon_aceh.json",
    ],
    "fish": [
        ROOT / "data" / "reference" / "ikan_aceh.json",
        ROOT / "data" / "ikan_aceh.json",
    ],
}


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _load_first_existing(paths: List[Path]) -> List[Dict[str, Any]]:
    for p in paths:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    # fleksibel kalau dibungkus field tertentu
                    for key in ["items", "data", "rows", "features"]:
                        val = data.get(key)
                        if isinstance(val, list):
                            return val
                    return [data]
            except Exception:
                continue
    return []


def _pick_name(row: Dict[str, Any]) -> Optional[str]:
    for k in ["name", "nama", "nama_pulau", "pulau", "island_name"]:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _pick_region(row: Dict[str, Any]) -> Optional[str]:
    for k in ["kabupaten", "kab_kota", "kabupaten_kota", "wilayah", "region"]:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def load_small_islands() -> List[Dict[str, Any]]:
    return _load_first_existing(CANDIDATE_FILES["small_islands"])


def count_small_islands(region: Optional[str] = None) -> Dict[str, Any]:
    rows = load_small_islands()
    if not rows:
        return {"count": 0, "items": [], "region": region, "found": False}

    if region:
        r = _norm(region)
        filtered = []
        for row in rows:
            row_region = _norm(_pick_region(row) or "")
            if r == row_region or r in row_region or row_region in r:
                filtered.append(row)
        rows = filtered

    names = []
    for row in rows:
        nm = _pick_name(row)
        if nm:
            names.append(nm)

    return {
        "count": len(rows),
        "items": names[:20],
        "region": region,
        "found": True,
    }


def list_small_islands(region: Optional[str] = None) -> Dict[str, Any]:
    rows = load_small_islands()
    if not rows:
        return {"items": [], "region": region, "found": False}

    if region:
        r = _norm(region)
        filtered = []
        for row in rows:
            row_region = _norm(_pick_region(row) or "")
            if r == row_region or r in row_region or row_region in r:
                filtered.append(row)
        rows = filtered

    names = []
    for row in rows:
        nm = _pick_name(row)
        if nm:
            names.append(nm)

    return {
        "count": len(names),
        "items": names[:50],
        "region": region,
        "found": True,
    }
