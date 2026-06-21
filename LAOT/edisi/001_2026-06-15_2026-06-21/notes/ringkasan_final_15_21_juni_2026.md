# Ringkasan Final LAOT Edisi 001
## Periode 15-21 Juni 2026

## Status Data
- Total hari terbaca: 7
- Hari dengan zona/sinyal hotspot: 6
- Hari dengan operational_core_zone: 4
- Hari dengan operational_strong_zone: 3
- 15-18 Juni: archive backfill dari grid/hotspot summary.
- 19-21 Juni: capture harian LAOT dari endpoint API, bila 21 Juni sudah masuk.

## Statistik Ringkas
- Rata-rata mean operational score: 0.7428
- Rata-rata confidence zona/top signal: 0.9458
- Rata-rata kedalaman top signal: 927.76 m
- Hari dengan mean operational score tertinggi: 2026-06-16 (HZ20260616_N001, operational_core_zone, score 0.8363)

## Kelas Ruang
- Hari dominan shelf: 2
- Hari dominan slope: 1
- Hari dominan deep: 4

## Tabel Harian
- 2026-06-15: ACEH_067_043 | hotspot_core | zones_count=0 | depth=772.0 m | class=slope_200_1000m | score=0.6551 | quality=archive_backfill_grid_summary
- 2026-06-16: HZ20260616_N001 | operational_core_zone | zones_count=3 | depth=795.71 m | class=deep_1000_3000m | score=0.8363 | quality=archive_backfill_grid_summary
- 2026-06-17: HZ20260617_N001 | operational_core_zone | zones_count=6 | depth=1675.69 m | class=deep_1000_3000m | score=0.7563 | quality=archive_backfill_grid_summary
- 2026-06-18: HZ20260618_N001 | operational_strong_zone | zones_count=1 | depth=87.84 m | class=shelf_50_200m | score=0.7249 | quality=archive_backfill_grid_summary
- 2026-06-19: HZ20260619_N001 | operational_strong_zone | zones_count=1 | depth=87.84 m | class=shelf_50_200m | score=0.7249 | quality=usable_with_caution
- 2026-06-20: HZ20260620_N001 | operational_core_zone | zones_count=1 | depth=1893.89 m | class=deep_1000_3000m | score=0.8027 | quality=usable_with_caution
- 2026-06-21: HZ20260621_N001 | operational_strong_zone | zones_count=3 | depth=1181.36 m | class=deep_1000_3000m | score=0.6994 | quality=usable_with_caution

## Guardrail Redaksi
- Hotspot dibaca sebagai kandidat pemantauan, bukan titik pasti penangkapan.
- Skor 15-18 Juni berasal dari archive backfill grid/hotspot, bukan capture API harian.
- Skor 19-21 Juni tetap perlu dibaca sebagai indikator internal dan tidak dijadikan klaim tunggal.
- Informasi LAOT bukan peringatan resmi, bukan instruksi navigasi, dan bukan jaminan hasil tangkapan.
