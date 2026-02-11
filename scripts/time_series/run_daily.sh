#!/usr/bin/env bash
set -euo pipefail

cd /home/coastalai/NELAYA-AI-LAB

# default CFG (kalau environment belum ngeset)
export CFG="${CFG:-/home/coastalai/NELAYA-AI-LAB/config/time_series_aceh.json}"

# jalankan untuk kemarin (UTC) agar data sudah tersedia
DAY="$(date -u -d "yesterday" +%F)"

echo "[INFO] daily update for ${DAY}"
./scripts/time_series/run_one_day.sh "${DAY}"
