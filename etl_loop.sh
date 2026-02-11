#!/usr/bin/env bash
set -euo pipefail

# ===== KONFIG RINGAN =====
REGION="aceh"
LON_MIN=90; LON_MAX=106
LAT_MIN=-10; LAT_MAX=10

RUN_GFS=1
RUN_FEATURES=1
RUN_CHECKSUM=1
RUN_CATALOG=1

GFS_SDATE="${GFS_SDATE:-2025-10-26}"
GFS_EDATE="${GFS_EDATE:-2025-10-26}"
GFS_HH="${GFS_HH:-00}"

mkdir -p data/raw/wind/gfs/2025/10 data/derived/wind/2025/10 data/meta

log(){ echo "[ETL] $*"; }

date_seq(){ local d="$1"; local end="$2"; while [ "$(date -ud "$d" +%F)" != "$(date -ud "$end +1 day" +%F)" ]; do echo "$(date -ud "$d" +%F)"; d="$(date -ud "$d +1 day" +%F)"; done; }

standardize_wind_netcdf(){ # arg: path.nc
  local P="$1"
  ncrename -O -d lat,latitude     "$P" 2>/dev/null || true
  ncrename -O -d lon,longitude    "$P" 2>/dev/null || true
  ncrename -O -v ugrd10m,u10      "$P" 2>/dev/null || true
  ncrename -O -v vgrd10m,v10      "$P" 2>/dev/null || true
  ncrename -O -v UGRD_10maboveground,u10 "$P" 2>/dev/null || true
  ncrename -O -v VGRD_10maboveground,v10 "$P" 2>/dev/null || true
}

pull_gfs_day(){ local D="$1"
  local OUT="data/raw/wind/gfs/2025/10/gfs_u10v10_${D}_${GFS_HH}z_${REGION}.nc"
  set +e
  python scripts/pull_gfs_subset.py \
    --run-date ${D} --hour ${GFS_HH} \
    --lon-min ${LON_MIN} --lon-max ${LON_MAX} \
    --lat-min ${LAT_MIN} --lat-max ${LAT_MAX} \
    --out "${OUT}"
  local rc=$?
  set -e
  if [ $rc -ne 0 ]; then
    log "OPeNDAP gagal untuk ${D} (rc=$rc). Skip hari ini."
    return 0
  fi
  standardize_wind_netcdf "${OUT}"
}

derive_wind_features(){ local D="$1"
  local SRC="data/raw/wind/gfs/2025/10/gfs_u10v10_${D}_${GFS_HH}z_${REGION}.nc"
  [ -f "$SRC" ] || { log "Skip features (no $SRC)"; return 0; }
  log "Wind features ${D}"
  python scripts/derive_wind_features.py \
    --src "$SRC" \
    --out "data/derived/wind/2025/10/wind_features_gfs_${D}_${GFS_HH}z_${REGION}.nc" || true
}

append_checksums(){
  log "Update checksums"
  find data -type f -name "*.nc" -printf "%p\n" | sort | xargs -r sha256sum >> data/meta/checksums.sha256
}

build_catalog_csv(){
  log "Build catalog CSV"
  python scripts/build_catalog_csv.py
}

# ===== RUN =====
if [ "$RUN_GFS" -eq 1 ] || [ "$RUN_FEATURES" -eq 1 ]; then
  for D in $(date_seq "$GFS_SDATE" "$GFS_EDATE"); do
    [ "$RUN_GFS" -eq 1 ] && pull_gfs_day "$D"
    [ "$RUN_FEATURES" -eq 1 ] && derive_wind_features "$D"
  done
fi

[ "$RUN_CHECKSUM" -eq 1 ] && append_checksums
[ "$RUN_CATALOG" -eq 1 ] && build_catalog_csv

log "DONE."
