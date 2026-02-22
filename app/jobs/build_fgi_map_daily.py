from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
FGI_DAILY_LATEST = ROOT / "data" / "fgi_daily" / "latest.json"
MAP_DIR = ROOT / "data" / "fgi_map"
MAP_DIR.mkdir(parents=True, exist_ok=True)

def main() -> int:
    if not FGI_DAILY_LATEST.exists():
        raise SystemExit(f"[ERR] missing {FGI_DAILY_LATEST}. Run: python scripts/daily_fgi.py")

    daily = json.loads(FGI_DAILY_LATEST.read_text(encoding="utf-8"))
    d = daily.get("date_utc") or datetime.now(timezone.utc).date().isoformat()

    region = daily.get("region") or {"min_lon": 92, "max_lon": 99, "min_lat": 1, "max_lat": 7}
    min_lon = float(region["min_lon"]); max_lon = float(region["max_lon"])
    min_lat = float(region["min_lat"]); max_lat = float(region["max_lat"])

    # polygon box
    coords = [[
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
        [min_lon, min_lat],
    ]]

    feature = {
        "type": "Feature",
        "properties": {
            "date_utc": d,
            "fgi": daily.get("fgi", {}),
            "means": daily.get("means", {}),
            "note": "v0 box map (upgrade to grid map later)",
        },
        "geometry": {"type": "Polygon", "coordinates": coords},
    }

    geojson = {
        "type": "FeatureCollection",
        "features": [feature],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    out_day = MAP_DIR / f"fgi_map_{d}.geojson"
    out_latest = MAP_DIR / "latest.geojson"
    out_day.write_text(json.dumps(geojson, indent=2), encoding="utf-8")
    out_latest.write_text(json.dumps(geojson, indent=2), encoding="utf-8")

    print(f"[OK] wrote {out_day}")
    print(f"[OK] wrote {out_latest}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
