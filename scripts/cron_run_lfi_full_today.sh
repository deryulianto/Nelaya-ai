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

echo "=================================================="
echo "NELAYA-AI LFI Daily Cron Run"
echo "Started at: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "=================================================="

./scripts/run_lfi_full_today.sh

echo "=================================================="
echo "Finished at: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "=================================================="
