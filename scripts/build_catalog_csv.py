#!/usr/bin/env python
import os, pandas as pd, xarray as xr
rows=[]
for root,_,files in os.walk("data"):
    for f in files:
        if not f.endswith(".nc"): continue
        p=os.path.join(root,f)
        rec={"path":p,"vars":None,"dims":None,"time_start":None,"time_end":None,"size_bytes":os.path.getsize(p)}
        try:
            ds=xr.open_dataset(p, decode_times=False, chunks={})
            rec["vars"]=";".join(sorted(ds.data_vars))
            rec["dims"]=";".join(f"{k}:{int(v)}" for k,v in ds.sizes.items())
            for t in ("time","TIME","t"):
                if t in ds.variables and ds[t].size>0:
                    rec["time_start"]=float(ds[t].isel({t:0}).values)
                    rec["time_end"]=float(ds[t].isel({t:-1}).values); break
        except Exception: pass
        rows.append(rec)
df=pd.DataFrame(rows).sort_values("path")
os.makedirs("data/meta", exist_ok=True)
df.to_csv("data/meta/catalog.csv", index=False)
print("Saved → data/meta/catalog.csv", len(df), "files")
