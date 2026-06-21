#!/usr/bin/env bash
set -u

echo "=== STATUS LAOT EDISI 001 ==="
echo
echo "Folder:"
pwd
echo
echo "Data harian:"
find data -maxdepth 2 -type f | sort
echo
echo "CSV mingguan:"
if [ -f data/laot_weekly_rows_2026-06-15_2026-06-21.csv ]; then
  cat data/laot_weekly_rows_2026-06-15_2026-06-21.csv
else
  echo "Belum ada CSV mingguan."
fi
echo
echo "Notes:"
ls -lh notes 2>/dev/null || true
echo
echo "Source audit:"
tail -n 20 source-audit/source_audit_edisi001.md 2>/dev/null || true
