#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

DATES=("2026-03-30" "2026-03-31")

echo "[INFO] ROOT=${ROOT_DIR}"
echo "[INFO] Backfill dates: ${DATES[*]}"
echo

for DAY in "${DATES[@]}"; do
  echo "[INFO] Backfill daily means for ${DAY}"
  METRICS="sst,chlorophyll,current" bash ./scripts/time_series/run_one_day.sh "${DAY}"
  echo
done

echo "=== latest rows: sst ==="
tail -n 7 data/time_series/aceh/banda_aceh_aceh_besar/sst/series/sst_daily_mean.csv || true

echo
echo "=== latest rows: chlorophyll ==="
tail -n 7 data/time_series/aceh/banda_aceh_aceh_besar/chlorophyll/series/chlorophyll_daily_mean.csv || true

echo
echo "=== latest rows: current ==="
tail -n 7 data/time_series/aceh/banda_aceh_aceh_besar/current/series/current_daily_mean.csv || true
