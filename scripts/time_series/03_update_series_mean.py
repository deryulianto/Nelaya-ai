from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from ts_common import load_config, ensure_dirs


def append_daily_mean(series_csv: Path, date: str, mean_val: float) -> None:
    new_row = pd.DataFrame([{"date": date, "mean": mean_val}])

    if series_csv.exists():
        df = pd.read_csv(series_csv)
        df = df[df["date"] != date]
        df = pd.concat([df, new_row], ignore_index=True)
    else:
        df = new_row

    df = df.sort_values("date")
    df.to_csv(series_csv, index=False)



def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/time_series_aceh.yaml")
    ap.add_argument("--var", required=True, help="var key dari config (mis: sst/chlorophyll/current/temp50)")

    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    cfg = load_config(args.config)
    dirs = ensure_dirs(cfg, args.var)

    daily_csv = dirs["daily"] / f"{args.var}_daily_{args.date}.csv"
    if not daily_csv.exists():
        raise SystemExit(f"Daily grid CSV belum ada: {daily_csv}")

    df = pd.read_csv(daily_csv)

    if args.var == "current":
        # mean speed
        m = float(df["speed"].mean())
        series_csv = dirs["series"] / "current_daily_mean.csv"
    else:
        m = float(df["value"].mean())
        series_csv = dirs["series"] / f"{args.var}_daily_mean.csv"

    append_daily_mean(series_csv, args.date, m)
    print(f"[OK] updated series: {series_csv} (date={args.date}, mean={m:.6g})")


if __name__ == "__main__":
    main()
