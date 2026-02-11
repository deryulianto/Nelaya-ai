# -*- coding: utf-8 -*-
from pathlib import Path
import json, joblib
import numpy as np, pandas as pd
import torch, torch.nn as nn
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT/"models"
OUTDIR = ROOT/"data/processed"

# 1) Load spec & scaler
spec = json.loads((ROOT/"config/fgi_feature_spec.json").read_text())
FEATURES = spec["features"]
scaler = joblib.load(MODELS/"fgi_scaler.pkl")

# 2) Dua varian arsitektur
class MLP4(nn.Module):
    def __init__(self, d_in):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(d_in, 256), nn.ReLU(),
            nn.Linear(256, 256), nn.ReLU(),
            nn.Linear(256, 128), nn.ReLU(),
            nn.Linear(128, 1), nn.Sigmoid()
        )
    def forward(self, x): return self.net(x).squeeze(1)

class MLP2(nn.Module):
    def __init__(self, d_in, hidden):
        super().__init__()
        self.fc1 = nn.Linear(d_in, hidden)
        self.act = nn.ReLU()
        self.fc2 = nn.Linear(hidden, 1)
        self.out = nn.Sigmoid()
    def forward(self, x):
        x = self.act(self.fc1(x))
        x = self.out(self.fc2(x))
        return x.squeeze(1)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
state = torch.load(MODELS/"fgi_dl_best.pt", map_location="cpu")
state_keys = set(state.keys())

# 3) Autodetect arsitektur & hidden dim
if any(k.startswith("fc1.") for k in state_keys):
    # Model 2-layer; ambil hidden dari ukuran bobot
    hidden = state["fc1.weight"].shape[0]  # contoh: 8
    ModelCls = lambda d_in: MLP2(d_in, hidden)
elif any(k.startswith("net.0.") for k in state_keys):
    ModelCls = lambda d_in: MLP4(d_in)
else:
    raise SystemExit(f"Unknown model keys in state_dict: {sorted(list(state_keys))[:6]} ...")

model = ModelCls(len(FEATURES)).to(DEVICE)
model.load_state_dict(state, strict=True)
model.eval()

# 4) Ambil grid fitur
grid_path = ROOT/"data/processed"/"grid_features.parquet"
if not grid_path.exists():
    raise SystemExit(f"Grid file not found: {grid_path}")

df = pd.read_parquet(grid_path)
need = set(["lon","lat"] + FEATURES)
miss = [c for c in need if c not in df.columns]
if miss:
    raise SystemExit(f"Missing columns in grid: {miss}")

# 5) Scale & predict
X = scaler.transform(df[FEATURES].values.astype(np.float32))
X = torch.from_numpy(X).to(DEVICE)
with torch.no_grad():
    p = model(X).cpu().numpy()

df["FGI_score"] = p

# 6) Simpan GeoJSON
OUTDIR.mkdir(parents=True, exist_ok=True)
gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
out = OUTDIR/"fgi_pred_points.geojson"
gdf[["lon","lat","FGI_score","geometry"]].to_file(out, driver="GeoJSON")
print("OK:", out, "| points:", len(gdf), "| n_features:", len(FEATURES))
