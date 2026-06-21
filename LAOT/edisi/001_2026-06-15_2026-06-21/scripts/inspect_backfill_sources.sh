#!/usr/bin/env bash
set -u

ROOT="$HOME/NELAYA-AI-LAB"

echo "=== INSPEKSI SUMBER BACKFILL 15–18 JUNI 2026 ==="

for d in 2026-06-15 2026-06-16 2026-06-17 2026-06-18
do
  echo
  echo "=================================================="
  echo "## $d"
  echo "=================================================="

  MARKET="$ROOT/data/marketplace_insights/${d}.json"
  GRID_SUM="$ROOT/data/grid/daily/grid_scoring_${d}_calibrated_v011_summary.json"
  ZONE_SUM="$ROOT/data/grid/hotspots/grid_hotspot_zones_${d}_v012_summary.json"
  HOT_SUM="$ROOT/data/grid/hotspots/grid_hotspot_${d}_v010_summary.json"

  echo
  echo "--- MARKETPLACE INSIGHT ---"
  if [ -f "$MARKET" ]; then
    echo "$MARKET"
    jq 'keys' "$MARKET"
    echo "Ringkas:"
    jq '{
      date,
      headline,
      title,
      fgi,
      fgi_current_aware,
      sst,
      chl,
      chlorophyll,
      wave,
      wind,
      risk,
      summary,
      insight
    }' "$MARKET" 2>/dev/null || true
  else
    echo "Tidak ada: $MARKET"
  fi

  echo
  echo "--- GRID SCORING SUMMARY ---"
  if [ -f "$GRID_SUM" ]; then
    echo "$GRID_SUM"
    jq 'keys' "$GRID_SUM"
    jq '{
      date,
      score_mean_v011,
      overall_confidence_mean_v011,
      ocean_cells,
      coverage,
      quality,
      summary
    }' "$GRID_SUM" 2>/dev/null || true
  else
    echo "Tidak ada: $GRID_SUM"
  fi

  echo
  echo "--- ZONE SUMMARY ---"
  if [ -f "$ZONE_SUM" ]; then
    echo "$ZONE_SUM"
    jq 'keys' "$ZONE_SUM"
    jq '{
      date,
      zones_count,
      zone_level_counts,
      top_zones,
      zones,
      summary
    }' "$ZONE_SUM" 2>/dev/null || true
  else
    echo "Tidak ada: $ZONE_SUM"
  fi

  echo
  echo "--- HOTSPOT SUMMARY ---"
  if [ -f "$HOT_SUM" ]; then
    echo "$HOT_SUM"
    jq 'keys' "$HOT_SUM"
    jq '{
      date,
      hotspot_count,
      hotspot_counts,
      top_hotspots,
      summary
    }' "$HOT_SUM" 2>/dev/null || true
  else
    echo "Tidak ada: $HOT_SUM"
  fi
done
