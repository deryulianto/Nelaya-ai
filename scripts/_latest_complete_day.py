from pathlib import Path
import re, sys

ROOT = Path(__file__).resolve().parents[1]
RAW  = ROOT / "data" / "raw" / "aceh_simeulue"
KINDS = ["sst_nrt","chl_nrt","wind_nrt","wave_anfc","ssh_anfc","sal_anfc"]
pat = re.compile(r"(\d{4}-\d{2}-\d{2})")

def latest_day(kind: str):
    base = RAW / kind
    if not base.exists(): return None
    days=[]
    for p in base.rglob("*.nc"):
        m = pat.search(p.name)
        if m: days.append(m.group(1))
    return max(days) if days else None

days = {k: latest_day(k) for k in KINDS}
if any(v is None for v in days.values()):
    print("MISSING:", days, file=sys.stderr)
    sys.exit(2)

# hari lengkap terbaru = yang paling “ketinggalan” di antara inputs
print(min(days.values()))
