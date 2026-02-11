#!/usr/bin/env bash
set -euo pipefail

START="${1:-}"
END="${2:-}"
METRICS="${3:-sst,chlorophyll,current}"   # csv: "sst" atau "sst,current"

if [[ -z "$START" || -z "$END" ]]; then
  echo "Usage: $0 YYYY-MM-DD YYYY-MM-DD [metrics_csv]"
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs/time_series"
mkdir -p "${LOG_DIR}"

# ✅ Paksa pakai YAML yang sudah benar (boleh override: CFG=/path/to/file.yaml ./backfill_range.sh ...)
CFG="${CFG:-${ROOT_DIR}/config/time_series_aceh.yaml}"

LOG_FILE="${LOG_DIR}/backfill_${START}_to_${END}.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "[INFO] Backfill from ${START} to ${END}"
echo "[INFO] Using runner: ${ROOT_DIR}/scripts/time_series/run_one_day.sh"
echo "[INFO] Metrics: ${METRICS}"
echo "[INFO] Logs: ${LOG_DIR}"
echo "[INFO] CFG: ${CFG}"

DAY="${START}"
fail_count=0

while [[ "${DAY}" < "${END}" || "${DAY}" == "${END}" ]]; do
  echo "[RUN ] ${DAY}"

  set +e
  # ✅ Inject CFG ke runner (ini yang memperbaiki masalah .json)
  CFG="${CFG}" bash "${ROOT_DIR}/scripts/time_series/run_one_day.sh" "${DAY}" "${METRICS}"
  rc=$?
  set -e

  if [[ $rc -ne 0 ]]; then
    echo "[WARN] ${DAY} ada kegagalan (rc=${rc})"
    fail_count=$((fail_count+1))
  fi

  DAY="$(date -I -d "${DAY} + 1 day")"
done

echo "[INFO] Backfill done. fail_days=${fail_count}"
exit 0
