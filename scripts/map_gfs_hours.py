#!/usr/bin/env python
import sys, datetime as dt
# target 24 jam UTC untuk satu tanggal
date = dt.datetime.strptime(sys.argv[1], "%Y-%m-%d")
hours = [date + dt.timedelta(hours=h) for h in range(24)]

# siklus yang dicoba berurutan (prioritas tinggi dulu)
cycles = [0, 6, 12, 18]

def best_pairs(t):
    # untuk waktu t, cari (run_cycle, fh) yang cocok
    pairs=[]
    for cyc in cycles:
        run = t.replace(hour=cyc, minute=0, second=0, microsecond=0)
        if run>t: run -= dt.timedelta(days=1)  # siklus tidak boleh di masa depan
        fh = int((t - run).total_seconds()//3600)
        if 0 <= fh <= 384:  # batas aman GFS
            pairs.append((run, cyc, fh))
    # urutan sudah dari cycles; kembalikan kandidat
    return pairs

print("#hour, run_yyyymmdd, cycle_hh, fh3")
for idx,t in enumerate(hours):
    cands = best_pairs(t)
    line = f"{idx:02d}"
    for run, cyc, fh in cands:
        line += f" {run:%Y%m%d} {cyc:02d} {fh:03d}"
    print(line)
