#!/usr/bin/env bash
set -u

ROOT="/home/coastalai/NELAYA-AI-LAB"
PY="$ROOT/.venv/bin/python"
LOG_DIR="$ROOT/logs"
DATE_RUN="$(date '+%Y-%m-%d %H:%M:%S %Z')"

mkdir -p "$LOG_DIR"

export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

cd "$ROOT" || exit 1

log() {
  echo ""
  echo "=============================================================================="
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $1"
  echo "=============================================================================="
}

run_step() {
  local name="$1"
  shift

  log "START: $name"
  "$@"
  local code=$?

  if [ $code -ne 0 ]; then
    log "FAILED: $name with code $code"
    exit $code
  fi

  log "DONE: $name"
}

optional_step() {
  local name="$1"
  shift

  log "START OPTIONAL: $name"
  "$@"
  local code=$?

  if [ $code -ne 0 ]; then
    log "WARNING OPTIONAL FAILED: $name with code $code"
    return 0
  fi

  log "DONE OPTIONAL: $name"
}

echo "NELAYA-AI Daily Ocean Pipeline v0.7.3-alpha.1"
echo "Run at: $DATE_RUN"

run_step "Download current surface NRT" \
  "$PY" scripts/download_current_nrt_copernicus.py --days-back 7

run_step "Download current multi-depth NRT 0-120 m" \
  "$PY" scripts/download_current_depth_nrt_copernicus.py --days-back 7 --max-depth 120

run_step "Build daily current analysis dashboard" \
  "$PY" scripts/build_current_analysis_daily.py --days-back 10

run_step "Build daily current surface map" \
  "$PY" scripts/build_current_surface_map_daily.py --days-back 10

run_step "Build ocean dynamic physics layer" \
  "$PY" scripts/build_ocean_dynamic_physics_features.py --front-threshold 0.50

run_step "Sync current metrics into earth signals" \
  "$PY" scripts/sync_earth_current_from_dynamic_physics.py

optional_step "Build FGI physics support" \
  "$PY" scripts/build_physics_informed_fgi_v06.py

run_step "Build tuna depth current analysis" \
  "$PY" scripts/build_tuna_depth_current_analysis.py --geojson-threshold 0.90 --max-points 150

optional_step "Build FGI temporal memory" \
  "$PY" scripts/build_fgi_temporal_memory.py

log "FINAL CHECK"

echo "Earth current:"
cat data/earth/earth_signals_today.json | jq '.metrics | {
  current_ms,
  current_direction_label,
  current_source_date,
  current_source
}' || true

echo "Current analysis:"
cat data/physics/current_analysis_today.json | jq '{
  snapshot_date,
  mean_speed: .speed_stats.mean,
  max_speed: .speed_stats.max,
  dominant_direction_label,
  hotspot
}' || true

echo "Tuna depth current:"
cat data/physics/tuna_depth_current_today.json | jq '{
  version,
  snapshot_date,
  rank_score: .composite.candidate_rank_score_stats,
  hotspot: .composite.hotspot,
  ethical_note: .narrative.ethical_note
}' || true

log "PIPELINE COMPLETED"
