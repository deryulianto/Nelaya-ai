#!/usr/bin/env bash
set -u

HTML="html/laot_edisi001_15-21juni2026_working.html"

if [ ! -f "$HTML" ]; then
  echo "File tidak ditemukan: $HTML"
  exit 1
fi

python3 - <<'PY'
from pathlib import Path

p = Path("html/laot_edisi001_15-21juni2026_working.html")
s = p.read_text(encoding="utf-8", errors="ignore")

replacements = {
    "8–14 Juni 2026": "15–21 Juni 2026",
    "8-14 Juni 2026": "15–21 Juni 2026",
    "08–14 Juni 2026": "15–21 Juni 2026",
    "08-14 Juni 2026": "15–21 Juni 2026",
    "Terbit Senin, 15 Juni 2026": "Terbit Senin, 22 Juni 2026",
    "Senin, 15 Juni 2026": "Senin, 22 Juni 2026",
    "Edisi 001 · 8–14 Juni 2026": "Edisi 001 · 15–21 Juni 2026",
    "Edisi 001 | 8–14 Juni 2026": "Edisi 001 | 15–21 Juni 2026",
    "Edisi 001 — 8–14 Juni 2026": "Edisi 001 — 15–21 Juni 2026",
}

for old, new in replacements.items():
    s = s.replace(old, new)

marker = "Status: Edisi Perdana / Pilot PDF Digital"
if marker not in s:
    s = s.replace(
        "<body>",
        "<body>\n<!-- Status: Edisi Perdana / Pilot PDF Digital | Periode 15–21 Juni 2026 | Terbit 22 Juni 2026 -->",
        1
    )

p.write_text(s, encoding="utf-8")
print("OK patch identitas:", p)
PY
