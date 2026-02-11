#!/usr/bin/env bash
set -Eeuo pipefail

# ===== PARAM =====
RUNDATE="${RUNDATE:-2025-10-26}"     # run sumber (UTC)
RUNHH="${RUNHH:-00}"                 # 00/06/12/18
TARGET="${TARGET:-2025-10-28}"       # tanggal target (UTC) (FH 48..71 utk 26/00Z)
REGION="${REGION:-aceh}"
LON_MIN="${LON_MIN:-90}"; LON_MAX="${LON_MAX:-106}"
LAT_MIN="${LAT_MIN:--10}"; LAT_MAX="${LAT_MAX:-10}"

BASE="https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.${RUNDATE//-/}/${RUNHH}/atmos"
TMP="data/tmp/gfs_${TARGET}_${RUNHH}"
OUTDIR_RAW="data/raw/wind/gfs/${TARGET:0:4}/${TARGET:5:2}"
OUTDIR_DER="data/derived/wind/${TARGET:0:4}/${TARGET:5:2}"
OUT_HR_DIR="${TMP}/nc_hourly"
OUT_DAY="${OUTDIR_RAW}/gfs_u10v10_${TARGET}_${RUNHH}z_${REGION}.nc"
OUT_DER="${OUTDIR_DER}/wind_features_gfs_${TARGET}_${RUNHH}z_${REGION}.nc"

mkdir -p "$TMP" "$OUTDIR_RAW" "$OUTDIR_DER" "$OUT_HR_DIR" data/meta

log(){ echo "[GFS] $*"; }
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

# ===== 1) Unduh 24 file: f048..f071 (28/00–23Z untuk run 26/00Z) =====
for f in $(seq -w 48 71); do
  url="${BASE}/gfs.t${RUNHH}z.pgrb2.0p25.f${f}"
  dst="${TMP}/gfs.t${RUNHH}z.pgrb2.0p25.f${f}"
  if [ -s "$dst" ]; then
    log "skip $f (exists)"; continue
  fi
  log "GET $url"
  if ! curl -fS --retry 5 --retry-delay 5 --connect-timeout 15 -o "$dst" "$url"; then
    log "skip $f (download fail)"; rm -f "$dst"
  fi
  sleep 1
done

# ===== 2) Proses per-jam: subset var & bbox → NetCDF per jam =====
python - << 'PY' "${TMP}" "${OUT_HR_DIR}" "${LON_MIN}" "${LON_MAX}" "${LAT_MIN}" "${LAT_MAX}"
import os, glob, sys, xarray as xr
TMP, OUT_HR_DIR, LON_MIN, LON_MAX, LAT_MIN, LAT_MAX = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6])

files = sorted(glob.glob(os.path.join(TMP, "gfs.t*z.pgrb2.0p25.f???")))
if not files: raise SystemExit("No GRIB files")

os.makedirs(OUT_HR_DIR, exist_ok=True)
for f in files:
    fh = os.path.basename(f)[-3:]
    try:
        du = xr.open_dataset(f, engine="cfgrib",
             backend_kwargs={"filter_by_keys":{"typeOfLevel":"heightAboveGround","shortName":"10u","level":10}})
        dv = xr.open_dataset(f, engine="cfgrib",
             backend_kwargs={"filter_by_keys":{"typeOfLevel":"heightAboveGround","shortName":"10v","level":10}})

        # cari nama dim lat/lon
        latd=[d for d in du.dims if 'lat' in d.lower()][0]
        lond=[d for d in du.dims if 'lon' in d.lower()][0]
        latv=du[latd]

        # slice lat sesuai urutan (naik/turun)
        lat_slc = slice(LAT_MAX, LAT_MIN) if float(latv[0])>float(latv[-1]) else slice(LAT_MIN, LAT_MAX)
        sub_u = du.rename({'10u':'u10'}).sel({latd:lat_slc, lond:slice(LON_MIN, LON_MAX)})
        sub_v = dv.rename({'10v':'v10'}).sel({latd:lat_slc, lond:slice(LON_MIN, LON_MAX)})

        ds = xr.merge([sub_u[['u10']], sub_v[['v10']]])
        out = os.path.join(OUT_HR_DIR, f"hour_{fh}.nc")
        ds.to_netcdf(out)
        print("Saved hour ->", out)
    except Exception as e:
        print("warn:", f, e)
PY

# ===== 3) Gabung ke harian =====
python - << 'PY' "${OUT_HR_DIR}" "${OUT_DAY}"
import os, glob, xarray as xr, sys
IN_DIR, OUT_DAY = sys.argv[1], sys.argv[2]
hrs = sorted(glob.glob(os.path.join(IN_DIR, "hour_???.nc")))
if not hrs: raise SystemExit("No hourly nc to concat")
dsets=[xr.open_dataset(h) for h in hrs]
ds=xr.concat(dsets, dim='time')
os.makedirs(os.path.dirname(OUT_DAY), exist_ok=True)
ds.to_netcdf(OUT_DAY)
print("Saved day ->", OUT_DAY, "| hours:", ds.sizes.get('time',0))
PY

# ===== 4) Fitur angin =====
python scripts/derive_wind_features.py --src "$OUT_DAY" --out "$OUT_DER"
log "Saved features -> $OUT_DER"

# ===== 5) Meta =====
sha256sum "$OUT_DAY" "$OUT_DER" | tee -a data/meta/checksums.sha256
python scripts/build_catalog_csv.py
log "DONE."
