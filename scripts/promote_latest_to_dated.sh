#!/usr/bin/env bash
set -euo pipefail

ROOT="data/raw/aceh_simeulue"
LATEST="${ROOT}/latest"
KEEP="${KEEP_LATEST:-7}"   # simpan N file bertanggal per metrik di latest

PY="./.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="python3"; fi

# ambil tanggal data dari NetCDF (YYYY-MM-DD)
nc_date() {
  "$PY" - <<'PY' "$1"
import sys, xarray as xr
p=sys.argv[1]
with xr.open_dataset(p, decode_times=True) as ds:
    t=None
    for k in ("time","valid_time","time_counter"):
        if k in ds.variables:
            t=ds[k].values
            break
    if t is None:
        for k in ds.coords:
            if "time" in k.lower():
                t=ds[k].values
                break
    if t is None:
        raise SystemExit("NO_TIME")
    v=t[-1] if hasattr(t,"__len__") else t
    print(str(v)[:10])
PY
}

promote_one() {
  local f="$1"
  local base metric day y m kind dest_dir dest_name dest_path latest_name

  base="$(basename "$f")"
  metric="${base%.nc}"

  # hanya proses file "generik" (mis: sst_nrt.nc), bukan yang sudah bertanggal
  if [[ "$base" == *_aceh_*.nc ]]; then
    return 0
  fi

  day="$(nc_date "$f" || true)"
  if [[ -z "${day}" || "${day}" == "NO_TIME" ]]; then
    echo "[SKIP] no time coord: $f"
    return 0
  fi

  y="${day:0:4}"
  m="${day:5:2}"

  # pola nama historis mengikuti kebiasaan kamu:
  # - anfc: folder sal_anfc/..., file: sal_aceh_YYYY-MM-DD.nc
  # - nrt : folder sst_nrt/..., file: sst_nrt_aceh_YYYY-MM-DD.nc
  if [[ "$metric" == *_anfc ]]; then
    kind="${metric%_anfc}"                 # sal_anfc -> sal
    dest_name="${kind}_aceh_${day}.nc"
  else
    kind="${metric}"                       # sst_nrt tetap sst_nrt
    dest_name="${metric}_aceh_${day}.nc"
  fi

  dest_dir="${ROOT}/${metric}/${y}/${m}"
  mkdir -p "$dest_dir"
  dest_path="${dest_dir}/${dest_name}"

  # 1) simpan ke dataset historis
  if [[ -f "$dest_path" ]]; then
    # jika sudah ada, buang staging agar tidak dobel (anggap dest benar)
    echo "[OK] exists, drop staging: $dest_path"
    rm -f "$f"
  else
    mv "$f" "$dest_path"
    echo "[MOVE] $base -> $dest_path"
  fi

  # 2) buat latest yang informatif (hardlink kalau bisa, fallback copy)
  latest_name="${LATEST}/${dest_name}"
  if ln -f "$dest_path" "$latest_name" 2>/dev/null; then
    echo "[LINK] latest/${dest_name} (hardlink)"
  else
    cp -a "$dest_path" "$latest_name"
    echo "[COPY] latest/${dest_name}"
  fi

  # 3) bersihkan latest versi bertanggal lama (per kind/metric)
  #    contoh: sst_nrt_aceh_*.nc, sal_aceh_*.nc
  local prefix
  prefix="${LATEST}/${kind}_aceh_"
  mapfile -t files < <(ls -1 "${prefix}"*.nc 2>/dev/null | sort || true)
  local n="${#files[@]}"
  if (( n > KEEP )); then
    for ((i=0; i<n-KEEP; i++)); do
      rm -f "${files[$i]}"
    done
    echo "[CLEAN] removed $((n-KEEP)) old files for ${kind}"
  fi
}

mkdir -p "$LATEST"

shopt -s nullglob
for f in "$LATEST"/*.nc; do
  promote_one "$f"
done

echo "[DONE] promote_latest_to_dated finished."
