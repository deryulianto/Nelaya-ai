#!/usr/bin/env bash
set -euo pipefail

cd /home/coastalai/NELAYA-AI-LAB

export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTHONFAULTHANDLER=1

PY="/home/coastalai/NELAYA-AI-LAB/.venv/bin/python"
LOG_DIR="/home/coastalai/NELAYA-AI-LAB/logs/tuna_depth_v080"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/tuna_depth_v080_$STAMP.log"

mkdir -p "$LOG_DIR"

{
  echo "============================================================"
  echo "NELAYA-AI Tuna Depth v0.8.0 Daily Pipeline"
  echo "Started: $(date -Is)"
  echo "============================================================"

  echo ""
  echo "=== 1. Download current-depth uo/vo ==="
  "$PY" scripts/download_current_depth_nrt_copernicus.py --days-back 7 || true

  echo ""
  echo "=== 2. Download thermal-depth thetao ==="
  "$PY" scripts/download_thermal_depth_nrt_copernicus.py --days-back 7 || true

  echo ""
  echo "=== 3. Build Tuna Depth Current + Thermal Gate ==="
  "$PY" scripts/build_tuna_depth_current_analysis.py \
    --geojson-threshold 0.72 \
    --max-points 500

  echo ""
  echo "=== 4. Summary check ==="
  jq '{
    version,
    snapshot_date,
    thermal_status: .thermal_diagnostics.status,
    temp_mean_30_100: .thermal_diagnostics.temperature_mean_30_100_stats_c.mean,
    thermal_score_mean: .thermal_diagnostics.thermal_score_stats.mean,
    ecological_confidence: .confidence_breakdown.ecological_confidence,
    overall_confidence: .confidence_breakdown.overall_confidence,
    confidence_label: .confidence_breakdown.confidence_label
  }' data/physics/tuna_depth_current_today.json

  echo ""
  echo "Finished: $(date -Is)"
  echo "============================================================"
} 2>&1 | tee "$LOG_FILE"
