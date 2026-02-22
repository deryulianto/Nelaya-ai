#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${NELAYA_KIND:?missing NELAYA_KIND}"
: "${NELAYA_DAY:?missing NELAYA_DAY}"   # YYYY-MM-DD (UTC day)
: "${NELAYA_OUT:?missing NELAYA_OUT}"

# =========================
# Region box: Aceh–Simeulue
# =========================
MIN_LON=92
MAX_LON=99
MIN_LAT=1
MAX_LAT=7

# =========================
# Pick copernicusmarine bin
# Priority: venv -> mamba -> PATH
# =========================
COP="${COPERNICUSMARINE_BIN:-$ROOT/.venv/bin/copernicusmarine}"

if [[ -x "$HOME/.local/share/mamba/envs/cm/bin/copernicusmarine" ]]; then
  COP="$HOME/.local/share/mamba/envs/cm/bin/copernicusmarine"
fi

if [[ ! -x "$COP" ]]; then
  if command -v copernicusmarine >/dev/null 2>&1; then
    COP="$(command -v copernicusmarine)"
  fi
fi

if [[ ! -x "$COP" ]]; then
  echo "[ERROR] copernicusmarine not found. Checked:" >&2
  echo "  - $ROOT/.venv/bin/copernicusmarine" >&2
  echo "  - $HOME/.local/share/mamba/envs/cm/bin/copernicusmarine" >&2
  echo "  - PATH: \$(command -v copernicusmarine)" >&2
  exit 1
fi

echo "[INFO] Using copernicusmarine: $COP"
"$COP" --version || true

# =========================
# Time windows
# IMPORTANT: jangan start=end (bisa jadi empty result)
# Use full-day window in UTC by using [DAY 00:00 .. NEXTDAY 00:00)
# =========================
NEXT_DAY="$(date -u -d "${NELAYA_DAY} +1 day" +%F)"

# CHL NRT sering delay; mundurkan 2 hari agar tidak out-of-bounds
if [[ "$NELAYA_KIND" == "chl_nrt" ]]; then
  NELAYA_DAY="$(date -u -d "${NELAYA_DAY} -2 day" +%F)"
  NEXT_DAY="$(date -u -d "${NELAYA_DAY} +1 day" +%F)"
fi


P1D_START="${NELAYA_DAY}T00:00:00"
P1D_END="${NEXT_DAY}T00:00:00"

H_START="${NELAYA_DAY}T00:00:00"
H_END="${NEXT_DAY}T00:00:00"

# Surface depth (workaround biar konsisten & kecil)
DEPTH_SURF="0.49402499198913574"

dataset=""
time_start="$P1D_START"
time_end="$P1D_END"
depth_args=()
vars_try_sets=()

case "$NELAYA_KIND" in
  sst_nrt)
    dataset="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m"
    depth_args=(--minimum-depth "$DEPTH_SURF" --maximum-depth "$DEPTH_SURF")
    vars_try_sets=("thetao")
    ;;
  chl_nrt)
    dataset="cmems_obs-oc_glo_bgc-plankton_nrt_l3-multi-4km_P1D"
    vars_try_sets=("CHL" "chl")
    ;;
  wind_nrt)
    dataset="cmems_obs-wind_glo_phy_nrt_l3-metopc-ascat-des-0.25deg_P1D-i"
    vars_try_sets=("eastward_wind,northward_wind" "u10,v10" "uwnd,vwnd" "u,v" "wind_speed,wind_dir")
    ;;
  wave_anfc)
    dataset="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
    time_start="$H_START"; time_end="$H_END"
    vars_try_sets=("VHM0,VTPK,VMDR" "VHM0,VMDR" "VHM0")
    ;;
  ssh_anfc)
    dataset="cmems_mod_glo_phy_anfc_0.083deg_P1D-m"
    vars_try_sets=("zos" "adt" "sla")
    ;;
  sal_anfc)
    dataset="cmems_mod_glo_phy-so_anfc_0.083deg_P1D-m"
    depth_args=(--minimum-depth "$DEPTH_SURF" --maximum-depth "$DEPTH_SURF")
    vars_try_sets=("so")
    ;;
  *)
    echo "[ERR] unknown kind: $NELAYA_KIND" >&2
    exit 3
    ;;
esac

out_dir="$(dirname "$NELAYA_OUT")"
out_file="$(basename "$NELAYA_OUT")"
mkdir -p "$out_dir"

# =========================
# Run subset for a variable set
# =========================
run_subset () {
  local varcsv="$1"
  IFS=',' read -r -a VARS <<< "$varcsv"

  local -a args=(
    "$COP" subset
    --dataset-id "$dataset"
    --minimum-longitude "$MIN_LON" --maximum-longitude "$MAX_LON"
    --minimum-latitude "$MIN_LAT" --maximum-latitude "$MAX_LAT"
    --start-datetime "$time_start" --end-datetime "$time_end"
    --output-directory "$out_dir"
    --output-filename "$out_file"
  )

  if (( ${#depth_args[@]} > 0 )); then
    args+=("${depth_args[@]}")
  fi

  for v in "${VARS[@]}"; do
    [[ -n "$v" ]] && args+=( --variable "$v" )
  done

  echo "[CMD] ${args[*]}"
  "${args[@]}"
}

# =========================
# Try variable sets until one succeeds
# =========================
for varset in "${vars_try_sets[@]}"; do
  set +e
  run_subset "$varset"
  rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then
    # sanity check output exists & not tiny
    if [[ -f "$NELAYA_OUT" ]]; then
      sz="$(stat -c%s "$NELAYA_OUT" 2>/dev/null || echo 0)"
      echo "[INFO] output size: ${sz} bytes -> $NELAYA_OUT"
      if [[ "$sz" -ge 10000 ]]; then
        exit 0
      fi
      echo "[WARN] output too small (<10KB), treating as failure; deleting: $NELAYA_OUT"
      rm -f "$NELAYA_OUT" || true
    else
      echo "[WARN] subset returned 0 but output file missing: $NELAYA_OUT"
    fi
  fi
  echo "[WARN] subset failed rc=$rc with vars=$varset (trying next...)"
done

echo "[ERR] all variable sets failed for kind=$NELAYA_KIND dataset=$dataset" >&2
exit 10
