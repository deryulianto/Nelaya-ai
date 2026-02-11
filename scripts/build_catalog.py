#!/usr/bin/env python
import os, warnings
import pandas as pd
import xarray as xr

warnings.filterwarnings("ignore", category=FutureWarning)

rows = []
for root, _, files in os.walk("data"):
    for f in files:
        if not f.endswith(".nc"):
            continue
        p = os.path.join(root, f)
        rec = {
            "path": p,
            "vars": None,
            "dims": None,
            "time_start": None,
            "time_end": None,
            "size_bytes": os.path.getsize(p),
        }
        try:
            # decode_times=False biar cepat & aman untuk berbagai origin time
            # chunks={} -> buka tanpa memuat penuh ke RAM
            ds = xr.open_dataset(p, decode_times=False, chunks={})
            # gunakan sizes (mapping dim->length) -> tidak memicu FutureWarning
            rec["dims"] = ";".join(f"{k}:{int(v)}" for k, v in ds.sizes.items())
            rec["vars"] = ";".join(sorted([k for k in ds.data_vars]))

            # cari variabel waktu umum
            for tname in ("time", "TIME", "t"):
                if tname in ds.variables:
                    t = ds[tname]
                    if t.size > 0:
                        rec["time_start"] = float(t.isel({tname: 0}).values)
                        rec["time_end"]   = float(t.isel({tname:-1}).values)
                    break
        except Exception as e:
            rec["vars"] = f"<err:{type(e).__name__}>"
            rec["dims"] = "<err>"
        rows.append(rec)

df = pd.DataFrame(rows).sort_values("path")
os.makedirs("data/meta", exist_ok=True)
# Tulis Parquet (jika pyarrow ada), sambil selalu tulis CSV
try:
    df.to_parquet("data/meta/catalog.parquet", index=False)
except Exception:
    pass
df.to_csv("data/meta/catalog.csv", index=False)
print(f"Saved → data/meta/catalog.parquet & data/meta/catalog.csv ( {len(df)} files )")
