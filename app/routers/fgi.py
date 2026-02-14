from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import csv
import threading
from typing import Any, Dict, Optional, Tuple
import inspect
import time


import numpy as np
from fastapi import APIRouter, HTTPException

# --- pydantic v1/v2 compatibility ---
try:
    # pydantic v2
    from pydantic import BaseModel, Field, field_validator
except Exception:
    # pydantic v1 fallback
    from pydantic import BaseModel, Field, validator as field_validator  # type: ignore


# ==== Direktori Proyek ====
ROOT_DIR = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT_DIR / "models"
LOGS_DIR = ROOT_DIR / "logs"

BEST_PT = MODELS_DIR / "fgi_dl_best.pt"
SCALER_PKL = MODELS_DIR / "fgi_scaler.pkl"
META_PATH = MODELS_DIR / "fgi_dl.meta.json"

INFER_LOG = LOGS_DIR / "inference_log.csv"

_RETRAIN_LOCK = threading.Lock()
_LAST_RETRAIN_TS = 0.0

def _kick_retrain_async(threshold: int = 10, cooldown_s: int = 3600):
    """Start retrain async max 1x per cooldown (default 1 jam)."""
    global _LAST_RETRAIN_TS
    now = time.time()
    with _RETRAIN_LOCK:
        if now - _LAST_RETRAIN_TS < cooldown_s:
            return
        _LAST_RETRAIN_TS = now

    try:
        from app.trainers.retrain_fgi import retrain_model

        kwargs = {}
        try:
            if "threshold" in inspect.signature(retrain_model).parameters:
                kwargs["threshold"] = threshold
        except Exception:
            # kalau signature gagal dibaca, jalan tanpa kwargs
            kwargs = {}

        threading.Thread(target=retrain_model, kwargs=kwargs, daemon=True).start()
    except Exception:
        # retrain optional: jangan ganggu prediksi
        pass



def _to_prob(y: float) -> float:
    """Kalau output bukan 0..1, anggap logit -> sigmoid."""
    y = float(y)
    if y < 0.0 or y > 1.0:
        y = 1.0 / (1.0 + float(np.exp(-y)))
    return float(max(0.0, min(1.0, y)))


def _to_band(p: float) -> str:
    return "High" if p >= 0.75 else ("Medium" if p >= 0.50 else "Low")


# ==== Optional imports (Torch & joblib) ====
TORCH_AVAILABLE = False
torch = None
nn = None
joblib = None

try:
    import torch as _torch  # type: ignore
    import torch.nn as _nn  # type: ignore
    import joblib as _joblib  # type: ignore

    torch = _torch
    nn = _nn
    joblib = _joblib
    TORCH_AVAILABLE = True
except Exception:
    TORCH_AVAILABLE = False


# ==== Router ====
router = APIRouter(prefix="/fgi", tags=["FGI (Fish Growth Intelligence)"])


# ==== Model Input ====
class FGIRequest(BaseModel):
    temp: float = Field(..., description="Suhu laut dalam °C")
    sal: float = Field(..., description="Salinitas air laut (PSU)")
    chl: float = Field(..., description="Klorofil-a (mg/m³)")

    @field_validator("temp", "sal", "chl")
    def check_positive(cls, v, *args, **kwargs):
        if v < 0:
            raise ValueError("Nilai tidak boleh negatif")
        return v


# ==== Neural Network (sesuai training) ====
if TORCH_AVAILABLE:
    class SimpleNet(nn.Module):  # type: ignore
        def __init__(self, n_input: int = 3, n_hidden: int = 8):
            super().__init__()
            self.fc = nn.Sequential(  # type: ignore
                nn.Linear(n_input, n_hidden),  # type: ignore
                nn.ReLU(),  # type: ignore
                nn.Linear(n_hidden, 1),  # type: ignore
            )

        def forward(self, x):
            return self.fc(x)
else:
    SimpleNet = object  # type: ignore


def _extract_state_dict(ckpt: Any) -> Dict[str, Any]:
    # support: raw state_dict, atau checkpoint {"state_dict": ...}
    if isinstance(ckpt, dict):
        if "state_dict" in ckpt and isinstance(ckpt["state_dict"], dict):
            return ckpt["state_dict"]
        if "model_state_dict" in ckpt and isinstance(ckpt["model_state_dict"], dict):
            return ckpt["model_state_dict"]
        return ckpt
    raise TypeError(f"Unsupported checkpoint type: {type(ckpt)}")


def _strip_module_prefix(state: Dict[str, Any]) -> Dict[str, Any]:
    # handle DataParallel: "module.xxx"
    if any(k.startswith("module.") for k in state.keys()):
        return {k.replace("module.", "", 1): v for k, v in state.items()}
    return state


