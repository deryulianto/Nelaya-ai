#!/usr/bin/env bash
set -euo pipefail

DAY="${1:-}"
METRICS=${METRICS:-sst,chlorophyll,current,temp3d,temp_profile}

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

# stabilkan native libs (hindari segfault random)
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export MALLOC_ARENA_MAX=2
ulimit -c 0 || true

# env python
PY_LOCAL="${ROOT_DIR}/.venv/bin/python"     # py3.12
PY_CM="${HOME}/.local/share/mamba/envs/cm/bin/python"  # py3.11

echo "[INFO] ROOT=${ROOT_DIR}"
echo "[INFO] DAY=${DAY}"
echo "[INFO] METRICS=${METRICS}"
echo "[INFO] LOG=${LOG_FILE}"
echo "[INFO] CFG=${CFG}"

IFS=',' read -r -a METRIC_ARR <<< "${METRICS}"

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

run_fetch() {
  local metric="$1"
  echo "  [RUN] fetch (cm)"

  if [[ "${metric}" == "temp3d" ]]; then
    PYTHONFAULTHANDLER=1 "${PY_CM}" -X faulthandler \
      "${ROOT_DIR}/scripts/time_series/01_fetch_daily_temp3D.py" --config "${CFG}" --var "temp3d" --date "${DAY}"
    return $?
  fi

  PYTHONFAULTHANDLER=1 "${PY_CM}" -X faulthandler \
    "${ROOT_DIR}/scripts/time_series/01_fetch_daily.py" --config "${CFG}" --var "${metric}" --date "${DAY}"
  rc=$?

  if [[ "${metric}" == "current" && $rc -eq 139 ]]; then
    echo "  [WARN] fetch current segfault rc=139 → retry sekali setelah 10s"
    sleep 10
    PYTHONFAULTHANDLER=1 "${PY_CM}" -X faulthandler \
      "${ROOT_DIR}/scripts/time_series/01_fetch_daily.py" --config "${CFG}" --var "${metric}" --date "${DAY}"
    return $?
  fi
  return $rc
}

run_temp_profile() {
  echo "  [RUN] derive temp_profile from temp3d (cm)"
  "${PY_CM}" "${ROOT_DIR}/scripts/time_series/04_make_temp_profile.py" \
    --config "${CFG}" --date "${DAY}" --var3d "temp3d" --max-depth 200 --step 10
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

    # ===== SPECIAL CASES =====
  if [[ "${metric}" == "temp3d" ]]; then
    set +e
    run_fetch "temp3d"
    rc=$?
    set -e
    if [[ $rc -ne 0 ]]; then
      echo "  [FAIL] fetch rc=${rc} metric=temp3d day=${DAY}"
      any_fail=1
      continue
    fi
    echo "  [OK] temp3d ${DAY} (fetch only)"
    continue
  fi

  if [[ "${metric}" == "temp_profile" ]]; then
    # pastikan temp3d raw ada (kalau belum, fetch dulu)
    base_dir="${ROOT_DIR}/data/time_series/aceh/banda_aceh_aceh_besar"
    nc="${base_dir}/temp3d/raw/temp3d_raw_${DAY}.nc"
    if [[ ! -f "${nc}" ]]; then
      echo "  [INFO] temp3d raw belum ada → fetch temp3d dulu"
      set +e
      run_fetch "temp3d"
      rc=$?
      set -e
      if [[ $rc -ne 0 ]]; then
        echo "  [FAIL] fetch rc=${rc} metric=temp3d (needed by temp_profile) day=${DAY}"
        any_fail=1
        continue
      fi
    fi

    set +e
    run_temp_profile
    rc=$?
    set -e
    if [[ $rc -ne 0 ]]; then
      echo "  [FAIL] derive temp_profile rc=${rc} day=${DAY}"
      any_fail=1
      continue
    fi
    echo "  [OK] temp_profile ${DAY} (derived)"
    continue
  fi

  # ===== DEFAULT FLOW (grid metrics) =====
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

