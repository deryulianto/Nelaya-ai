# -*- coding: utf-8 -*-
"""
NELAYA-AI · FGI Inference + Visualizer
- Ambil skor FGI dari FastAPI: /api/v1/fgi/score
- Normalisasi skor ke 0..1 (aman jika API kirim logit)
- Parsing angka format Indonesia (koma)
- Tampilkan peta dari data/processed/fgi_pred_points.geojson
"""
from __future__ import annotations

import os
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

# =========================
# Konfigurasi dasar
# =========================
st.set_page_config(page_title="NELAYA-AI · FGI Inference", layout="wide")
API_URL = os.environ.get("NELAYA_API_URL", "http://localhost:8000/api/v1/fgi/score")
ROOT = Path(__file__).resolve().parents[1]
GEOJSON_PATH = ROOT / "data" / "processed" / "fgi_pred_points.geojson"

# =========================
# Helpers
# =========================
def parse_id_float(x) -> float:
    """Ubah '28,00' -> 28.00; aman terhadap input kosong."""
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return 0.0

def to_prob(y: float) -> float:
    """Pastikan skor 0..1. Jika di luar, asumsikan logit → sigmoid; clamp."""
    try:
        y = float(y)
    except Exception:
        return 0.0
    if y < 0.0 or y > 1.0:
        y = 1.0 / (1.0 + np.exp(-y))
    return float(min(1.0, max(0.0, y)))

def to_band(p: float) -> str:
    return "High" if p >= 0.75 else ("Medium" if p >= 0.50 else "Low")

def api_score(temp: float, sal: float, chl: float, timeout: float = 6.0) -> float:
    payload = {"data": {"temp": float(temp), "sal": float(sal), "chl": float(chl)}}
    r = requests.post(API_URL, json=payload, timeout=timeout)
    r.raise_for_status()
    resp = r.json()
    return to_prob(resp.get("score", 0.0))

def load_points_df(geojson_path: Path) -> pd.DataFrame | None:
    """Baca GeoJSON hasil inferensi dan siapkan kolom latitude/longitude untuk st.map."""
    if not geojson_path.exists():
        return None

    # Coba gunakan geopandas jika ada; kalau tidak, fallback ke json standar
    try:
        import geopandas as gpd  # type: ignore
        gdf = gpd.read_file(geojson_path)
        df = pd.DataFrame(gdf.drop(columns="geometry"))
        # rename agar cocok dengan st.map
        rename_map = {}
        if "lon" in df.columns and "longitude" not in df.columns:
            rename_map["lon"] = "longitude"
        if "lat" in df.columns and "latitude" not in df.columns:
            rename_map["lat"] = "latitude"
        df = df.rename(columns=rename_map)
    except Exception:
        feats = json.loads(geojson_path.read_text()).get("features", [])
        rows = []
        for f in feats:
            props = f.get("properties", {})
            coords = f.get("geometry", {}).get("coordinates", [None, None])
            props["longitude"] = coords[0]
            props["latitude"] = coords[1]
            rows.append(props)
        df = pd.DataFrame(rows)

    keep = [c for c in ["latitude", "longitude", "FGI_score"] if c in df.columns]
    return df[keep].copy() if keep else None

# =========================
# Header
# =========================
st.markdown("## 🙂 AI Inference")
st.caption("Masukkan parameter laut untuk memprediksi **Fish Growth Index (FGI)**")

# =========================
# Input form
# =========================
c1, c2, c3 = st.columns(3)
with c1:
    suhu_str = st.text_input("🌡️ Suhu Laut (°C)", value="28,00")
with c2:
    sal_str = st.text_input("🧪 Salinitas (PSU)", value="33,00")
with c3:
    chl_str = st.text_input("🌿 Klorofil (mg/m³)", value="0,50")

suhu = parse_id_float(suhu_str)
sal = parse_id_float(sal_str)
chl = parse_id_float(chl_str)

if st.button("🧠 Prediksi FGI"):
    try:
        p = api_score(suhu, sal, chl)
        st.success(f"FGI Score: {p:.4f} — {to_band(p)}")
    except Exception as e:
        st.error(f"Gagal memanggil API: {e}")
        st.info("Pastikan FastAPI aktif di **http://localhost:8000** dan endpoint **/api/v1/fgi/score** tersedia.")

st.divider()

# =========================
# Visualizer (Map)
# =========================
st.markdown("### 🗺️ FGI Visualizer")
thr = st.slider("Ambang FGI (threshold)", 0.0, 1.0, 0.70, 0.01)

df_pts = load_points_df(GEOJSON_PATH)
if df_pts is None:
    st.warning("File hasil inferensi belum tersedia. Jalankan inferensi grid untuk membuat **data/processed/fgi_pred_points.geojson**.")
else:
    total = len(df_pts)
    df_view = df_pts.copy()
    if "FGI_score" in df_view.columns:
        df_view = df_view[df_view["FGI_score"] >= thr]
    st.write(f"Titik: **{len(df_view):,}** dari {total:,} (≥ {thr:.2f})")

    # st.map memerlukan kolom latitude/longitude
    if {"latitude", "longitude"}.issubset(df_view.columns):
        st.map(df_view[["latitude", "longitude"]], zoom=6, size=3)
    else:
        st.warning("Kolom latitude/longitude tidak ditemukan pada data peta.")
