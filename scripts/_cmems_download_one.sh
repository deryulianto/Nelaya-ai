#!/usr/bin/env bash
set -euo pipefail

: "${NELAYA_KIND:?missing NELAYA_KIND}"
: "${NELAYA_DAY:?missing NELAYA_DAY}"
: "${NELAYA_OUT:?missing NELAYA_OUT}"

# Area Aceh box (sesuaikan kalau perlu)
MIN_LON=92
MAX_LON=99
MIN_LAT=1
MAX_LAT=7

COP="copernicusmarine"

# Start/end UTC satu hari (00:00 to 23:59:59)
START="${NELAYA_DAY}T00:00:00Z"
END="${NELAYA_DAY}T23:59:59Z"

# Pilih dataset + variables per kind
case "$NELAYA_KIND" in
  sst_nrt)
    DATASET="GLOBAL_ANALYSISFORECAST_PHY_001_024"  # contoh; sesuaikan dengan yang kamu pakai
    VARS=("thetao")
    ;;
  chl_nrt)
    DATASET="GLOBAL_ANALYSISFORECAST_BIO_001_028"  # contoh
    VARS=("chl")
    ;;
  wind_nrt)
    DATASET="GLOBAL_ANALYSISFORECAST_WIND_001_027" # contoh
    VARS=("u10" "v10")
    ;;
  wave_anfc)
    DATASET="GLOBAL_ANALYSISFORECAST_WAV_001_027"  # contoh
    VARS=("VHM0" "VTPK" "VMDR")
    ;;
  ssh_anfc)
    DATASET="GLOBAL_ANALYSISFORECAST_PHY_001_024"  # contoh
    VARS=("zos")
    ;;
  sal_anfc)
    DATASET="GLOBAL_ANALYSISFORECAST_PHY_001_024"  # contoh
    VARS=("so")
    ;;
  *)
    echo "[ERR] unknown kind: $NELAYA_KIND" >&2
    exit 3
    ;;
esac

# NOTE:
# dataset IDs di atas adalah "contoh struktur". Kita harus samakan dengan yang sudah kamu pakai
# di skrip lama. Kalau sekarang beda, kita sesuaikan dari download_inputs_latest.sh / log.

# Jalankan download (format CLI bisa beda tergantung versi copernicusmarine)
# Kalau command kamu dulu beda, kita edit bagian ini sesuai log yang sukses.
args=(
  "$COP" subset
  --dataset-id "$DATASET"
  --minimum-longitude "$MIN_LON" --maximum-longitude "$MAX_LON"
  --minimum-latitude "$MIN_LAT" --maximum-latitude "$MAX_LAT"
  --start-datetime "$START" --end-datetime "$END"
  --output-filename "$NELAYA_OUT"
)

for v in "${VARS[@]}"; do
  args+=( --variable "$v" )
done

echo "[CMD] ${args[*]}"
"${args[@]}"
