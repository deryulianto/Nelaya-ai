from __future__ import annotations

import argparse
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_BASE = ROOT / "data" / "raw" / "aceh_simeulue" / "cur_nrt"

BBOX = {
    "min_lon": 92.0,
    "max_lon": 99.0,
    "min_lat": 1.0,
    "max_lat": 7.0,
}

DATASET_ID = "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m"
DEPTH = "0.49402499198913574"


def ymd(d: date) -> str:
    return d.isoformat()


def out_path_for_day(d: date) -> Path:
    return OUT_BASE / f"{d.year:04d}" / f"{d.month:02d}" / f"current_nrt_aceh_{ymd(d)}.nc"


def download_current(day: date, overwrite: bool = False) -> Path:
    out_path = out_path_for_day(day)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and out_path.stat().st_size > 10_000 and not overwrite:
        print(f"[SKIP] exists: {out_path}")
        return out_path

    start_dt = f"{ymd(day)}T00:00:00"
    end_dt = f"{ymd(day)}T23:59:59"

    cmd = [
        "copernicusmarine",
        "subset",
        "--dataset-id", DATASET_ID,
        "--variable", "uo",
        "--variable", "vo",
        "--minimum-longitude", str(BBOX["min_lon"]),
        "--maximum-longitude", str(BBOX["max_lon"]),
        "--minimum-latitude", str(BBOX["min_lat"]),
        "--maximum-latitude", str(BBOX["max_lat"]),
        "--start-datetime", start_dt,
        "--end-datetime", end_dt,
        "--minimum-depth", DEPTH,
        "--maximum-depth", DEPTH,
        "--output-directory", str(out_path.parent),
        "--output-filename", out_path.name,
        "--force-download",
    ]

    print("[RUN]", " ".join(cmd))
    subprocess.run(cmd, check=True)

    if not out_path.exists() or out_path.stat().st_size <= 10_000:
        raise RuntimeError(f"Downloaded file invalid or too small: {out_path}")

    print(f"[OK] downloaded: {out_path}")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="YYYY-MM-DD. Default: today UTC")
    parser.add_argument("--days-back", type=int, default=2)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
        download_current(target, overwrite=args.overwrite)
        return 0

    # Copernicus harian kadang belum lengkap pada hari H.
    # Jadi coba hari ini, kemarin, lalu mundur sesuai days-back.
    today = datetime.now(timezone.utc).date()

    last_error = None
    for i in range(args.days_back + 1):
        d = today - timedelta(days=i)
        try:
            download_current(d, overwrite=args.overwrite)
            return 0
        except Exception as e:
            last_error = e
            print(f"[WARN] failed for {d}: {e}")

    raise RuntimeError(f"All attempts failed. Last error: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())
