#!/usr/bin/env bash
set -Eeuo pipefail

# =============================================================================
# NELAYA-AI Daily Physics-informed FGI Pipeline
# Version: 0.6.2
#
# Purpose:
#   Build daily Physics-informed FGI Support from:
#   - Bathymetry static layer
#   - Dynamic ocean physics layer
#   - FGI physics support fusion layer
#
# Outputs:
#   data/physics/bathymetry_features_aceh.nc
#   data/physics/bathymetry_features_summary.json
#   data/physics/bathymetry_shelfbreak_preview.geojson
#
#   data/physics/dynamic_inputs_report.json
#   data/physics/ocean_dynamic_physics_today.nc
#   data/physics/ocean_dynamic_physics_today.json
#   data/physics/ocean_dynamic_front_preview.geojson
#
#   data/physics/fgi_physics_support_today.nc
#   data/physics/fgi_physics_support_today.json
#   data/physics/fgi_physics_support_preview.geojson
# =============================================================================

ROOT_DIR="${NELAYA_AI_LAB_ROOT:-$HOME/NELAYA-AI-LAB}"
cd "$ROOT_DIR"

# -----------------------------------------------------------------------------
# Safe native-library settings for xarray/netCDF/HDF5/NumPy
# -----------------------------------------------------------------------------
export HDF5_USE_FILE_LOCKING="${HDF5_USE_FILE_LOCKING:-FALSE}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_MAX_THREADS="${NUMEXPR_MAX_THREADS:-1}"

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
SPECIES_GROUP="${SPECIES_GROUP:-medium_pelagic}"
BATHY_THRESHOLD="${BATHY_THRESHOLD:-0.50}"
FRONT_THRESHOLD="${FRONT_THRESHOLD:-0.50}"
FGI_PHYSICS_THRESHOLD="${FGI_PHYSICS_THRESHOLD:-0.22}"

LOG_DIR="$ROOT_DIR/logs/physics_fgi"
mkdir -p "$LOG_DIR"

RUN_TS="$(date '+%Y%m%d_%H%M%S')"
LOG_FILE="$LOG_DIR/run_daily_physics_fgi_${RUN_TS}.log"

PHYSICS_DIR="$ROOT_DIR/data/physics"
BATHY_FEATURES="$PHYSICS_DIR/bathymetry_features_aceh.nc"
BATHY_SUMMARY="$PHYSICS_DIR/bathymetry_features_summary.json"
DYNAMIC_JSON="$PHYSICS_DIR/ocean_dynamic_physics_today.json"
FGI_JSON="$PHYSICS_DIR/fgi_physics_support_today.json"
FGI_GEOJSON="$PHYSICS_DIR/fgi_physics_support_preview.geojson"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

run_step() {
  local title="$1"
  shift

  log "======================================================================"
  log "STEP: $title"
  log "CMD : $*"
  log "======================================================================"

  "$@"

  log "DONE: $title"
}

