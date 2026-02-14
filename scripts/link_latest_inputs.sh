#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BASE="data/raw/aceh_simeulue"
kinds=("sst_nrt" "chl_nrt" "wind_nrt" "wave_anfc" "ssh_anfc" "sal_anfc")

mkdir -p "$BASE/latest"

for k in "${kinds[@]}"; do
  latest_file="$(find "$BASE/$k" -type f -name "*.nc" -printf "%T@ %p\n" 2>/dev/null | sort -nr | head -n 1 | awk '{print $2}')"
  if [ -n "${latest_file:-}" ]; then
    out="$BASE/latest/${k}.nc"
    cp -f "$latest_file" "$out"
    echo "OK: $k -> $out (from $(basename "$latest_file"))"
  else
    echo "WARN: no files for $k"
  fi
done
