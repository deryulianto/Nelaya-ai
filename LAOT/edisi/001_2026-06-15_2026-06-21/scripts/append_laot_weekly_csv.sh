#!/usr/bin/env bash
set -euo pipefail

DAY="${1:-$(date +%F)}"
ROW="data/${DAY}/laot_daily_row.json"
OUT="data/laot_weekly_rows_2026-06-15_2026-06-21.csv"

if [ ! -f "$ROW" ]; then
  echo "File tidak ditemukan: $ROW"
  echo "Jalankan dulu: ./scripts/extract_laot_day.sh $DAY"
  exit 1
fi

python3 - "$DAY" "$ROW" "$OUT" <<'PY'
import sys, json, csv
from pathlib import Path

day, row_path, out_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
data = json.loads(row_path.read_text(encoding="utf-8"))

top = data.get("grid", {}).get("top_zone") or {}

fields = [
    "capture_date","insight_date","sst","sst_class","chl","chl_class",
    "wave","wave_class","wind","wind_class","fgi_final","fgi_0_100_temp",
    "fgi_confidence","grid_level","grid_quality","zones_count","top_zone",
    "zone_level","lon_center","lat_center","depth_mean_m","depth_class",
    "mean_operational_score","mean_confidence","ocean_health_status"
]

new = {
    "capture_date": data.get("capture_date"),
    "insight_date": data.get("insight_date"),
    "sst": data.get("ocean_signals", {}).get("sst"),
    "sst_class": data.get("ocean_signals", {}).get("sst_class"),
    "chl": data.get("ocean_signals", {}).get("chl"),
    "chl_class": data.get("ocean_signals", {}).get("chl_class"),
    "wave": data.get("ocean_signals", {}).get("wave"),
    "wave_class": data.get("ocean_signals", {}).get("wave_class"),
    "wind": data.get("ocean_signals", {}).get("wind"),
    "wind_class": data.get("ocean_signals", {}).get("wind_class"),
    "fgi_final": data.get("fgi", {}).get("final"),
    "fgi_0_100_temp": data.get("fgi", {}).get("final_0_100"),
    "fgi_confidence": data.get("fgi", {}).get("confidence"),
    "grid_level": data.get("grid", {}).get("dashboard_level"),
    "grid_quality": data.get("grid", {}).get("quality_label"),
    "zones_count": data.get("grid", {}).get("zones_count"),
    "top_zone": top.get("zone_id"),
    "zone_level": top.get("zone_level"),
    "lon_center": top.get("lon_center"),
    "lat_center": top.get("lat_center"),
    "depth_mean_m": top.get("depth_mean_m"),
    "depth_class": top.get("dominant_depth_class"),
    "mean_operational_score": top.get("mean_operational_score"),
    "mean_confidence": top.get("mean_overall_confidence"),
    "ocean_health_status": data.get("ocean_health", {}).get("status_label"),
}

rows = []
if out_path.exists() and out_path.stat().st_size > 0:
    with out_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

# Upsert: hapus baris tanggal yang sama, lalu masukkan versi terbaru
rows = [r for r in rows if r.get("capture_date") != day]
rows.append({k: "" if new.get(k) is None else new.get(k) for k in fields})
rows.sort(key=lambda r: r.get("capture_date", ""))

with out_path.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

print(f"OK upsert -> {out_path} ({len(rows)} baris)")
PY

cat "$OUT"
