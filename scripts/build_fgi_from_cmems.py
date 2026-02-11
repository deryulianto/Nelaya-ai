#!/usr/bin/env python3
import sys, math
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "cmems" / "parquet"
OUT = ROOT / "data" / "fgi_grid"; OUT.mkdir(parents=True, exist_ok=True)

def fgi_rule(sst, chl, u, v):
    temp_ok = 1.0 if 26.5 <= sst <= 30.5 else 0.0
    chl_norm = np.log1p(max(chl, 0.0))          # 0..~2
    speed = math.hypot(u or 0.0, v or 0.0)      # m/s
    curr_pen = min(speed/1.0, 1.0)              # penalti jika >1 m/s
    raw = 0.5*temp_ok + 0.7*chl_norm - 0.6*curr_pen
    # sigmoid
    return 1/(1+math.exp(-raw))

def main(date):
    src = list(SRC.glob(f"*{date.replace('-','')}*.parquet"))
    if not src:
        print(f"[WARN] Tidak ada parquet CMEMS utk {date}")
        sys.exit(1)
    df = pd.read_parquet(src[0])
    # kolom minimal: time, lat, lon, sst, sal, u, v, chl (sebagian bisa hilang → isi 0)
    for c in ["sst","chl","u","v"]:
        if c not in df.columns: df[c] = 0.0
    df["FGI"] = df.apply(lambda r: fgi_rule(float(r.sst), float(r.chl), float(r.u), float(r.v)), axis=1)
    def cat(x): 
        return "High" if x >= 0.7 else ("Medium" if x >= 0.3 else "Low")
    df["category"] = df["FGI"].apply(cat)
    out = OUT / f"fgi_grid_{date}.parquet"
    df[["time","lat","lon","sst","chl","u","v","FGI","category"]].to_parquet(out, index=False)
    print("✅ saved:", out)

if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv)>1 else pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    main(date)
