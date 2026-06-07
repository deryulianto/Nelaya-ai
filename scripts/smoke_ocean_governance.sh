#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-http://127.0.0.1:8001}"

echo "=== NELAYA-AI Ocean Insight Governance Smoke Test ==="
echo "BASE: $BASE"
echo

echo "1) API health"
curl -fsS "$BASE/health" | jq .
echo

echo "2) System card latest readable"
curl -fsS "$BASE/api/v1/ocean/system-card/latest?lookback_days=7" \
| jq '.snapshot_date, .card.badge, .card.badge_status, .card.readiness_level, .card.public_status, .layers'
echo

echo "3) System card include unavailable"
curl -fsS "$BASE/api/v1/ocean/system-card/latest?lookback_days=7&include_unavailable=true" \
| jq '.snapshot_date, .card.badge, .card.badge_status, .card.readiness_level, .card.public_status'
echo

echo "4) System snapshot latest"
curl -fsS "$BASE/api/v1/ocean/system-snapshot/latest?lookback_days=7" \
| jq '.snapshot_date, .system_status, .summary'
echo

echo "5) Safe insight latest"
curl -fsS "$BASE/api/v1/ocean/safe-insight/latest?lookback_days=7" \
| jq '.snapshot_date, .publish_decision, .final_insight.title, .final_insight.readiness_level'
echo

echo "6) Lint safe text should PASS"
SAFE_RESULT=$(
curl -fsS -X POST "$BASE/api/v1/ocean/insight-lint/latest?lookback_days=7" \
  -H "Content-Type: application/json" \
  -d '{"text":"Pembacaan hari ini masih terbatas dan tidak boleh digunakan sebagai advisory operasional penuh. Data masih parsial, sebagian layer belum tersedia, dan validasi nelayan tetap penting."}' \
| jq -r '.result.passed'
)

echo "safe_text_passed=$SAFE_RESULT"

if [ "$SAFE_RESULT" != "true" ]; then
  echo "❌ Safe text lint failed"
  exit 1
fi

echo

echo "7) Lint risky text should FAIL"
RISKY_RESULT=$(
curl -fsS -X POST "$BASE/api/v1/ocean/insight-lint/latest?lookback_days=7" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hari ini peluang ikan tinggi dan nelayan disarankan melaut ke zona tangkap utama."}' \
| jq -r '.result.passed'
)

echo "risky_text_passed=$RISKY_RESULT"

if [ "$RISKY_RESULT" != "false" ]; then
  echo "❌ Risky text should not pass lint"
  exit 1
fi

echo
echo "✅ Ocean Insight Governance smoke test PASSED"
