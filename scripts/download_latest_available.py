from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
import argparse

ROOT = Path(__file__).resolve().parents[1]
RAW_BASE = ROOT / "data" / "raw" / "aceh_simeulue"

KINDS = ["sst_nrt", "chl_nrt", "wind_nrt", "wave_anfc", "ssh_anfc", "sal_anfc"]

MIN_BYTES_DEFAULT = 10_000


def _is_ok_file(p: Path, min_bytes: int = MIN_BYTES_DEFAULT) -> bool:
    try:
        return p.exists() and p.is_file() and p.stat().st_size >= min_bytes
    except Exception:
        return False


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def ymd(d: date) -> str:
    return d.isoformat()


def default_out_path(kind: str, d: date) -> Path:
    y = f"{d.year:04d}"
    m = f"{d.month:02d}"
    day = ymd(d)

    if kind in ("sst_nrt", "chl_nrt", "wind_nrt"):
        fname = f"{kind}_aceh_{day}.nc"
        return RAW_BASE / kind / y / m / fname

    if kind == "wave_anfc":
        return RAW_BASE / kind / y / m / f"wave_aceh_{day}.nc"

    if kind == "ssh_anfc":
        return RAW_BASE / kind / y / m / f"ssh_aceh_{day}.nc"

    if kind == "sal_anfc":
        return RAW_BASE / kind / y / m / f"sal_aceh_{day}.nc"

    return RAW_BASE / kind / y / m / f"{kind}_aceh_{day}.nc"


def _run_download(kind: str, d: date, out: Path, verbose: bool = False) -> tuple[bool, str]:
    """
    Jalankan downloader 1 kali untuk (kind, d) ke file out.
    Return (ok, log_text).
    """
    out.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["NELAYA_KIND"] = kind
    env["NELAYA_DAY"] = ymd(d)
    env["NELAYA_OUT"] = str(out)

    r = subprocess.run(
        ["bash", "scripts/_cmems_download_one.sh"],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )

    log = ((r.stdout or "") + ("\n" if r.stdout and r.stderr else "") + (r.stderr or "")).strip()

    # sukses kalau exit=0 dan file valid
    if r.returncode == 0 and _is_ok_file(out):
        return True, log

    # kalau file kecil/partial, bersihkan
    try:
        if out.exists() and out.stat().st_size < MIN_BYTES_DEFAULT:
            out.unlink()
    except Exception:
        pass

    # kalau verbose, kembalikan log biar kelihatan kenapa gagal
    return False, log


def find_latest(
    kind: str,
    base_day: date,
    max_back: int,
    out_override: str | None = None,
    verbose: bool = False,
) -> Path | None:
    """
    Cari data terbaru dengan mundur sampai max_back hari.
    Prioritas: cache lokal -> kalau sudah ada dan valid, HIT tanpa download.
    """
    for i in range(max_back + 1):
        d = base_day - timedelta(days=i)

        out = Path(out_override) if out_override else default_out_path(kind, d)

        # 0) CACHE HIT: kalau file sudah ada & valid, jangan download ulang
        if _is_ok_file(out):
            print(f"[HIT] local cache exists: {out.as_posix()} ({out.stat().st_size} bytes)")
            return out

        print(f"[TRY] {kind} day={ymd(d)} -> {out.as_posix()}")

        ok, log = _run_download(kind, d, out, verbose=verbose)
        if ok:
            print(f"[OK]  {kind} -> {out.as_posix()}")
            return out

        print(f"[MISS] {kind} not available for {ymd(d)} (try previous day)")
        if verbose and log:
            print("----- downloader log (tail) -----")
            # biar tidak kebanjiran, tampilkan tail 80 baris saja
            lines = log.splitlines()
            tail = "\n".join(lines[-80:])
            print(tail)
            print("----- end log -----")

    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="", help="YYYY-MM-DD (default: today UTC)")
    ap.add_argument("--max-back", type=int, default=7)
    ap.add_argument("--kind", default="", help="run only one kind")
    ap.add_argument(
        "--out",
        default="",
        help="override output path (advanced). If set, file will be written here (no per-day naming).",
    )
    ap.add_argument("--verbose", action="store_true", help="print downloader log when MISS")
    args = ap.parse_args()

    base_day = utc_today()
    if args.day:
        base_day = datetime.strptime(args.day, "%Y-%m-%d").date()

    kinds = [args.kind] if args.kind else KINDS

    # validasi kind supaya tidak “MISS halu”
    for k in kinds:
        if k not in KINDS:
            print(f"[ERROR] unknown kind: {k}. Allowed: {', '.join(KINDS)}")
            sys.exit(2)

    out_override = args.out.strip() or None

    ok_any = False
    for k in kinds:
        print(f"\n---- {k} ----")
        p = find_latest(
            k,
            base_day=base_day,
            max_back=int(args.max_back),
            out_override=out_override,
            verbose=bool(args.verbose),
        )
        if p:
            ok_any = True

    print("\n[DONE] all downloads attempted.")
    sys.exit(0 if ok_any else 2)


if __name__ == "__main__":
    main()
