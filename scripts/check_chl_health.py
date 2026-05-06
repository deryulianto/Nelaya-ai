from pathlib import Path
import json
import re
import numpy as np
import xarray as xr

ROOT = Path("/home/coastalai/NELAYA-AI-LAB")
EARTH = ROOT / "data/earth/earth_signals_today.json"

print("\n=== 1) CEK earth_signals_today.json ===")
if EARTH.exists():
    d = json.loads(EARTH.read_text())
    print("date:", d.get("date"))
    print("snapshot_date:", d.get("snapshot_date"))
    print("latest_available_date:", d.get("latest_available_date"))
    print("generated_at:", d.get("generated_at"))

    metrics = d.get("metrics", {})
    print("\nCHL-like metrics:")
    found = False
    for k, v in metrics.items():
        if re.search(r"chl|chlor|chla", k, re.I):
            print(" ", k, "=", v)
            found = True
    if not found:
        print("  Tidak ada key CHL-like di .metrics")

    print("\nCHL-like top-level:")
    found = False
    for k, v in d.items():
        if re.search(r"chl|chlor|chla", k, re.I):
            print(" ", k, "=", v)
            found = True
    if not found:
        print("  Tidak ada key CHL-like di top-level")
else:
    print("earth_signals_today.json tidak ditemukan:", EARTH)

print("\n=== 2) CARI FILE RAW CHL ===")
candidates = []
for p in (ROOT / "data").rglob("*"):
    if p.is_file() and re.search(r"chl|chlor|chla", p.name, re.I):
        candidates.append(p)

candidates = sorted(candidates, key=lambda p: p.stat().st_mtime)
if not candidates:
    print("Tidak ada file raw CHL/chlor/chla ditemukan di data/")
    raise SystemExit

for p in candidates[-20:]:
    print(f"{p.stat().st_size:>12} bytes  {p}")

print("\n=== 3) BUKA NETCDF TERBARU DAN CEK VARIABLE ===")
nc_files = [p for p in candidates if p.suffix.lower() in [".nc", ".nc4", ".cdf"]]
if not nc_files:
    print("Tidak ada file NetCDF CHL ditemukan.")
    raise SystemExit

for p in nc_files[-10:]:
    print("\n--- FILE:", p)
    try:
        ds = xr.open_dataset(p)
        print("dims:", dict(ds.dims))
        print("coords:", list(ds.coords))
        print("data_vars:", list(ds.data_vars))

        time_name = None
        for c in ["time", "valid_time", "date"]:
            if c in ds.coords or c in ds.dims:
                time_name = c
                break

        if time_name:
            try:
                times = ds[time_name].values
                print("time first:", str(times[0]))
                print("time last :", str(times[-1]))
                print("time count:", len(times))
            except Exception as e:
                print("time read error:", e)

        chl_vars = [v for v in ds.data_vars if re.search(r"chl|chlor|chla", v, re.I)]
        if not chl_vars:
            print("Tidak ada data_vars bernama CHL-like.")
            ds.close()
            continue

        for var in chl_vars:
            da = ds[var]
            print("candidate var:", var, "dims:", da.dims, "shape:", da.shape)
            try:
                # Ambil time terakhir kalau ada dimensi time
                if time_name and time_name in da.dims:
                    da2 = da.isel({time_name: -1})
                else:
                    da2 = da

                arr = da2.values
                valid = np.isfinite(arr)
                valid_count = int(valid.sum())
                total = int(arr.size)
                if valid_count > 0:
                    mean_val = float(np.nanmean(arr))
                    min_val = float(np.nanmin(arr))
                    max_val = float(np.nanmax(arr))
                    print("valid:", valid_count, "/", total)
                    print("mean :", mean_val)
                    print("min  :", min_val)
                    print("max  :", max_val)
                else:
                    print("Semua nilai NaN/tidak valid pada slice terakhir.")
            except Exception as e:
                print("stat read error:", e)

        ds.close()

    except Exception as e:
        print("GAGAL buka file:", e)
