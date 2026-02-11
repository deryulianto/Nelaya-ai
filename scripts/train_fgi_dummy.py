# ===============================================
# NELAYA-AI LAB: Dummy Fish Growth Index Model v0.1
# ===============================================
import torch
import torch.nn as nn
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import joblib, json
from pathlib import Path

# === Path setup ===
ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
MODELS.mkdir(exist_ok=True)

MODEL_PATH = MODELS / "fgi_dl_best.pt"
SCALER_PATH = MODELS / "fgi_scaler.pkl"
META_PATH = MODELS / "fgi_dl.meta.json"

# === 1. Generate dummy dataset ===
np.random.seed(42)
n = 500
temp = np.random.uniform(24, 32, n)
sal  = np.random.uniform(28, 36, n)
chl  = np.random.uniform(0.1, 5.0, n)
target = (0.4 * (temp - 24)/8 + 0.4 * (sal - 28)/8 + 0.2 * (chl/5))  # dummy formula

X = np.vstack([temp, sal, chl]).T
y = target.reshape(-1, 1)

# === 2. Scaling ===
scaler = MinMaxScaler()
X_scaled = scaler.fit_transform(X)
joblib.dump(scaler, SCALER_PATH)

# === 3. Model definition ===
class SimpleNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Sequential(
            nn.Linear(3, 8),
            nn.ReLU(),
            nn.Linear(8, 1)
        )
    def forward(self, x):
        return self.fc(x)

model = SimpleNet()

# === 4. Training ===
criterion = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

X_tensor = torch.tensor(X_scaled, dtype=torch.float32)
y_tensor = torch.tensor(y, dtype=torch.float32)

for epoch in range(500):
    optimizer.zero_grad()
    outputs = model(X_tensor)
    loss = criterion(outputs, y_tensor)
    loss.backward()
    optimizer.step()

print(f"✅ Training done | Final loss: {loss.item():.6f}")

# === 5. Save model ===
torch.save(model.state_dict(), MODEL_PATH)

# === 6. Save metadata ===
meta = {
    "model_name": "NELAYA-AI FGI Demo v0.1",
    "input_features": ["temp", "sal", "chl"],
    "target": "FGI_Score",
    "architecture": "SimpleNet(3→8→1)",
    "loss": float(loss.item())
}
with open(META_PATH, "w") as f:
    json.dump(meta, f, indent=2)

print("📦 Model, scaler, and metadata saved in:", MODELS)
