#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def utc_today() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout

def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def try_download(kind: str, day: datetime, out_nc: Path) -> tuple[bool, str]:
    """
    Delegate actual download to copernicusmarine CLI using an env-var based recipe
    or pre-defined dataset selection inside bash script.
    We keep this python generic: it only calls the bash script with DAY/KIND.
    """
    ensure_parent(out_nc)
    env = os.environ.copy()
    env["NELAYA_KIND"] = kind
    env["NELAYA_DAY"] = day.date().isoformat()
    env["NELAYA_OUT"] = str(out_nc)

    # This helper bash script should exist (we'll create if missing)
    helper = ROOT / "scripts" / "_cmems_download_one.sh"
    if not helper.exists():
        return False, f"[MISS] helper not found: {helper}"

    code, out = run(["/usr/bin/bash", str(helper)])
    ok = (code == 0) and out_nc.exists() and out_nc.stat().st_size > 0
    return ok, out

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, help="sst_nrt|chl_nrt|wind_nrt|wave_anfc|ssh_anfc|sal_anfc|...")
    ap.add_argument("--out", required=True, help="output .nc path")
    ap.add_argument("--max-back", type=int, default=4, help="max days to step back when dataset not ready")
    args = ap.parse_args()

    kind = args.kind
    out_nc = Path(args.out)

    base = utc_today()
    logs: list[str] = []
    for back in range(0, args.max_back + 1):
        day = base - timedelta(days=back)
        logs.append(f"[TRY] {kind} day={day.date().isoformat()} -> {out_nc}")
        ok, out = try_download(kind, day, out_nc)
        logs.append(out.strip())
        if ok:
            logs.append(f"[OK] {kind} saved: {out_nc}")
            print("\n".join([x for x in logs if x]))
            return 0
        logs.append(f"[MISS] {kind} not available for {day.date().isoformat()} (try previous day)")

    print("\n".join([x for x in logs if x]))
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
