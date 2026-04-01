#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

DAY_WIB="$(TZ=Asia/Jakarta date +%F)"

echo "[INFO] Running temp_profile + sal_profile for WIB day: ${DAY_WIB}"

METRICS="temp_profile,sal_profile" bash ./scripts/time_series/run_one_day.sh "${DAY_WIB}"

echo
echo "[INFO] Verify temp_profile endpoint"
curl -s "http://127.0.0.1:8001/api/v1/fgi/time-series/temp-profile?date=${DAY_WIB}&max_depth=200" | jq '.date, (.points|length)'

echo
echo "[INFO] Verify sal_profile endpoint"
curl -s "http://127.0.0.1:8001/api/v1/fgi/time-series/sal-profile?date=${DAY_WIB}&max_depth=200" | jq '.date, (.points|length)'
