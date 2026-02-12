from pathlib import Path
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]

# Router kamu membaca salah satu dari ini:
OUT_A = ROOT / "data" / "earth_signals_today.json"
OUT_B = ROOT / "data" / "earth" / "earth_signals_today.json"

payload = {
    "ok": True,
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "note": "Auto-generated placeholder to keep Nelaya daily pipeline alive. Will be replaced by real signals pipeline.",
    "signals": [],
}

for out in (OUT_A, OUT_B):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK:", out)
