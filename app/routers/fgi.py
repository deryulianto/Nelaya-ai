from __future__ import annotations
from pathlib import Path
from datetime import datetime
import json, csv
import numpy as np

# --- at top imports ---

def _to_prob(y: float) -> float:
    # jika bukan 0..1, anggap logit → sigmoid
    if y < 0.0 or y > 1.0:
        y = 1.0 / (1.0 + float(np.exp(-float(y))))
    return float(max(0.0, min(1.0, y)))

def _to_band(p: float) -> str:
    return "High" if p >= 0.75 else ("Medium" if p >= 0.50 else "Low")

from fastapi import APIRouter, HTTPException
router = APIRouter(prefix="", tags=["FGI"])

from pydantic import BaseModel, Field, validator

# ==== Direktori Proyek ====
ROOT_DIR = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT_DIR / "models"
LOGS_DIR = ROOT_DIR / "logs"

BEST_PT     = MODELS_DIR / "fgi_dl_best.pt"
SCALER_PKL  = MODELS_DIR / "fgi_scaler.pkl"
META_PATH   = MODELS_DIR / "fgi_dl.meta.json"

# ==== Optional imports ====
try:
    import torch
    import torch.nn as nn
    import joblib
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


# ==== Router ====
router = APIRouter(prefix="/fgi", tags=["FGI (Fish Growth Intelligence)"])


# ==== Model Input ====
class FGIInput(BaseModel):
    temp: float = Field(..., description="Suhu laut (°C)")
    sal: float = Field(..., description="Salinitas (PSU)")
    chl: float = Field(..., description="Klorofil-a (mg/m³)")

    @validator("temp", "sal", "chl")
    def must_be_positive(cls, v):
        if v < 0:
            raise ValueError("Nilai tidak boleh negatif")
        return v


# ==== Neural Network (sama seperti saat training) ====
class SimpleNet(nn.Module):
    def __init__(self, n_input: int = 3, n_hidden: int = 8):
        super(SimpleNet, self).__init__()
        self.fc = nn.Sequential(
            nn.Linear(n_input, n_hidden),
            nn.ReLU(),
            nn.Linear(n_hidden, 1)
        )

    def forward(self, x):
        return self.fc(x)


# ==== Load Model dan Scaler ====
MODEL, SCALER, META = None, None, None

if TORCH_AVAILABLE and BEST_PT.exists() and SCALER_PKL.exists():
    try:
        SCALER = joblib.load(SCALER_PKL)
        META = json.load(open(META_PATH))

        n_features = len(
            META.get("features") or META.get("input_features") or [3]
        )

        MODEL = SimpleNet(n_input=n_features)
        state = torch.load(BEST_PT, map_location="cpu")

        # handle saved state_dict
        if isinstance(state, dict) and "state_dict" in state:
            MODEL.load_state_dict(state["state_dict"])
        else:
            MODEL.load_state_dict(state)

        MODEL.eval()
        print(f"[INFO] ✅ Model FGI loaded successfully ({n_features} features)")

    except Exception as e:
        print(f"[WARN] ⚠️ Gagal memuat model FGI: {e}")
else:
    print("[WARN] ⚠️ Model file tidak ditemukan atau Torch belum tersedia.")


# ==== Endpoint Health Check ====
@router.get("/ping")
def ping():
    return {"status": "ok", "message": "FGI module alive"}


# ==== Endpoint Inferensi ====
from pydantic import BaseModel, Field, field_validator

class FGIRequest(BaseModel):
    temp: float = Field(..., description="Suhu laut dalam °C")
    sal: float = Field(..., description="Salinitas air laut (PSU)")
    chl: float = Field(..., description="Klorofil-a (mg/m³)")

    @field_validator("temp", "sal", "chl")
    def check_positive(cls, v, field):
        if v < 0:
            raise ValueError(f"{field.name} tidak boleh bernilai negatif")
        return v

@router.post("/predict")
def predict_fgi(data: FGIRequest):
    try:
        # --- Normalisasi input ---
        X = np.array([[data.temp, data.sal, data.chl]], dtype=np.float32)
        X_scaled = SCALER.transform(X)
        X_tensor = torch.tensor(X_scaled, dtype=torch.float32)

        with torch.no_grad():
            y_pred = MODEL(X_tensor).item()

        # --- Tentukan kategori ---
        if y_pred < 0.3:
            category = "Low"
        elif y_pred < 0.7:
            category = "Medium"
        else:
            category = "High"

        # --- Simpan log inferensi ---
        import csv, threading
        from datetime import datetime
        from app.trainers.retrain_fgi import retrain_model
        log_path = Path("logs/inference_log.csv")
        log_path.parent.mkdir(exist_ok=True)
        with open(log_path, "a", newline="") as f:
            writer = csv.writer(f)
            if f.tell() == 0:  # Kalau file baru, tulis header
                writer.writerow(["timestamp", "temp", "sal", "chl", "FGI", "category"])
            writer.writerow([datetime.now().isoformat(), data.temp, data.sal, data.chl, round(float(y_pred), 4), category])

        # --- Jalankan retrain otomatis di background ---
        threading.Thread(target=retrain_model, kwargs={"threshold": 10}, daemon=True).start()

        # --- Return hasil ---
        return {"FGI_Score": round(float(y_pred), 4), "Category": category}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#baru v0.9
from app.trainers.retrain_fgi import retrain_model

@router.post("/fgi/retrain")
def retrain_from_log():
    """
    Melatih ulang model FGI menggunakan data dari logs/inference_log.csv
    """
    try:
        result = retrain_model()
        return {"status": "success", "message": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import numpy as np
def _to_prob(y):
    if y < 0.0 or y > 1.0:
        y = 1.0 / (1.0 + np.exp(-float(y)))
    return float(max(0.0, min(1.0, y)))

@router.post("/score")
def score(payload: dict):
    data = payload.get("data", {})
    #...hitung skor ....
    return {"score": 0.0, "ok": True}
