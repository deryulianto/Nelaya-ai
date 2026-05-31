#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/coastalai/NELAYA-AI-LAB"
cd "$ROOT"

mkdir -p logs/upwelling_daily

export PYTHONUNBUFFERED=1
export HDF5_USE_FILE_LOCKING=FALSE
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

source .venv/bin/activate

echo "=== NELAYA-AI Upwelling Daily Pipeline START $(date -Is) ==="

echo "=== 1. Build Upwelling Watch Today ==="
python scripts/build_upwelling_watch_today.py

echo "=== 2. Export candidates GeoJSON ==="
python scripts/export_upwelling_candidates_geojson.py

echo "=== 3. Export candidate buffers GeoJSON ==="
python scripts/export_upwelling_candidate_buffers_geojson.py

echo "=== 4. Export candidate clusters ==="
python scripts/export_upwelling_candidate_clusters.py

echo "=== 5. Export temporal memory ==="
python scripts/export_upwelling_temporal_memory.py

echo "=== 6. Cache upwelling for FGI Feature Store ==="
python scripts/cache_upwelling_today.py

echo "=== 7. Enrich freshness + archive daily outputs ==="
python scripts/enrich_upwelling_freshness_archive.py

echo "=== 8. Output audit ==="
python - <<'PY'
import json
from pathlib import Path
from datetime import datetime

p = Path("data/upwelling/upwelling_watch_today.json")
d = json.loads(p.read_text())

first = (d.get("candidate_locations") or d.get("top_cells") or [{}])[0]

print("file:", p)
print("file_mtime:", datetime.fromtimestamp(p.stat().st_mtime).isoformat())
print("generated_at:", d.get("generated_at"))
print("version:", d.get("version"))
print("score_max:", d.get("index", {}).get("score_max"))
print("score_mean:", d.get("index", {}).get("score_mean"))
print("top_coordinate:", first.get("coordinate_text") or f"{first.get('lat')}, {first.get('lon')}")
print("top_zone:", first.get("zone_label"))
print("data_files_used:")
for k, v in (d.get("data_files_used") or {}).items():
    print(f"  {k}: {v}")
PY

echo "=== NELAYA-AI Upwelling Daily Pipeline END $(date -Is) ==="
