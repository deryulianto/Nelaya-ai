#!/usr/bin/env bash
set -u

HTML="html/laot_edisi001_15-21juni2026_working.html"

if [ ! -f "$HTML" ]; then
  echo "File tidak ditemukan: $HTML"
  exit 1
fi

python3 - <<'PY'
from pathlib import Path
import re

p = Path("html/laot_edisi001_15-21juni2026_working.html")
s = p.read_text(encoding="utf-8", errors="ignore")

replacements = [
    ("LAOT — Tabloid Laut Aceh Mingguan", "NELAYA: Tabloid Laut Aceh"),
    ("LAOT - Tabloid Laut Aceh Mingguan", "NELAYA: Tabloid Laut Aceh"),
    ("LAOT — Tabloid Laut Aceh", "NELAYA: Tabloid Laut Aceh"),
    ("LAOT - Tabloid Laut Aceh", "NELAYA: Tabloid Laut Aceh"),
    ("LAOT: Tabloid Laut Aceh", "NELAYA: Tabloid Laut Aceh"),
    ("LAOT", "NELAYA"),
]

for old, new in replacements:
    s = s.replace(old, new)

# Rapikan beberapa kemungkinan subtitle
s = s.replace("Tabloid Laut Aceh Mingguan", "Tabloid Laut Aceh")

# Kalau ada title tag yang masih lama
s = re.sub(r"<title>\s*LAOT.*?</title>", "<title>NELAYA: Tabloid Laut Aceh</title>", s, flags=re.IGNORECASE|re.DOTALL)

# Sisipkan komentar branding bila belum ada
marker = "Brand publik: NELAYA: Tabloid Laut Aceh"
if marker not in s:
    s = s.replace(
        "<body>",
        "<body>\n<!-- Brand publik: NELAYA: Tabloid Laut Aceh -->",
        1
    )

p.write_text(s, encoding="utf-8")
print("OK rename brand:", p)
PY
