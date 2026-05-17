#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

DATE_ARG="${1:-}"

echo "=================================================="
echo " NELAYA-AI LFI Alpha Full Daily Runner"
echo "=================================================="

if [[ -n "$DATE_ARG" ]]; then
  echo "Tanggal diminta: $DATE_ARG"
  BUILD_DATE_ARGS=(--date "$DATE_ARG")
else
  echo "Tidak ada tanggal diberikan. Memakai file current_nrt terbaru."
  BUILD_DATE_ARGS=()
fi

echo
echo "1) Build LFI Alpha JSON + GeoJSON"
python scripts/build_lagrangian_front_alpha.py "${BUILD_DATE_ARGS[@]}"

echo
echo "2) Plot LFI Alpha PNG"
python scripts/plot_lagrangian_front_alpha.py "${BUILD_DATE_ARGS[@]}"

echo
echo "3) Integrate LFI into earth_signals_today.json"
python scripts/integrate_lfi_to_earth_signals.py

echo
echo "4) Output files"
ls -lh \
  data/physics/lagrangian_front_today.json \
  data/physics/lagrangian_front_today.geojson \
  data/physics/lagrangian_front_today.png \
  data/earth/earth_signals_today.json

echo
echo "5) LFI Summary"
cat data/physics/lagrangian_front_today.json | jq '{
  version,
  date,
  method,
  summary,
  first_zone: .top_zones[0]
}'

echo
echo "6) FGI Lagrangian-aware Summary"
cat data/earth/earth_signals_today.json | jq '.metrics | {
  fgi_value: .fgi.value,
  fgi_current_aware: .fgi_current_aware.value,
  lfi_alpha: .lfi_alpha.value,
  fgi_lagrangian_aware: .fgi_lagrangian_aware.value,
  fgi_lagrangian_band: .fgi_lagrangian_aware.band,
  hotspot_shadow_value: .fgi_lagrangian_aware.inputs.hotspot_shadow_value
}'

echo
echo "=================================================="
echo " LFI full daily runner completed."
echo "=================================================="
