#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

DATE_ARG="${1:-}"

echo "=== NELAYA-AI LFI Alpha daily runner ==="

if [[ -n "$DATE_ARG" ]]; then
  echo "Using requested date: $DATE_ARG"
  python scripts/build_lagrangian_front_alpha.py --date "$DATE_ARG"
else
  echo "No date argument provided. Using latest available current_nrt file."
  python scripts/build_lagrangian_front_alpha.py
fi

echo
echo "=== Integrating LFI into earth_signals_today.json ==="
python scripts/integrate_lfi_to_earth_signals.py

echo
echo "=== LFI Summary ==="
cat data/physics/lagrangian_front_today.json | jq '{
  version,
  date,
  summary,
  first_zone: .top_zones[0]
}'

echo
echo "=== FGI Lagrangian-aware Summary ==="
cat data/earth/earth_signals_today.json | jq '.metrics | {
  fgi,
  fgi_current_aware,
  lfi_alpha,
  fgi_lagrangian_aware
}'

echo
echo "Done."
