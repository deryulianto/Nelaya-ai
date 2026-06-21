#!/usr/bin/env python3
import csv
from pathlib import Path
from statistics import mean

CSV = Path("data/laot_weekly_rows_2026-06-15_2026-06-21.csv")
OUT = Path("notes/ringkasan_final_15_21_juni_2026.md")

rows = list(csv.DictReader(CSV.open(encoding="utf-8")))

def fnum(v):
    try:
        if v in ("", None):
            return None
        return float(v)
    except Exception:
        return None

zones_days = [r for r in rows if fnum(r.get("zones_count")) and fnum(r.get("zones_count")) > 0]
core_days = [r for r in rows if "core" in (r.get("zone_level") or "")]
strong_days = [r for r in rows if "strong" in (r.get("zone_level") or "")]

scores = [fnum(r.get("mean_operational_score")) for r in rows if fnum(r.get("mean_operational_score")) is not None]
conf = [fnum(r.get("mean_confidence")) for r in rows if fnum(r.get("mean_confidence")) is not None]
depths = [fnum(r.get("depth_mean_m")) for r in rows if fnum(r.get("depth_mean_m")) is not None]

max_score_row = None
for r in rows:
    val = fnum(r.get("mean_operational_score"))
    if val is None:
        continue
    if max_score_row is None or val > fnum(max_score_row.get("mean_operational_score")):
        max_score_row = r

deep_days = [r for r in rows if "deep" in (r.get("depth_class") or "")]
shelf_days = [r for r in rows if "shelf" in (r.get("depth_class") or "")]
slope_days = [r for r in rows if "slope" in (r.get("depth_class") or "")]

lines = []
lines.append("# Ringkasan Final LAOT Edisi 001")
lines.append("## Periode 15-21 Juni 2026")
lines.append("")
lines.append("## Status Data")
lines.append(f"- Total hari terbaca: {len(rows)}")
lines.append(f"- Hari dengan zona/sinyal hotspot: {len(zones_days)}")
lines.append(f"- Hari dengan operational_core_zone: {len(core_days)}")
lines.append(f"- Hari dengan operational_strong_zone: {len(strong_days)}")
lines.append("- 15-18 Juni: archive backfill dari grid/hotspot summary.")
lines.append("- 19-21 Juni: capture harian LAOT dari endpoint API, bila 21 Juni sudah masuk.")
lines.append("")
lines.append("## Statistik Ringkas")
if scores:
    lines.append(f"- Rata-rata mean operational score: {mean(scores):.4f}")
if conf:
    lines.append(f"- Rata-rata confidence zona/top signal: {mean(conf):.4f}")
if depths:
    lines.append(f"- Rata-rata kedalaman top signal: {mean(depths):.2f} m")
if max_score_row:
    lines.append(
        f"- Hari dengan mean operational score tertinggi: {max_score_row['capture_date']} "
        f"({max_score_row['top_zone']}, {max_score_row['zone_level']}, "
        f"score {float(max_score_row['mean_operational_score']):.4f})"
    )
lines.append("")
lines.append("## Kelas Ruang")
lines.append(f"- Hari dominan shelf: {len(shelf_days)}")
lines.append(f"- Hari dominan slope: {len(slope_days)}")
lines.append(f"- Hari dominan deep: {len(deep_days)}")
lines.append("")
lines.append("## Tabel Harian")
for r in rows:
    lines.append(
        f"- {r['capture_date']}: {r.get('top_zone') or '-'} | "
        f"{r.get('zone_level') or '-'} | zones_count={r.get('zones_count') or '-'} | "
        f"depth={r.get('depth_mean_m') or '-'} m | "
        f"class={r.get('depth_class') or '-'} | "
        f"score={r.get('mean_operational_score') or '-'} | "
        f"quality={r.get('grid_quality') or '-'}"
    )

lines.append("")
lines.append("## Guardrail Redaksi")
lines.append("- Hotspot dibaca sebagai kandidat pemantauan, bukan titik pasti penangkapan.")
lines.append("- Skor 15-18 Juni berasal dari archive backfill grid/hotspot, bukan capture API harian.")
lines.append("- Skor 19-21 Juni tetap perlu dibaca sebagai indikator internal dan tidak dijadikan klaim tunggal.")
lines.append("- Informasi LAOT bukan peringatan resmi, bukan instruksi navigasi, dan bukan jaminan hasil tangkapan.")

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"OK -> {OUT}")
print(OUT.read_text(encoding="utf-8"))
