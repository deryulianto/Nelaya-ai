// app/trainers/retrain_fgi.py

from pathlib import Path
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.preprocessing import MinMaxScaler
import joblib
import json
from datetime import datetime

# === Path dasar proyek ===
ROOT_DIR = Path(__file__).resolve().parents[2]
LOGS_DIR = ROOT_DIR / "logs"
MODELS_DIR = ROOT_DIR / "models"

LOG_FILE = LOGS_DIR / "inference_log.csv"
BEST_PT = MODELS_DIR / "fgi_dl_best.pt"
SCALER_PKL = MODELS_DIR / "fgi_scaler.pkl"
META_PATH = MODELS_DIR / "fgi_dl.meta.json"


# === Arsitektur model sederhana ===
class SimpleNet(nn.Module):
    def __init__(self, in_features=3, hidden=8, out_features=1):
        super(SimpleNet, self).__init__()
        self.fc1 = nn.Linear(in_features, hidden)
        self.fc2 = nn.Linear(hidden, out_features)
        self.relu = nn.ReLU()

    def forward(self, x):
        x = self.relu(self.fc1(x))
        x = torch.sigmoid(self.fc2(x))
        return x


# === Fungsi utama retraining ===
def retrain_model():
    
    if not LOG_FILE.exists():
        return "❌ Tidak ditemukan file log untuk retraining."

    df = pd.read_csv(LOG_FILE)

    # --- Pastikan kolom yang dibutuhkan ada ---
    required_cols = ["temp", "sal", "chl", "FGI"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        return f"❌ Kolom hilang: {missing}"

    # --- Pembersihan data ---
    df = df.dropna(subset=required_cols)
    df["FGI"] = pd.to_numeric(df["FGI"], errors="coerce")
    df = df.dropna(subset=["FGI"])
    if df.empty:
        return "❌ Tidak ada data valid untuk pelatihan."

    # --- Siapkan input/output ---
    X = df[["temp", "sal", "chl"]].values
    y = df["FGI"].values.reshape(-1, 1)

    # --- Normalisasi ---
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X)

    # --- Setup model ---
    model = SimpleNet(in_features=3, hidden=8, out_features=1)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.01)

    X_tensor = torch.FloatTensor(X_scaled)
    y_tensor = torch.FloatTensor(y)

    # --- Training loop ---
    n_epochs = 300
    for epoch in range(n_epochs):
        optimizer.zero_grad()
        outputs = model(X_tensor)
        loss = criterion(outputs, y_tensor)
        loss.backward()
        optimizer.step()

    # --- Simpan model dan scaler ---
    torch.save(model.state_dict(), BEST_PT)
    joblib.dump(scaler, SCALER_PKL)

    meta = {
        "model_name": "NELAYA-AI FGI v0.9",
        "trained_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "input_features": ["temp", "sal", "chl"],
        "target": "FGI",
        "architecture": "SimpleNet(3→8→1)",
        "loss": float(loss.item()),
        "data_used": len(df),
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=4)

    return f"✅ Retraining selesai — loss: {loss.item():.6f} (data: {len(df)})"


# === Fungsi retrain yang bisa dipanggil langsung dari API ===
if __name__ == "__main__":
    result = retrain_model()
    print(result)



