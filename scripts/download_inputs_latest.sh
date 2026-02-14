#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== NELAYA INPUTS: download latest available (UTC) ==="

PY="$ROOT/.venv/bin/python"
COP="$ROOT/.venv/bin/copernicusmarine"

if [ ! -x "$COP" ]; then
  echo "[ERROR] copernicusmarine not found: $COP"
  exit 1
fi

echo "[INFO] Using copernicusmarine: $COP"

# UTC date for directory naming (file date bisa beda karena fallback, tapi cukup konsisten untuk storage)
Y="$(date -u +%Y)"
M="$(date -u +%m)"
D="$(date -u +%F)"

# Base output dirs
BASE="data/raw/aceh_simeulue"
mkdir -p "$BASE"

# stamp run supaya kelihatan service benar-benar jalan (walau cache HIT)
STAMP="$BASE/_last_download_run.txt"
{
  echo "run_wib=$(TZ=Asia/Jakarta date -Is)"
  echo "run_utc=$(date -u -Is)"
  echo "host=$(hostname)"
  echo "user=$(whoami)"
} > "$STAMP"


run_one () {
  local kind="$1"
  echo
  echo "---- $kind ----"
  "$PY" scripts/download_latest_available.py --kind "$kind" --max-back 10 || true
}


# NRT (sering telat 1–2 hari)
run_one "sst_nrt"  
run_one "chl_nrt"  
run_one "wind_nrt" 

# ANFC (biasanya lebih dekat, tapi tetap fallback)
run_one "wave_anfc" 
run_one "ssh_anfc"  
run_one "sal_anfc"  

echo
echo "[DONE] all downloads attempted."

# build + refresh signals for dashboard
python scripts/build_earth_signals_from_raw.py || true
python scripts/update_signals_today.py || true
