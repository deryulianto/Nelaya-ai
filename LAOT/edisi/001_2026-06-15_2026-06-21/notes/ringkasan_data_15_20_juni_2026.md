# Ringkasan Data LAOT 15–20 Juni 2026

## Status Sumber
- 15–18 Juni: archive backfill dari grid/hotspot summary.
- 19–20 Juni: capture harian LAOT dari endpoint API.
- 21 Juni: menunggu capture Minggu.

## Catatan Guardrail
- Skor 15–18 Juni berasal dari score_mean_v011 grid summary, bukan FGI publik harian.
- Skor 19–20 Juni berasal dari endpoint insight_today dan masih perlu rekonsiliasi dengan FGI publik.
- Karena itu, angka skor tidak dijadikan klaim utama “peluang ikan”, tetapi dibaca sebagai indikator model internal.
- Hotspot dibaca sebagai kandidat pemantauan, bukan titik pasti penangkapan.

## Pola Sementara
15 Juni:
- zones_count = 0
- top hotspot cell: ACEH_067_043
- hotspot_core, slope_200_1000m
- mean score/top score sekitar 0.6551

16 Juni:
- zones_count = 3
- top zone: HZ20260616_N001
- operational_core_zone
- 440 sel
- pusat 97.138039 BT / 6.486153 LU
- depth mean 795.71 m
- mean operational score 0.8363
- confidence 0.9903

17 Juni:
- zones_count = 6
- top zone: HZ20260617_N001
- operational_core_zone
- pusat 94.91481 BT / 5.257366 LU
- depth mean 1675.69 m
- mean operational score 0.7563
- confidence 0.93

18 Juni:
- zones_count = 1
- top zone: HZ20260618_N001
- operational_strong_zone
- pusat 98.776325 BT / 6.143687 LU
- depth mean 87.84 m
- shelf_50_200m
- mean operational score 0.7249
- confidence 0.9151

19 Juni:
- capture harian aktif
- zones_count = 1
- top zone: HZ20260619_N001
- operational_strong_zone
- SST 30.47 C, CHL 0.277, wave 1.19 m, wind 2.91 m/s
- depth mean 87.84 m
- shelf_50_200m

20 Juni:
- capture harian aktif
- zones_count = 1
- top zone: HZ20260620_N001
- operational_core_zone
- SST 30.44 C, CHL 0.124, wave 1.23 m, wind 3.12 m/s
- depth mean 1893.89 m
- deep_1000_3000m

## Kesimpulan Sementara
Minggu 15–20 Juni memperlihatkan sinyal spasial yang dinamis. Zona kuat muncul pada 16–17 Juni, menyempit pada 18–19 Juni, lalu kembali menguat pada 20 Juni tetapi bergeser ke laut dalam. LAOT membacanya sebagai perubahan ruang kandidat pemantauan, bukan sebagai kepastian lokasi penangkapan.
