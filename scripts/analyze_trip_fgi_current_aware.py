from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
TRIP_DIR = ROOT / "data/fgi_trip"
EARTH = ROOT / "data/earth/earth_signals_today.json"

earth = json.loads(EARTH.read_text(encoding="utf-8"))

fgi = earth.get("fgi")
fgi_ca = earth.get("fgi_current_aware")
current_ms = earth.get("current_ms")

files = sorted(TRIP_DIR.rglob("*.json")) if TRIP_DIR.exists() else []

rows = []

for f in files:
    try:
        obj = json.loads(f.read_text(encoding="utf-8"))

        success = obj.get("success")
        catch_kg = obj.get("catch_kg")
        fuel_liter = obj.get("fuel_liter")
        data_quality = obj.get("data_quality")

        rows.append({
            "file": str(f),
            "success": success,
            "catch_kg": catch_kg,
            "fuel_liter": fuel_liter,
            "data_quality": data_quality,
        })
    except Exception:
        pass

catch_vals = [r["catch_kg"] for r in rows if isinstance(r.get("catch_kg"), (int, float))]
fuel_vals = [r["fuel_liter"] for r in rows if isinstance(r.get("fuel_liter"), (int, float))]

summary = {
    "ok": True,
    "trip_count": len(rows),
    "earth_snapshot": {
        "fgi": fgi,
        "fgi_current_aware": fgi_ca,
        "delta": None if fgi is None or fgi_ca is None else fgi_ca - fgi,
        "current_ms": current_ms,
    },
    "trip_summary": {
        "success_count": sum(1 for r in rows if r.get("success") is True),
        "failed_count": sum(1 for r in rows if r.get("success") is False),
        "avg_catch_kg": mean(catch_vals) if catch_vals else None,
        "avg_fuel_liter": mean(fuel_vals) if fuel_vals else None,
    },
    "note": "Early comparison only. This does not validate the model yet; it prepares the structure for field calibration.",
}

out = ROOT / "data/fgi_trip/trip_fgi_current_aware_summary.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps(summary, ensure_ascii=False, indent=2))
