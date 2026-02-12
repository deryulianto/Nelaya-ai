#!/usr/bin/env python3
"""
Temporary stub to prevent pipeline failure when this file was missing.

Goal: return exit code 0 so systemd service continues to run
(update_signals_today.py, timeseries, daily fgi, etc).

Next step: replace with real downloader logic.
"""
from __future__ import annotations
import sys
from datetime import datetime

def main() -> int:
    ts = datetime.now().isoformat(timespec="seconds")
    print(f"[WARN] download_latest_available.py STUB active ({ts}). No download executed.")
    # You can add quick sanity prints for args:
    if len(sys.argv) > 1:
        print("[INFO] args:", " ".join(sys.argv[1:]))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
