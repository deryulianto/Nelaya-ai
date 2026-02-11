#!/usr/bin/env bash
set -Eeuo pipefail

# ===== Params =====
DATE="${1:-2025-10-28}"          # tanggal target (UTC), default contoh
REGION="aceh"
LON_MIN=90;  LON_MAX=106
LAT_MIN=-10; LAT_MAX=10

OUT="data/raw/wind/erddap/${DATE:0:4}/${DATE:5:2}/ncei_blended_wind_${DATE}_${REGION}.nc"
OUT_DIRV="data/derived/wind/${DATE:0:4}/${DATE:5:2}"
OUT_DER="${OUT_DIRV}/wind_features_ncei_blended_${DATE}_${REGION}.nc"

mkdir -p "$(dirname "$OUT")" "$OUT_DIRV" data/meta

log(){ echo "[ERDDAP] $*"; }

# Kurangi agresivitas thread lib numerik
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

# 1) Download 6-hourly (00/06/12/18Z) via ERDDAP (stabil & kecil)
#    Dataset: NOAA CoastWatch NRT Blended Winds 6-hourly @0.25deg
#    Subset time: DATE 00Z..18Z, lat: LAT_MIN..LAT_MAX, lon: LON_MIN..LON_MAX
URL="https://coastwatch.noaa.gov/erddap/griddap/noaacwBlendednrtWinds6hr.nc"
Q="uwnd[(${DATE}T00:00:00Z):1:(${DATE}T18:00:00Z)][(${LAT_MIN}):1:(${LAT_MAX})][(${LON_MIN}):1:(${LON_MAX})],vwnd[(${DATE}T00:00:00Z):1:(${DATE}T18:00:00Z)][(${LAT_MIN}):1:(${LAT_MAX})][(${LON_MIN}):1:(${LON_MAX})]"

log "Download ${DATE} bbox=(${LAT_MIN},${LON_MIN})..(${LAT_MAX},${LON_MAX})"
# retry ringan + fail on HTTP errors
curl -fSLo "$OUT" --retry 4 --retry-delay 5 --connect-timeout 15 \
  "${URL}?${Q}"

# 2) Standarkan nama variabel agar cocok pipeline (u10/v10)
log "Standardize variable names → u10/v10"
ncrename -O -v uwnd,u10 -v vwnd,v10 "$OUT"

# 3) Turunkan fitur (|U|, tau, curl_tau, w_E) dgn skrip yang sudah ada
log "Derive wind features"
python scripts/derive_wind_features.py --src "$OUT" --out "$OUT_DER"

# 4) Catat checksum & rebuild catalog CSV
log "Update checksums & catalog"
sha256sum "$OUT" "$OUT_DER" | tee -a data/meta/checksums.sha256
python scripts/build_catalog_csv.py

log "DONE. → $OUT  &  $OUT_DER"
