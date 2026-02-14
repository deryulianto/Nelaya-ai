from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]

SRC_CANDIDATES = [
    ROOT / "data" / "earth" / "earth_signals_today.json",   # ✅ prioritas: generator baru
    ROOT / "data" / "earth_signals_today.json",
    ROOT / "data" / "signals_today.json",
]

DST = ROOT / "data" / "earth_signals_today.json"


def _load_if_valid(p: Path) -> dict | None:
    if not p.exists() or not p.is_file() or p.stat().st_size < 200:
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

    # valid kalau ok:true ATAU punya metrik inti
    if obj.get("ok") is True:
        return obj
    if any(k in obj for k in ["sst_c", "chl_mg_m3", "wind_ms", "wave_m", "ssh_cm", "metrics"]):
        # kalau metrik ada, anggap valid walau ok flag belum ada
        return obj
    return None


def main() -> int:
    for src in SRC_CANDIDATES:
        obj = _load_if_valid(src)
        if obj:
            DST.parent.mkdir(parents=True, exist_ok=True)
            DST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[OK] refreshed {DST} (from {src})")
            return 0

    placeholder = {
        "ok": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Placeholder signals (no valid source found). Pipeline should generate earth_signals_today.json.",
    }
    DST.write_text(json.dumps(placeholder, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[WARN] wrote placeholder: {DST} (no valid source)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
