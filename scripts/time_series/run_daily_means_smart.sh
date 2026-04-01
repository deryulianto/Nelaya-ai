#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

DAY_WIB="${1:-$(TZ=Asia/Jakarta date +%F)}"

echo "[INFO] ROOT=${ROOT_DIR}"
echo "[INFO] DAY_WIB=${DAY_WIB}"
echo

date_minus() {
  local d="$1"
  local n="$2"
  date -u -d "${d} -${n} day" +%F
}

latest_date_from_series() {
  local csv="$1"
  if [[ ! -f "$csv" ]]; then
    echo ""
    return 0
  fi
  tail -n 1 "$csv" | cut -d',' -f1
}

run_metric_for_day() {
  local metric="$1"
  local day="$2"

  echo "[INFO] metric=${metric} day=${day}"
  METRICS="${metric}" bash ./scripts/time_series/run_one_day.sh "${day}" || true
}

try_metric_with_fallback() {
  local metric="$1"
  local csv="$2"
  shift 2
  local -a try_days=("$@")

  for d in "${try_days[@]}"; do
    run_metric_for_day "${metric}" "${d}"

    local latest
    latest="$(latest_date_from_series "${csv}")"

    if [[ "${latest}" == "${d}" ]]; then
      echo "[OK] ${metric} berhasil memakai tanggal ${d}"
      return 0
    fi

    echo "[WARN] ${metric} belum berhasil untuk ${d}; latest series masih ${latest:-<kosong>}"
    echo
  done

  echo "[WARN] ${metric} tidak berhasil pada semua kandidat tanggal: ${try_days[*]}"
  return 1
}

SST_CSV="data/time_series/aceh/banda_aceh_aceh_besar/sst/series/sst_daily_mean.csv"
CHL_CSV="data/time_series/aceh/banda_aceh_aceh_besar/chlorophyll/series/chlorophyll_daily_mean.csv"
CUR_CSV="data/time_series/aceh/banda_aceh_aceh_besar/current/series/current_daily_mean.csv"

DAY_0="${DAY_WIB}"
DAY_1="$(date_minus "${DAY_WIB}" 1)"
DAY_2="$(date_minus "${DAY_WIB}" 2)"
DAY_3="$(date_minus "${DAY_WIB}" 3)"

echo "[INFO] Kandidat tanggal:"
echo "  DAY_0=${DAY_0}"
echo "  DAY_1=${DAY_1}"
echo "  DAY_2=${DAY_2}"
echo "  DAY_3=${DAY_3}"
echo

# SST dan current idealnya tembus hari ini
try_metric_with_fallback "sst" "${SST_CSV}" "${DAY_0}" "${DAY_1}" "${DAY_2}" || true
echo
try_metric_with_fallback "current" "${CUR_CSV}" "${DAY_0}" "${DAY_1}" "${DAY_2}" || true
echo

# Chlorophyll biasanya lag lebih besar; kasih fallback lebih panjang
try_metric_with_fallback "chlorophyll" "${CHL_CSV}" "${DAY_0}" "${DAY_1}" "${DAY_2}" "${DAY_3}" || true
echo

echo "=== latest rows: sst ==="
tail -n 7 "${SST_CSV}" || true

echo
echo "=== latest rows: chlorophyll ==="
tail -n 7 "${CHL_CSV}" || true

echo
echo "=== latest rows: current ==="
tail -n 7 "${CUR_CSV}" || true

echo
echo "[INFO] Latest dates actually used:"
echo "  sst         : $(latest_date_from_series "${SST_CSV}")"
echo "  chlorophyll : $(latest_date_from_series "${CHL_CSV}")"
echo "  current     : $(latest_date_from_series "${CUR_CSV}")"
