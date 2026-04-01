#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

DAY_WIB="$(TZ=Asia/Jakarta date +%F)"

echo "[INFO] Running daily mean pipeline for WIB day: ${DAY_WIB}"

METRICS="sst,chlorophyll,current" bash ./scripts/time_series/run_one_day.sh "${DAY_WIB}"

echo
echo "=== latest rows: sst ==="
tail -n 5 data/time_series/aceh/banda_aceh_aceh_besar/sst/series/sst_daily_mean.csv

echo
echo "=== latest rows: chlorophyll ==="
tail -n 5 data/time_series/aceh/banda_aceh_aceh_besar/chlorophyll/series/chlorophyll_daily_mean.csv

echo
echo "=== latest rows: current ==="
tail -n 5 data/time_series/aceh/banda_aceh_aceh_besar/current/series/current_daily_mean.csv

echo
echo "[INFO] Verify endpoint"
curl -s "http://127.0.0.1:8001/api/v1/fgi/time-series/daily-mean?days=90" | jq
