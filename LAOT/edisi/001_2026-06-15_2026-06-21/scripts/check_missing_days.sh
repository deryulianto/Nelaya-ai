#!/usr/bin/env bash
set -u

echo "=== CEK DATA LAOT PERIODE 15–21 JUNI 2026 ==="
for d in 2026-06-15 2026-06-16 2026-06-17 2026-06-18 2026-06-19 2026-06-20 2026-06-21
do
  echo
  echo "## $d"
  if [ -d "data/$d" ]; then
    echo "Folder LAOT: ADA"
    ls -1 data/$d
  else
    echo "Folder LAOT: BELUM ADA"
  fi

  echo "Cari kemungkinan arsip di ~/NELAYA-AI-LAB:"
  find ~/NELAYA-AI-LAB/data ~/NELAYA-AI-LAB/logs -type f 2>/dev/null \
    | grep "$d" \
    | head -20 || true
done
