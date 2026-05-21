#!/usr/bin/env bash
set -euo pipefail

cd /home/coastalai/NELAYA-AI-LAB

# Aktifkan virtual environment
source .venv/bin/activate

# Environment aman untuk NetCDF/HDF5
export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

# Default: tanggal hari ini dalam timezone server
# Bisa override manual: ./scripts/cron_run_time_series_0500.sh 2026-05-08
RUN_DATE="${1:-$(date +%F)}"

echo "=================================================="
echo "NELAYA-AI Time Series Daily Cron Run"
echo "Started at : $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Run date   : ${RUN_DATE}"
echo "=================================================="

echo
echo "1) Fetch salinity/ocean profile"
python scripts/time_series/01_fetch_so_profile.py --date "${RUN_DATE}"

echo
echo "2) Build salinity profile"
python scripts/time_series/04_make_sal_profile.py --date "${RUN_DATE}"

echo
echo "3) Build temp_profile one-day time series"
METRICS=temp_profile bash scripts/time_series/run_one_day.sh "${RUN_DATE}"

echo
echo "4) Run daily means today"
chmod +x scripts/time_series/run_daily_means_today.sh
bash ./scripts/time_series/run_daily_means_today.sh

echo
echo "=================================================="
echo "Finished at: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "=================================================="
