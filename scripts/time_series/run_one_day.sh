#!/usr/bin/env bash
set -euo pipefail

DAY="${1:-}"
METRICS="${2:-sst,chlorophyll,current}"

if [[ -z "${DAY}" ]]; then
  echo "Usage: $0 YYYY-MM-DD [metrics_csv]"
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs/time_series"
mkdir -p "${LOG_DIR}"

LOG_FILE="${LOG_DIR}/run_${DAY}.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

CFG="${ROOT_DIR}/config/time_series_aceh.yaml"

# env python
PY_LOCAL="${ROOT_DIR}/.venv/bin/python"     # py3.12
PY_CM="${HOME}/.local/share/mamba/envs/cm/bin/python"  # py3.11

echo "[INFO] ROOT=${ROOT_DIR}"
echo "[INFO] DAY=${DAY}"
echo "[INFO] METRICS=${METRICS}"
echo "[INFO] LOG=${LOG_FILE}"
echo "[INFO] CFG=${CFG}"

IFS=',' read -r -a METRIC_ARR <<< "${METRICS}"

run_fetch() {
  local metric="$1"
  # fetch selalu pakai cm (stabil)
  echo "  [RUN] fetch (cm)"
  "${PY_CM}" "${ROOT_DIR}/scripts/time_series/01_fetch_daily.py" --config "${CFG}" --var "${metric}" --date "${DAY}"
}

run_export() {
  local metric="$1"

  # export default pakai local, tapi chlorophyll sering segv → fallback ke cm
  if [[ "${metric}" == "chlorophyll" ]]; then
    echo "  [RUN] export (local, then fallback cm if fail)"
    set +e
    "${PY_LOCAL}" "${ROOT_DIR}/scripts/time_series/02_export_csv_grid.py" --config "${CFG}" --var "${metric}" --date "${DAY}"
    rc=$?
    set -e
    if [[ $rc -ne 0 ]]; then
      echo "  [WARN] export local gagal rc=${rc} untuk ${metric} ${DAY} → coba export (cm)"
      "${PY_CM}" "${ROOT_DIR}/scripts/time_series/02_export_csv_grid.py" --config "${CFG}" --var "${metric}" --date "${DAY}"
    fi
    return
  fi

  echo "  [RUN] export (local)"
  "${PY_LOCAL}" "${ROOT_DIR}/scripts/time_series/02_export_csv_grid.py" --config "${CFG}" --var "${metric}" --date "${DAY}"
}

run_update() {
  local metric="$1"

  # update juga: chlorophyll → pakai cm biar konsisten (hindari crash pandas/pyarrow py3.12)
  if [[ "${metric}" == "chlorophyll" ]]; then
    echo "  [RUN] update (cm)"
    "${PY_CM}" "${ROOT_DIR}/scripts/time_series/03_update_series_mean.py" --config "${CFG}" --var "${metric}" --date "${DAY}"
    return
  fi

  echo "  [RUN] update (local)"
  "${PY_LOCAL}" "${ROOT_DIR}/scripts/time_series/03_update_series_mean.py" --config "${CFG}" --var "${metric}" --date "${DAY}"
}

any_fail=0

for metric in "${METRIC_ARR[@]}"; do
  metric="$(echo "$metric" | xargs)"
  [[ -z "${metric}" ]] && continue

  echo "[METRIC] ${metric} @ ${DAY}"

  # fetch
  set +e
  run_fetch "${metric}"
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    echo "  [FAIL] fetch rc=${rc} metric=${metric} day=${DAY}"
    any_fail=1
    continue
  fi

  # export
  set +e
  run_export "${metric}"
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    echo "  [FAIL] export rc=${rc} metric=${metric} day=${DAY}"
    any_fail=1
    continue
  fi

  # update
  set +e
  run_update "${metric}"
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    echo "  [FAIL] update rc=${rc} metric=${metric} day=${DAY}"
    any_fail=1
    continue
  fi

  echo "  [OK] ${metric} ${DAY}"
done

if [[ $any_fail -eq 0 ]]; then
  echo "[DONE] ${DAY} sukses semua metric."
  exit 0
else
  echo "[DONE] ${DAY} selesai, ada metric yang gagal (lihat log)."
  exit 1
fi
