#!/usr/bin/env bash
set -euo pipefail

REGION="aceh"
LON_MIN=90; LON_MAX=106
LAT_MIN=-10; LAT_MAX=10

PHY_DATE="2025-09-01"
CHL_MONTH="2025-09"
WAV_START="2025-10-26"
WAV_END="2025-10-29"
GFS_RUN="2025-10-26"

mkdir -p data/raw/phy/2025/09 data/raw/chl/2025/09 data/raw/wave/2025/10 \
         data/raw/wind/gfs/2025/10 data/derived/{wind,eke,chl}/2025/{09,10} \
         data/meta/requests data/meta

log(){ echo "[ETL] $*"; }

pull_phy_currents(){
  log "PHY uo/vo ${PHY_DATE}"
  copernicusmarine subset \
    --dataset-id cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m \
    --variable uo --variable vo \
    --start-datetime ${PHY_DATE} --end-datetime ${PHY_DATE}T23:59:59Z \
    --minimum-latitude ${LAT_MIN} --maximum-latitude ${LAT_MAX} \
    --minimum-longitude ${LON_MIN} --maximum-longitude ${LON_MAX} \
    --minimum-depth 0.49402499198913574 --maximum-depth 0.49402499198913574 \
    --output-filename data/raw/phy/2025/09/phy_cur_${PHY_DATE}_${REGION}.nc
}

pull_phy_ssh(){
  log "PHY SSH zos ${PHY_DATE}"
  copernicusmarine subset \
    --dataset-id cmems_mod_glo_phy_anfc_0.083deg_P1D-m \
    --variable zos \
    --start-datetime ${PHY_DATE} --end-datetime ${PHY_DATE}T23:59:59Z \
    --minimum-latitude ${LAT_MIN} --maximum-latitude ${LAT_MAX} \
    --minimum-longitude ${LON_MIN} --maximum-longitude ${LON_MAX} \
    --output-filename data/raw/phy/2025/09/phy_ssh_${PHY_DATE}_${REGION}.nc
}

pull_chl_my_p1d(){
  log "CHL MY P1D ${CHL_MONTH}"
  copernicusmarine subset \
    --dataset-id cmems_obs-oc_glo_bgc-plankton_my_l4-gapfree-multi-4km_P1D \
    --variable CHL \
    --start-datetime ${CHL_MONTH}-01 --end-datetime ${CHL_MONTH}-30T23:59:59Z \
    --minimum-latitude ${LAT_MIN} --maximum-latitude ${LAT_MAX} \
    --minimum-longitude ${LON_MIN} --maximum-longitude ${LON_MAX} \
    --output-filename data/raw/chl/2025/09/chl_MY_gapfree_P1D_${CHL_MONTH}_${REGION}.nc
}

pull_wave(){
  log "WAVE PT3H ${WAV_START}..${WAV_END}"
  copernicusmarine subset \
    --dataset-id cmems_mod_glo_wav_anfc_0.083deg_PT3H-i \
    --variable VHM0 --variable VTM10 --variable VMDR \
    --start-datetime ${WAV_START} --end-datetime ${WAV_END} \
    --minimum-latitude ${LAT_MIN} --maximum-latitude ${LAT_MAX} \
    --minimum-longitude ${LON_MIN} --maximum-longitude ${LON_MAX} \
    --output-filename data/raw/wave/2025/10/wave_${WAV_START}_PT3H_${REGION}.nc
}

pull_gfs(){
  log "GFS 0.25 00Z ${GFS_RUN} via OPeNDAP:443"
  python scripts/pull_gfs_subset.py \
    --run-date ${GFS_RUN} --hour 00 \
    --lon-min ${LON_MIN} --lon-max ${LON_MAX} \
    --lat-min ${LAT_MIN} --lat-max ${LAT_MAX} \
    --out data/raw/wind/gfs/2025/10/gfs_u10v10_${GFS_RUN}_00z_${REGION}.nc
}

derive_features(){
  log "Wind features: |U|, tau, curl(tau), w_E"
  python scripts/derive_wind_features.py \
    --src data/raw/wind/gfs/2025/10/gfs_u10v10_${GFS_RUN}_00z_${REGION}.nc \
    --out data/derived/wind/2025/10/wind_features_gfs_${GFS_RUN}_00z_${REGION}.nc
}

write_checksums(){
  log "Checksums"
  {
    sha256sum data/raw/phy/2025/09/phy_cur_${PHY_DATE}_${REGION}.nc 2>/dev/null || true
    sha256sum data/raw/phy/2025/09/phy_ssh_${PHY_DATE}_${REGION}.nc 2>/dev/null || true
    sha256sum data/raw/chl/2025/09/chl_MY_gapfree_P1D_${CHL_MONTH}_${REGION}.nc 2>/dev/null || true
    sha256sum data/raw/wave/2025/10/wave_${WAV_START}_PT3H_${REGION}.nc 2>/dev/null || true
    sha256sum data/raw/wind/gfs/2025/10/gfs_u10v10_${GFS_RUN}_00z_${REGION}.nc 2>/dev/null || true
    sha256sum data/derived/wind/2025/10/wind_features_gfs_${GFS_RUN}_00z_${REGION}.nc 2>/dev/null || true
  } | tee -a data/meta/checksums.sha256
}

echo "[ETL] Selesai memuat fungsi. Un-comment baris di bawah sesuai kebutuhan:"
#pull_phy_currents
#pull_phy_ssh
#pull_chl_my_p1d
#pull_wave
#pull_gfs
#derive_features
#write_checksums
