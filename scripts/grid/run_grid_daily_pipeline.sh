#!/usr/bin/env bash
set -euo pipefail

cd ~/NELAYA-AI-LAB

DATE_ARG="${1:-$(date +%F)}"

echo "=== NELAYA-AI Grid Daily Pipeline ==="
echo "Date: ${DATE_ARG}"
echo

echo "1) Build daily grid scoring"
python scripts/grid/build_daily_grid_scoring.py --date "${DATE_ARG}"

echo
echo "2) Calibrate daily grid scoring v0.1.1"
python scripts/grid/calibrate_daily_grid_scoring_v011.py --date "${DATE_ARG}"

echo
echo "3) Build daily hotspot candidates v0.1.0"
python scripts/grid/build_daily_hotspot_candidates.py --date "${DATE_ARG}"

echo
echo "4) Build operational nucleus zones v0.1.2"
python scripts/grid/build_hotspot_zones_v012.py --date "${DATE_ARG}"

echo
echo "5) Build zone GeoJSON v0.1.2"
python scripts/grid/build_hotspot_zones_geojson_v012.py --date "${DATE_ARG}"

echo
echo "6) Build zone-cell GeoJSON v0.1.2"
python scripts/grid/build_hotspot_zone_cells_geojson_v012.py --date "${DATE_ARG}"

echo
echo
echo
echo "7) Build grid source audit"
python scripts/grid/build_grid_source_audit.py --date "${DATE_ARG}"

echo
echo "8) Build grid run manifest"
python scripts/grid/build_grid_run_manifest.py --date "${DATE_ARG}"

echo
echo "=== Pipeline complete ==="
echo "Summary:"
cat "data/grid/hotspots/grid_hotspot_zones_${DATE_ARG}_v012_summary.json" | jq '{
  module,
  version,
  date,
  zones_count,
  zone_level_counts,
  top_zones: .top_zones[:3],
  scientific_note
}'
