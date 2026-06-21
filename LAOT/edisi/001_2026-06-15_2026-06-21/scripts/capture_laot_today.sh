#!/usr/bin/env bash
set -u

BASE_LOCAL="http://127.0.0.1:8001"
TODAY="$(date +%F)"
OUTDIR="data/${TODAY}"
mkdir -p "$OUTDIR"

echo "=== LAOT Capture $TODAY ==="

capture_json () {
  NAME="$1"
  URL="$2"
  OUT="$OUTDIR/${NAME}.json"

  echo
  echo ">>> $NAME"
  echo "URL: $URL"

  if curl -sS --max-time 15 "$URL" | jq '.' > "$OUT"; then
    echo "OK -> $OUT"
  else
    echo "GAGAL -> $URL"
    rm -f "$OUT"
  fi
}

capture_json "insight_today" "$BASE_LOCAL/api/v1/insight/today"
capture_json "grid_dashboard_today" "$BASE_LOCAL/api/v1/grid/dashboard/today"
capture_json "grid_brief_today" "$BASE_LOCAL/api/v1/grid/brief/today"
capture_json "grid_health" "$BASE_LOCAL/api/v1/grid/health"
capture_json "ocean_health_public_card_today" "$BASE_LOCAL/api/v1/ocean-health/public-card/today"
capture_json "ocean_health_summary_today" "$BASE_LOCAL/api/v1/ocean-health/summary/today"

echo
echo "Selesai. File tersimpan di: $OUTDIR"
ls -lh "$OUTDIR"
