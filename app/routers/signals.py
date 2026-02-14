from __future__ import annotations

from pathlib import Path
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1/signals", tags=["Signals"])
ROOT = Path(__file__).resolve().parents[2]

# ✅ prioritas: file yang "ok:true" (hasil pipeline terbaru)
CANDIDATES = [
    ROOT / "data" / "earth" / "earth_signals_today.json",  # paling utama
    ROOT / "data" / "signals_today.json",
    ROOT / "data" / "earth_signals_today.json",
]

def _is_valid(p: Path) -> bool:
    try:
        if not p.exists():
            return False
        obj = json.loads(p.read_text(encoding="utf-8"))
        if obj.get("ok") is not True:
            return False
        # minimal harus punya salah satu angka yang dipakai UI
        if any(k in obj for k in ("sst_c", "chl_mg_m3", "wind_ms", "wave_m", "ssh_cm", "sal_psu")):
            return True
        # atau punya struktur metrics.sst.value
        m = obj.get("metrics") or {}
        return isinstance(m, dict) and ("sst" in m or "chl" in m or "wind" in m or "wave" in m or "ssh" in m or "sal" in m)
    except Exception:
        return False

def _pick_file() -> Path:
    # 1) pilih yang valid dulu
    for p in CANDIDATES:
        if _is_valid(p):
            return p
    # 2) kalau tidak ada valid, pilih yang ada (untuk debug)
    for p in CANDIDATES:
        if p.exists():
            return p
    return CANDIDATES[0]

@router.get("/today")
def today(trace: str | None = Query(default=None)):
    fp = _pick_file()
    if not fp.exists():
        raise HTTPException(status_code=404, detail=f"Missing signals file: {fp}")
    payload = json.loads(fp.read_text(encoding="utf-8"))
    payload.setdefault("meta", {})
    payload["meta"].setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    payload["meta"]["picked_file"] = str(fp)
    if trace:
        payload["meta"]["trace"] = trace
    return payload

@router.get("/ping")
def ping():
    return {"ok": True, "service": "signals"}
