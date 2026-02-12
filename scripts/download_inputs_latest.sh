#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== NELAYA INPUTS: download latest available (UTC) ==="

PY="$ROOT/.venv/bin/python"
COP="$ROOT/.venv/bin/copernicusmarine"

if [ ! -x "$COP" ]; then
  echo "[ERROR] copernicusmarine not found"
  exit 1
fi

echo "[INFO] Using copernicusmarine: $COP"

"$PY" scripts/download_latest_available.py