def _compat_rename_fc_keys(model: Any, state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Kompatibilitas:
    - model baru: fc Sequential -> keys "fc.0.*", "fc.2.*"
    - model lama: "fc1.*", "fc2.*"
    """
    model_keys = set(model.state_dict().keys())
    needs_new = ("fc.0.weight" in model_keys) or ("fc.2.weight" in model_keys)
    has_old = ("fc1.weight" in state) and ("fc2.weight" in state)

    if needs_new and has_old:
        state = dict(state)
        state["fc.0.weight"] = state.pop("fc1.weight")
        state["fc.0.bias"] = state.pop("fc1.bias")
        state["fc.2.weight"] = state.pop("fc2.weight")
        state["fc.2.bias"] = state.pop("fc2.bias")
    return state


def _load_meta(meta_path: Path) -> Dict[str, Any]:
    if not meta_path.exists():
        return {}
    with meta_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ==== Load Model dan Scaler ====
MODEL = None
SCALER = None
META: Dict[str, Any] = {}

if TORCH_AVAILABLE and BEST_PT.exists() and SCALER_PKL.exists():
    try:
        SCALER = joblib.load(SCALER_PKL)  # type: ignore
        META = _load_meta(META_PATH)

        feats = META.get("features") or META.get("input_features")
        if isinstance(feats, list) and len(feats) > 0:
            n_features = len(feats)
        else:
            n_features = 3

        MODEL = SimpleNet(n_input=n_features)  # type: ignore

        ckpt = torch.load(BEST_PT, map_location="cpu")  # type: ignore
        state = _extract_state_dict(ckpt)
        state = _strip_module_prefix(state)
        state = _compat_rename_fc_keys(MODEL, state)

        # strict=True harusnya sekarang sukses (warning hilang)
        MODEL.load_state_dict(state, strict=True)  # type: ignore
        MODEL.eval()  # type: ignore
        print(f"[INFO] ✅ Model FGI loaded successfully ({n_features} features)")

    except Exception as e:
        MODEL = None
        SCALER = None
        print(f"[WARN] ⚠️ Gagal memuat model FGI: {e}")
else:
    print("[WARN] ⚠️ Model file tidak ditemukan atau Torch belum tersedia.")


# ==== Endpoint Health Check ====
@router.get("/ping")
def ping():
    return {
        "status": "ok",
        "message": "FGI module alive",
        "torch_available": TORCH_AVAILABLE,
        "model_loaded": MODEL is not None and SCALER is not None,
    }


# ==== Endpoint Inferensi ====
@router.post("/predict")
def predict_fgi(data: FGIRequest):
    if not TORCH_AVAILABLE or MODEL is None or SCALER is None:
        raise HTTPException(status_code=503, detail="FGI model/scaler belum siap.")

    try:
        # --- Normalisasi input ---
        X = np.array([[data.temp, data.sal, data.chl]], dtype=np.float32)
        X_scaled = SCALER.transform(X)
        X_tensor = torch.tensor(X_scaled, dtype=torch.float32)  # type: ignore

        with torch.no_grad():  # type: ignore
            raw = float(MODEL(X_tensor).item())  # type: ignore

        p = _to_prob(raw)
        category = _to_band(p)

        # --- Simpan log inferensi ---
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        is_new = not INFER_LOG.exists()
        with INFER_LOG.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(["timestamp", "temp", "sal", "chl", "raw", "prob", "category"])
            w.writerow([datetime.now().isoformat(), data.temp, data.sal, data.chl, round(raw, 6), round(p, 6), category])

        # --- (opsional) retrain di background ---
        # NOTE: ini bisa berat kalau tiap request; tapi aku biarkan seperti konsep kamu.
        try:
            from app.trainers.retrain_fgi import retrain_model
            threading.Thread(target=retrain_model, daemon=True).start()
        except Exception:
            # retrain optional; jangan ganggu prediksi
            pass

        return {"FGI_Score": round(p, 4), "Category": category, "raw": round(raw, 6)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==== Retrain Endpoint (FIX path biar tidak dobel /fgi/fgi/...) ====
@router.post("/retrain")
def retrain_from_log():
    """
    Melatih ulang model FGI menggunakan data dari logs/inference_log.csv
    """
    try:
        from app.trainers.retrain_fgi import retrain_model
        result = retrain_model()
        return {"status": "success", "message": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==== Score placeholder ====
@router.post("/score")
def score(payload: dict):
    # ...hitung skor (placeholder)...
    return {"score": 0.0, "ok": True}
