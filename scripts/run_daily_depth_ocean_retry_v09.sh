#!/usr/bin/env bash
set -u

ROOT="/home/coastalai/NELAYA-AI-LAB"
PY="$ROOT/.venv/bin/python"
LOG_DIR="$ROOT/logs"

export PATH="$ROOT/.venv/bin:/home/coastalai/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

mkdir -p "$LOG_DIR"
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

echo "NELAYA-AI Depth Ocean Retry Pipeline v0.9"
echo "Run at: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "copernicusmarine: $(which copernicusmarine || echo NOT_FOUND)"

run_step "Download current multi-depth NRT 0-120 m" \
  "$PY" scripts/download_current_depth_nrt_copernicus.py --days-back 7 --max-depth 120

run_step "Build tuna depth current analysis" \
  "$PY" scripts/build_tuna_depth_current_analysis.py --geojson-threshold 0.90 --max-points 150

run_step "Build NS-informed ocean diagnostics v0.8-alpha" \
  "$PY" scripts/build_ns_ocean_diagnostics_v08.py --geojson-threshold 0.70 --max-points 200

run_step "Build integrated ocean decision v0.9-alpha" \
  "$PY" scripts/build_integrated_ocean_decision_v09.py

log "FINAL CHECK"

echo "Tuna depth:"
cat data/physics/tuna_depth_current_today.json | jq '{
  version,
  snapshot_date,
  hotspot: .composite.hotspot
}' || true

echo "NS diagnostics:"
cat data/physics/ns_ocean_diagnostics_today.json | jq '{
  version,
  snapshot_date,
  hotspot: .aggregate.hotspot
}' || true

echo "Integrated decision:"
cat data/decision/integrated_ocean_decision_today.json | jq '{
  version,
  snapshot_date,
  confidence,
  decision: .integrated_decision
}' || true

log "DEPTH RETRY PIPELINE COMPLETED"
