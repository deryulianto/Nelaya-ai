#!/usr/bin/env bash
set -Eeuo pipefail

REGION="aceh"
LON_MIN=90; LON_MAX=106
LAT_MIN=-10; LAT_MAX=10

OUT_DIR_CUR="data/raw/phy/2025/09"
OUT_DIR_SSH="data/raw/phy/2025/09"
mkdir -p "$OUT_DIR_CUR" "$OUT_DIR_SSH"

log(){ echo "[CMEMS] $*"; }
retry(){ local n=0; local max=3; local delay=5; until "$@"; do n=$((n+1)); [ $n -ge $max ] && return 1; sleep $delay; delay=$((delay*2)); echo "[retry] attempt $((n+1))/$max: $*"; done; }

date_seq(){ local d="$1"; local e="$2"; while [ "$(date -ud "$d" +%F)" != "$(date -ud "$e +1 day" +%F)" ]; do echo "$(date -ud "$d" +%F)"; d="$(date -ud "$d +1 day" +%F)"; done; }

pull_cur_day(){ local D="$1" F="$OUT_DIR_CUR/phy_cur_${D}_${REGION}.nc"; [ -s "$F" ] && { log "skip uo/vo $D (exists)"; return 0; }
  log "uo/vo $D → $F"
  retry copernicusmarine subset \
    --dataset-id cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m \
    --variable uo --variable vo \
    --start-datetime ${D} --end-datetime ${D}T23:59:59Z \
    --minimum-latitude ${LAT_MIN} --maximum-latitude ${LAT_MAX} \
    --minimum-longitude ${LON_MIN} --maximum-longitude ${LON_MAX} \
    --minimum-depth 0.49402499198913574 --maximum-depth 0.49402499198913574 \
    --output-filename "$F"
}

pull_ssh_day(){ local D="$1" F="$OUT_DIR_SSH/phy_ssh_${D}_${REGION}.nc"; [ -s "$F" ] && { log "skip zos $D (exists)"; return 0; }
  log "zos $D → $F"
  retry copernicusmarine subset \
    --dataset-id cmems_mod_glo_phy_anfc_0.083deg_P1D-m \
    --variable zos \
    --start-datetime ${D} --end-datetime ${D}T23:59:59Z \
    --minimum-latitude ${LAT_MIN} --maximum-latitude ${LAT_MAX} \
    --minimum-longitude ${LON_MIN} --maximum-longitude ${LON_MAX} \
    --output-filename "$F"
}

main(){
  local S="2025-09-02" E="2025-09-30"  # 01 sudah ada di kamu
  for D in $(date_seq "$S" "$E"); do
    pull_cur_day "$D" || echo "[warn] uo/vo gagal $D"
    pull_ssh_day "$D" || echo "[warn] zos gagal $D"
    sleep 1
  done
  echo "[CMEMS] done."
}
main
