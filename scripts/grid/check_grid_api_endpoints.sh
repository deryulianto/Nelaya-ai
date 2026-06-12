#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-http://127.0.0.1:8001}"

echo "=== NELAYA-AI Grid API Endpoint Check ==="
echo "Base: $BASE"
echo

check_json () {
  local name="$1"
  local url="$2"
  echo "=== $name ==="
  if curl -fsS "$url" | jq . >/tmp/grid_check.json; then
    echo "OK: $url"
    cat /tmp/grid_check.json | jq '{
      module,
      version,
      date,
      target_date,
      dashboard_level,
      status_label,
      quality_label,
      zones_count,
      features_count: (try (.features | length) catch null)
    }'
  else
    echo "FAILED: $url"
    exit 1
  fi
  echo
}

check_json "Health" "$BASE/api/v1/grid/health"
check_json "Dashboard" "$BASE/api/v1/grid/dashboard/today"
check_json "Public Brief" "$BASE/api/v1/grid/brief/public/today"
check_json "Manifest" "$BASE/api/v1/grid/manifest/today"
check_json "Source Audit" "$BASE/api/v1/grid/source-audit/today"
check_json "Zones Today" "$BASE/api/v1/grid/hotspots/zones/today"
check_json "Zone GeoJSON" "$BASE/api/v1/grid/hotspots/zones/geojson"
check_json "Zone Cells GeoJSON" "$BASE/api/v1/grid/hotspots/zones/cells/geojson"
check_json "Persistence W7" "$BASE/api/v1/grid/persistence/public/today?window=7"
check_json "Persistence W14" "$BASE/api/v1/grid/persistence/public/today?window=14"
check_json "Persistence W30" "$BASE/api/v1/grid/persistence/public/today?window=30"

echo "=== ALL GRID ENDPOINTS OK ==="
