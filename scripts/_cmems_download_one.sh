#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

: "${NELAYA_KIND:?missing NELAYA_KIND}"
: "${NELAYA_DAY:?missing NELAYA_DAY}"
: "${NELAYA_OUT:?missing NELAYA_OUT}"

# Area Aceh box
MIN_LON=92
MAX_LON=99
MIN_LAT=1
MAX_LAT=7

# Pakai copernicusmarine dari venv kalau ada
COP="/.local/share/mamba/envs/cm/bin/copernicusmarine"
if [[ ! -x "" ]]; then
  COP="/.venv/bin/copernicusmarine"
fi
if [[ ! -x "" ]]; then
  COP="1000 4 20 24 25 27 29 30 44 46 100 107 985 986 993 1000command -v copernicusmarine)"
fi

# Waktu: untuk produk P1D biasanya timestamp 00:00:00
P1D_START="${NELAYA_DAY}T00:00:00"
P1D_END="${NELAYA_DAY}T00:00:00"

# Untuk produk sub-harian (contoh wave PT3H) ambil 1 hari penuh
H_START="${NELAYA_DAY}T00:00:00"
H_END="${NELAYA_DAY}T23:59:59"

# Surface depth workaround (biar file kecil & konsisten dgn time-series kamu)
DEPTH_SURF="0.49402499198913574"

dataset=""
time_start="$P1D_START"
time_end="$P1D_END"
depth_args=()
vars_try_sets=()

case "$NELAYA_KIND" in
  sst_nrt)
    # Layer thetao (analysis/forecast), sesuai pola CMEMS
    dataset="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m"
    depth_args=(--minimum-depth "$DEPTH_SURF" --maximum-depth "$DEPTH_SURF")
    vars_try_sets=("thetao")
    ;;
  chl_nrt)
    # Ocean color chlorophyll; variabel sering "CHL"
    dataset="cmems_obs-oc_glo_bgc-plankton_nrt_l3-multi-4km_P1D"
    vars_try_sets=("CHL" "chl")
    ;;
  wind_nrt)
    # Wind L3 NRT (pilih salah satu dataset daily 0.25deg). Kalau mau ganti dataset lain: lihat list di halaman produk.
    dataset="cmems_obs-wind_glo_phy_nrt_l3-metopc-ascat-des-0.25deg_P1D-i"
    # Coba beberapa kemungkinan nama variabel (biar nggak nebak doang)
    vars_try_sets=("eastward_wind,northward_wind" "u10,v10" "uwnd,vwnd" "u,v" "wind_speed,wind_dir")
    ;;
  wave_anfc)
    dataset="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
    time_start="$H_START"; time_end="$H_END"
    vars_try_sets=("VHM0,VTPK,VMDR" "VHM0,VMDR" "VHM0")
    ;;
  ssh_anfc)
    # Sea surface height: coba dulu di layer multi-var anfc
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

# coba beberapa set variabel sampai ada yang tembus
if [[ "${#vars_try_sets[@]}" -eq 1 && "${vars_try_sets[0]}" != *","* ]]; then
  # single variable (tanpa CSV)
  run_subset "${vars_try_sets[0]}"
else
  for varset in "${vars_try_sets[@]}"; do
    set +e
    run_subset "$varset"
    rc=$?
    set -e
    if [[ $rc -eq 0 ]]; then
      exit 0
    fi
    echo "[WARN] subset failed rc=$rc with vars=$varset (trying next...)"
  done
  echo "[ERR] all variable sets failed for kind=$NELAYA_KIND dataset=$dataset" >&2
  exit 10
fi
