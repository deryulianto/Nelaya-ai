#!/usr/bin/env bash
set -u

TODAY="${1:-$(date +%F)}"
INDIR="data/${TODAY}"
OUT_JSON="${INDIR}/laot_daily_row.json"
OUT_MD="${INDIR}/laot_daily_note.md"

if [ ! -d "$INDIR" ]; then
  echo "Folder data tidak ditemukan: $INDIR"
  exit 1
fi

echo "=== Extract LAOT Day: $TODAY ==="

jq -n \
  --slurpfile insight "$INDIR/insight_today.json" \
  --slurpfile grid "$INDIR/grid_dashboard_today.json" \
  --slurpfile brief "$INDIR/grid_brief_today.json" \
  --slurpfile health "$INDIR/ocean_health_public_card_today.json" '
{
  capture_date: "'"$TODAY"'",
  insight_date: ($insight[0].date // null),

  ocean_signals: {
    sst: ($insight[0].signals.sst // null),
    chl: ($insight[0].signals.chl // null),
    wave: ($insight[0].signals.wave // null),
    wind: ($insight[0].signals.wind // null),
    sst_class: ($insight[0].classification.sst // null),
    chl_class: ($insight[0].classification.chl // null),
    wave_class: ($insight[0].classification.wave // null),
    wind_class: ($insight[0].classification.wind // null)
  },

  fgi: {
    core: ($insight[0].fgi.core // null),
    final: ($insight[0].fgi.final // null),
    final_0_100: (($insight[0].fgi.final // 0) * 100 | round),
    confidence: ($insight[0].fgi.confidence // null),
    iod_modifier: ($insight[0].fgi.iod_modifier // null),
    local_flags: ($insight[0].fgi.explain.local_flags // null),
    reasons: ($insight[0].fgi.explain.reasons // [])
  },

  insight_summary: ($insight[0].insight.summary // null),
  insight_risks: ($insight[0].insight.risks // null),

  climate_context: {
    enso_status: ($insight[0].enso.status // null),
    enso_nino34: ($insight[0].enso.nino34 // null),
    enso_date: ($insight[0].enso.date // null),
    iod_status: ($insight[0].iod.status // null),
    iod_dmi: ($insight[0].iod.dmi // null),
    iod_strength: ($insight[0].iod.strength // null),
    iod_date: ($insight[0].iod.date // null)
  },

  grid: {
    dashboard_level: ($grid[0].dashboard_level // null),
    dashboard_headline: ($grid[0].dashboard_headline // null),
    quality_label: ($grid[0].quality.quality_label // null),
    quality_note: ($grid[0].quality.public_quality_note // null),
    hotspot_status: ($grid[0].hotspot_status // null),
    zones_count: ($grid[0].zones.zones_count // $brief[0].zones_count // null),
    top_zone: ($grid[0].zones.top_zones[0] // $brief[0].top_zones[0] // null),
    persistence_w7_status: ($grid[0].persistence.w7.status_label // null),
    persistence_w7_reading: ($grid[0].persistence.w7.public_reading // null)
  },

  ocean_health: {
    headline: ($health[0].headline // null),
    status_label: ($health[0].status_label // null),
    public_facts: ($health[0].public_facts // []),
    what_this_means: ($health[0].what_this_means // null),
    do_not_interpret_as: ($health[0].do_not_interpret_as // [])
  }
}
' > "$OUT_JSON"

echo "OK JSON -> $OUT_JSON"

cat > "$OUT_MD" <<MD
# LAOT Daily Note — $TODAY

## Status Capture
- Capture date: $TODAY
- Insight date: $(jq -r '.insight_date // "-"' "$OUT_JSON")

## Ocean Signals
- SST: $(jq -r '.ocean_signals.sst // "-"' "$OUT_JSON") | class: $(jq -r '.ocean_signals.sst_class // "-"' "$OUT_JSON")
- CHL: $(jq -r '.ocean_signals.chl // "-"' "$OUT_JSON") | class: $(jq -r '.ocean_signals.chl_class // "-"' "$OUT_JSON")
- Wave: $(jq -r '.ocean_signals.wave // "-"' "$OUT_JSON") | class: $(jq -r '.ocean_signals.wave_class // "-"' "$OUT_JSON")
- Wind: $(jq -r '.ocean_signals.wind // "-"' "$OUT_JSON") | class: $(jq -r '.ocean_signals.wind_class // "-"' "$OUT_JSON")

## FGI
- FGI final: $(jq -r '.fgi.final // "-"' "$OUT_JSON")
- FGI 0–100 sementara: $(jq -r '.fgi.final_0_100 // "-"' "$OUT_JSON")
- Confidence: $(jq -r '.fgi.confidence // "-"' "$OUT_JSON")
- Catatan: cek konsistensi skala FGI sebelum dimuat sebagai angka utama LAOT.

## Grid Hotspot
- Dashboard level: $(jq -r '.grid.dashboard_level // "-"' "$OUT_JSON")
- Headline: $(jq -r '.grid.dashboard_headline // "-"' "$OUT_JSON")
- Quality: $(jq -r '.grid.quality_label // "-"' "$OUT_JSON")
- Zones count: $(jq -r '.grid.zones_count // "-"' "$OUT_JSON")
- Top zone: $(jq -r '.grid.top_zone.zone_id // "-"' "$OUT_JSON")
- Zone level: $(jq -r '.grid.top_zone.zone_level // "-"' "$OUT_JSON")
- Center: $(jq -r '(.grid.top_zone.lon_center|tostring) + " BT / " + (.grid.top_zone.lat_center|tostring) + " LU"' "$OUT_JSON" 2>/dev/null || echo "-")
- Mean operational score: $(jq -r '.grid.top_zone.mean_operational_score // "-"' "$OUT_JSON")
- Mean confidence: $(jq -r '.grid.top_zone.mean_overall_confidence // "-"' "$OUT_JSON")

## Ocean Health
- Status: $(jq -r '.ocean_health.status_label // "-"' "$OUT_JSON")
- Headline: $(jq -r '.ocean_health.headline // "-"' "$OUT_JSON")

## Draft Narasi Aman
Grid Hotspot membaca satu zona operasional kuat pada $TODAY, dengan mutu data yang tetap harus dibaca secara hati-hati. Zona ini merupakan kandidat pemantauan, bukan titik pasti penangkapan.

Ocean Health Watch sudah aktif sebagai sistem pengamatan awal, tetapi belum cukup untuk label risiko publik karena laporan belum terverifikasi dan belum ada sampel mikroplastik terverifikasi.
MD

echo "OK MD -> $OUT_MD"
echo
cat "$OUT_MD"