json_check() {
  local file="$1"
  local label="$2"

  if [[ ! -f "$file" ]]; then
    log "ERROR: Missing $label file: $file"
    exit 1
  fi

  python - <<PY
import json
from pathlib import Path

p = Path("$file")
try:
    json.loads(p.read_text())
    print("JSON OK:", p)
except Exception as e:
    raise SystemExit(f"JSON invalid: {p} :: {e}")
PY
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
{
  log "NELAYA-AI Daily Physics-informed FGI Pipeline v0.6.2"
  log "ROOT_DIR              : $ROOT_DIR"
  log "SPECIES_GROUP         : $SPECIES_GROUP"
  log "BATHY_THRESHOLD       : $BATHY_THRESHOLD"
  log "FRONT_THRESHOLD       : $FRONT_THRESHOLD"
  log "FGI_PHYSICS_THRESHOLD : $FGI_PHYSICS_THRESHOLD"
  log "LOG_FILE              : $LOG_FILE"

  if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
    log "Virtualenv activated: .venv"
  else
    log "WARNING: .venv not found. Continuing with current Python environment."
  fi

  python --version

  # ---------------------------------------------------------------------------
  # 1. Bathymetry static layer
  # ---------------------------------------------------------------------------
  # Bathymetry is static. We rebuild when file is missing.
  # To force rebuild: FORCE_BATHY=1 scripts/run_daily_physics_fgi_pipeline.sh
  if [[ "${FORCE_BATHY:-0}" == "1" || ! -f "$BATHY_FEATURES" || ! -f "$BATHY_SUMMARY" ]]; then
    run_step "Build bathymetry physics features" \
      python scripts/build_bathymetry_physics_features.py \
        --engine scipy \
        --geojson-threshold "$BATHY_THRESHOLD"
  else
    log "SKIP: Bathymetry physics features already exist."
    log "      Use FORCE_BATHY=1 to rebuild."
  fi

  json_check "$BATHY_SUMMARY" "bathymetry summary"

  # ---------------------------------------------------------------------------
  # 2. Inspect dynamic inputs
  # ---------------------------------------------------------------------------
  run_step "Inspect latest dynamic physics inputs" \
    python scripts/inspect_dynamic_physics_inputs.py

  json_check "$PHYSICS_DIR/dynamic_inputs_report.json" "dynamic input report"

  log "Dynamic readiness:"
  cat "$PHYSICS_DIR/dynamic_inputs_report.json" | jq '.readiness' || true

  READY="$(cat "$PHYSICS_DIR/dynamic_inputs_report.json" | jq -r '.readiness.ready_for_dynamic_physics_v01')"
  if [[ "$READY" != "true" ]]; then
    log "ERROR: Dynamic inputs are not ready for physics v0.1."
    log "Latest files:"
    cat "$PHYSICS_DIR/dynamic_inputs_report.json" | jq '.latest_files' || true
    exit 1
  fi

  # ---------------------------------------------------------------------------
  # 3. Build ocean dynamic physics layer
  # ---------------------------------------------------------------------------
  run_step "Build ocean dynamic physics layer" \
    python scripts/build_ocean_dynamic_physics_features.py \
      --front-threshold "$FRONT_THRESHOLD"

  json_check "$DYNAMIC_JSON" "ocean dynamic physics summary"

  log "Dynamic physics summary:"
  cat "$DYNAMIC_JSON" | jq '.summary_metrics' || true
  cat "$DYNAMIC_JSON" | jq '.outputs.front_geojson' || true

  # ---------------------------------------------------------------------------
  # 4. Build Physics-informed FGI Support v0.6.2
  # ---------------------------------------------------------------------------
  run_step "Build FGI Physics Support v0.6.2" \
    python scripts/build_physics_informed_fgi_v06.py \
      --species-group "$SPECIES_GROUP" \
      --threshold "$FGI_PHYSICS_THRESHOLD"

  json_check "$FGI_JSON" "FGI physics support summary"
  json_check "$FGI_GEOJSON" "FGI physics support GeoJSON"

  log "FGI Physics Support summary:"
  cat "$FGI_JSON" | jq '.status, .version, .species_group, .summary_metrics' || true

  log "Top 5 FGI Physics Support cells:"
  cat "$FGI_JSON" | jq '.top_cells.fgi_physics_support_confidence_adjusted[0:5]' || true

  log "GeoJSON output:"
  cat "$FGI_JSON" | jq '.outputs.geojson' || true

  # ---------------------------------------------------------------------------
  # 4b. Archive daily output for temporal memory
  # ---------------------------------------------------------------------------
  run_step "Archive daily physics outputs" \
    python scripts/archive_daily_physics_outputs.py --overwrite

  json_check "$PHYSICS_DIR/history/index.json" "physics history index"

  log "History index:"
  cat "$PHYSICS_DIR/history/index.json" | jq '.count, .entries[-1]' || true

  # ---------------------------------------------------------------------------
  # 4c. Build FGI Temporal Memory v0.7-alpha
  # ---------------------------------------------------------------------------
  run_step "Build FGI temporal memory v0.7-alpha" \
    python scripts/build_fgi_temporal_memory.py \
      --window-days 5 \
      --active-threshold "$FGI_PHYSICS_THRESHOLD" \
      --geojson-threshold 0.25

  json_check "$PHYSICS_DIR/fgi_temporal_memory_today.json" "FGI temporal memory summary"
  json_check "$PHYSICS_DIR/fgi_temporal_memory_preview.geojson" "FGI temporal memory GeoJSON"

  log "Temporal memory summary:"
  cat "$PHYSICS_DIR/fgi_temporal_memory_today.json" | jq '.summary_metrics, .movement_consistency, .outputs.geojson' || true


  # ---------------------------------------------------------------------------
  # 5. API health check when backend is running locally
  # ---------------------------------------------------------------------------
  if curl -s --max-time 3 "http://127.0.0.1:8001/health" >/dev/null 2>&1; then
    log "Backend detected on 127.0.0.1:8001. Checking physics-support API..."

    curl -s "http://127.0.0.1:8001/api/v1/fgi/physics-support/health" | jq || true
    curl -s "http://127.0.0.1:8001/api/v1/fgi/physics-support/summary" | jq '.status, .summary_metrics, .best_cell' || true
  else
    log "Backend local API not running. Skipping curl health check."
  fi

  log "======================================================================"
  log "PIPELINE SUCCESS"
  log "FGI Physics Support v0.6.2 is ready."
  log "Summary : $FGI_JSON"
  log "GeoJSON : $FGI_GEOJSON"
  log "Log     : $LOG_FILE"
  log "======================================================================"

} 2>&1 | tee "$LOG_FILE"
