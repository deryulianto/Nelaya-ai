# Source Audit LAOT Edisi 001

Periode: 15–21 Juni 2026
Rilis: Senin, 22 Juni 2026

| Bagian | Sumber | Status | Catatan |
|---|---|---|---|
| Dashboard Laut Hari Ini | NELAYA-AI Dashboard/API | Perlu capture | Ambil data harian |
| Insights Harian | nelaya-ai.com/insights | Perlu ringkas | Ambil 7 hari |
| FGI | FGI Lab / Insight | Perlu capture | FGI dan current-aware FGI |
| Grid Hotspot | Grid Dashboard | Perlu capture | Baca sebagai indikatif |
| Risk | Risk Page/API | Perlu capture | Bukan peringatan resmi |
| GIS | GIS Page | Perlu screenshot | Untuk visual tabloid |
| Biodiversity | Ocean Intelligence | Perlu capture | Guardrail biodiversitas |
| Tuna Depth | Ocean Intelligence | Perlu capture | Kandidat layer, bukan kepastian |
| Harga Pasar | PPI/Pasar lapangan | Belum tersedia | Jangan isi angka tanpa verifikasi |
| Sponsor | Manual | Belum ada | Isi Ruang Kolaborasi Dibuka |
| Yayasan | Manual | Perlu narasi | Profil + ruang amanah |

## Update Jumat, 19 Juni 2026

Capture berhasil untuk:
- insight_today.json
- grid_dashboard_today.json
- grid_brief_today.json
- grid_health.json
- ocean_health_public_card_today.json
- ocean_health_summary_today.json

Catatan kualitas:
- Capture dilakukan pada 2026-06-19.
- insight_today.json masih membawa insight_date 2026-06-18.
- Data ini dicatat sebagai data tersedia dengan catatan lag D-1.
- FGI final dari endpoint insight_today bernilai 0.193. Angka ini belum langsung dipakai sebagai FGI publik karena perlu rekonsiliasi skala dengan narasi insight/FGI Lab.
- Grid Hotspot dapat dipakai untuk narasi indikatif karena struktur zona, quality, confidence, dan guardrail sudah jelas.
- Ocean Health Watch dapat dipakai sebagai catatan lingkungan awal, bukan label risiko publik.

## Update Jumat, 19 Juni 2026

Capture berhasil untuk:
- insight_today.json
- grid_dashboard_today.json
- grid_brief_today.json
- grid_health.json
- ocean_health_public_card_today.json
- ocean_health_summary_today.json

Catatan kualitas:
- Capture dilakukan pada 2026-06-19.
- insight_today.json masih membawa insight_date 2026-06-18.
- Data ini dicatat sebagai data tersedia dengan catatan lag D-1.
- FGI final dari endpoint insight_today bernilai 0.193. Angka ini belum langsung dipakai sebagai FGI publik karena perlu rekonsiliasi skala dengan narasi insight/FGI Lab.
- Grid Hotspot dapat dipakai untuk narasi indikatif karena struktur zona, quality, confidence, dan guardrail sudah jelas.
- Ocean Health Watch dapat dipakai sebagai catatan lingkungan awal, bukan label risiko publik.

## Update Sabtu, 20 Juni 2026

Capture berhasil untuk:
- insight_today.json
- grid_dashboard_today.json
- grid_brief_today.json
- grid_health.json
- ocean_health_public_card_today.json
- ocean_health_summary_today.json

Catatan kualitas:
- Capture dilakukan pada 2026-06-20.
- insight_today.json masih membawa insight_date 2026-06-19.
- Data dicatat sebagai data tersedia dengan catatan lag D-1.
- FGI final dari endpoint insight_today bernilai 0.198. Angka ini belum langsung dipakai sebagai FGI publik karena perlu rekonsiliasi skala dengan narasi insight/FGI Lab.
- Grid Hotspot membaca 1 zona, HZ20260620_N001, level operational_core_zone.
- Zona berada pada laut dalam, depth_mean_m sekitar 1893.89 m, kelas deep_1000_3000m.
- Mean operational score 0.8027 dan mean confidence 1.0.
- Ocean Health Watch tetap belum siap untuk label risiko publik.

## Update Sabtu, 20 Juni 2026

Capture berhasil untuk:
- insight_today.json
- grid_dashboard_today.json
- grid_brief_today.json
- grid_health.json
- ocean_health_public_card_today.json
- ocean_health_summary_today.json

Catatan kualitas:
- Capture dilakukan pada 2026-06-20.
- insight_today.json masih membawa insight_date 2026-06-19.
- Data dicatat sebagai data tersedia dengan catatan lag D-1.
- FGI final dari endpoint insight_today bernilai 0.198. Angka ini belum langsung dipakai sebagai FGI publik karena perlu rekonsiliasi skala dengan narasi insight/FGI Lab.
- Grid Hotspot membaca 1 zona, HZ20260620_N001, level operational_core_zone.
- Zona berada pada laut dalam, depth_mean_m sekitar 1893.89 m, kelas deep_1000_3000m.
- Mean operational score 0.8027 dan mean confidence 1.0.
- Ocean Health Watch tetap belum siap untuk label risiko publik.

## Temuan Backfill Sabtu, 20 Juni 2026

Pemeriksaan awal menunjukkan arsip data 15–18 Juni 2026 tersedia di folder utama NELAYA-AI-LAB, walaupun belum masuk ke folder kerja LAOT.

Sumber yang ditemukan:
- data/grid/daily/grid_scoring_YYYY-MM-DD_calibrated_v011_summary.json
- data/grid/hotspots/grid_hotspot_zones_YYYY-MM-DD_v012_summary.json
- data/grid/hotspots/grid_hotspot_YYYY-MM-DD_v010_summary.json
- data/marketplace_insights/YYYY-MM-DD.json
- data/time_series/aceh/banda_aceh_aceh_besar/

Catatan:
- Data 15–18 Juni akan diperlakukan sebagai backfill arsip.
- Backfill hanya akan dipakai setelah struktur JSON dicek.
- Jika field tidak konsisten dengan capture harian LAOT, data akan masuk sebagai catatan konteks, bukan angka utama.

## Backfill Arsip 15–18 Juni 2026

Backfill dibuat untuk tanggal 15–18 Juni 2026 dari arsip grid/hotspot utama NELAYA-AI-LAB.

Prinsip:
- Backfill tidak dianggap sebagai capture API harian LAOT.
- Backfill dipakai sebagai konteks mingguan.
- Field SST/CHL/wave/wind hanya diisi bila tersedia aman dari marketplace signals/snapshot.
- Grid/hotspot dipakai dari summary resmi arsip harian.
- Jika aggregated zone tidak tersedia, top hotspot cell hanya dibaca sebagai indikasi sel, bukan zona operasional.

Catatan:
- 15 Juni memiliki grid summary dan top hotspot, tetapi zones_count = 0.
- 16 Juni memiliki 3 aggregated zones.
- 17 Juni memiliki 6 aggregated zones.
- 18 Juni memiliki 1 aggregated zone.
