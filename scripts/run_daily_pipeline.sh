#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-publish}"

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

if [[ -f "$APP_DIR/.env.systemd" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$APP_DIR/.env.systemd"
  set +a
fi

PIPELINE_TZ="${PIPELINE_TZ:-Asia/Jakarta}"
TARGET_DAY="${TARGET_DAY:-$(TZ="$PIPELINE_TZ" date +%F)}"

PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/.venv/bin/python}"
CMEMS_HELPER="${CMEMS_HELPER:-$APP_DIR/scripts/_cmems_download_one.sh}"
LOG_DIR="${LOG_DIR:-$APP_DIR/logs/pipeline}"
RAW_BASE_DIR="${RAW_BASE_DIR:-$APP_DIR/data/raw/aceh_simeulue}"
PRODUCTS_STR="${PRODUCTS:-sst_nrt chl_nrt wind_nrt wave_anfc ssh_anfc sal_anfc}"
read -r -a PRODUCTS <<< "$PRODUCTS_STR"

SURF_BUILD_CMD="${SURF_BUILD_CMD:-}"
INSIGHT_BUILD_CMD="${INSIGHT_BUILD_CMD:-}"

mkdir -p "$LOG_DIR"

RUN_TS="$(date '+%Y-%m-%dT%H-%M-%S%z')"
LOG_FILE="$LOG_DIR/${MODE}_${RUN_TS}.log"

exec > >(tee -a "$LOG_FILE") 2>&1

FAILED=0

log() {
  echo "[$(date '+%F %T %Z')] $*"
}

build_output_path() {
  local product="$1"
  local y="${TARGET_DAY:0:4}"
  local m="${TARGET_DAY:5:2}"
  local out_dir="$RAW_BASE_DIR/$product/$y/$m"
  local filename=""

  mkdir -p "$out_dir"

  case "$product" in
    sst_nrt)
      filename="sst_nrt_aceh_${TARGET_DAY}.nc"
      ;;
    chl_nrt)
      filename="chl_nrt_aceh_${TARGET_DAY}.nc"
      ;;
    wind_nrt)
      filename="wind_nrt_aceh_${TARGET_DAY}.nc"
      ;;
    wave_anfc)
      filename="wave_aceh_${TARGET_DAY}.nc"
      ;;
    ssh_anfc)
      filename="ssh_aceh_${TARGET_DAY}.nc"
      ;;
    sal_anfc)
      filename="sal_aceh_${TARGET_DAY}.nc"
      ;;
    *)
      filename="${product}_aceh_${TARGET_DAY}.nc"
      ;;
  esac

  printf '%s/%s\n' "$out_dir" "$filename"
}

run_one_product() {
  local product="$1"
  local out_path=""

  if [[ ! -x "$CMEMS_HELPER" ]]; then
    log "WARN: helper tidak ditemukan / tidak executable: $CMEMS_HELPER"
    FAILED=1
    return 0
  fi

  out_path="$(build_output_path "$product")"

  log "==> cek/download product: $product untuk day=$TARGET_DAY -> $out_path"
  if ! env \
    NELAYA_KIND="$product" \
    NELAYA_DAY="$TARGET_DAY" \
    NELAYA_OUT="$out_path" \
    bash "$CMEMS_HELPER"; then
    log "WARN: gagal pada product: $product"
    FAILED=1
  fi
}

run_downloads() {
  local product=""
  for product in "${PRODUCTS[@]}"; do
    run_one_product "$product"
  done
}

build_freshness_ledger() {
  local script="$APP_DIR/scripts/build_freshness_ledger.py"
  if [[ -f "$script" ]]; then
    log "==> build freshness ledger"
    if ! "$PYTHON_BIN" "$script"; then
      log "WARN: build freshness ledger gagal"
      FAILED=1
    fi
  else
    log "WARN: script freshness ledger tidak ditemukan: $script"
    FAILED=1
  fi
}

build_earth_signals() {
  local script="$APP_DIR/scripts/build_earth_signals_from_raw.py"
  if [[ -f "$script" ]]; then
    log "==> build earth signals"
    if ! "$PYTHON_BIN" "$script"; then
      log "WARN: build earth signals gagal"
      FAILED=1
    fi
  else
    log "WARN: script earth signals tidak ditemukan: $script"
    FAILED=1
  fi
}

mirror_earth_snapshot() {
  local src="$APP_DIR/data/earth/earth_signals_today.json"
  local dst="$APP_DIR/data/earth_signals_today.json"

  if [[ -f "$src" ]]; then
    cp "$src" "$dst"
    log "==> mirrored earth snapshot: $src -> $dst"
  else
    log "WARN: earth snapshot source tidak ditemukan: $src"
    FAILED=1
  fi
}

run_optional_cmd() {
  local name="$1"
  local cmd="$2"

  if [[ -z "$cmd" ]]; then
    log "==> skip optional step: $name (kosong)"
    return 0
  fi

  log "==> run optional step: $name"
  if ! bash -lc "$cmd"; then
    log "WARN: optional step gagal: $name"
    FAILED=1
  fi
}

case "$MODE" in
  probe)
    log "MODE=probe"
    run_downloads
    build_freshness_ledger
    ;;
  publish)
    log "MODE=publish"
    run_downloads
    build_freshness_ledger
    build_earth_signals
    mirror_earth_snapshot
    run_optional_cmd "surf" "$SURF_BUILD_CMD"
    run_optional_cmd "insight" "$INSIGHT_BUILD_CMD"
    ;;
  reconcile)
    log "MODE=reconcile"
    run_downloads
    build_freshness_ledger
    build_earth_signals
    mirror_earth_snapshot
    run_optional_cmd "surf" "$SURF_BUILD_CMD"
    run_optional_cmd "insight" "$INSIGHT_BUILD_CMD"
    ;;
  *)
    echo "Usage: $0 {probe|publish|reconcile}"
    exit 64
    ;;
esac

if [[ "$FAILED" -ne 0 ]]; then
  log "SELESAI dengan WARNING/ERROR"
  exit 1
fi

log "SELESAI sukses"
exit 0