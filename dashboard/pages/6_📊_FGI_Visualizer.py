import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.figure_factory as ff
from pathlib import Path

st.set_page_config(page_title="FGI Visualizer", page_icon="📊", layout="wide")

st.title("📊 FGI Visualizer 3D Dashboard")
st.markdown("""
Visualisasi interaktif **Fish Growth Intelligence (FGI)**  
untuk memahami hubungan antara suhu laut, salinitas, dan klorofil terhadap tingkat pertumbuhan ikan.
""")

log_path = Path("logs/inference_log.csv")

if not log_path.exists():
    st.warning("⚠️ Belum ada data inferensi. Lakukan prediksi dulu melalui menu *AI Inference*.")
    st.stop()

df = pd.read_csv(log_path)

expected_cols = ["timestamp", "temp", "sal", "chl", "FGI", "category"]
for col in expected_cols:
    if col not in df.columns:
        df[col] = np.nan

df["FGI"] = pd.to_numeric(
    df["FGI"].astype(str).str.replace("FGI", "").str.replace(":", ""), errors="coerce"
)
df.dropna(subset=["FGI"], inplace=True)

st.success(f"✅ Data FGI ditemukan: {len(df)} record")

# --- SCATTER 3D ---
st.subheader("🌐 Scatter 3D: Hubungan Temp, Sal, Chl terhadap FGI")
fig3d = px.scatter_3d(
    df,
    x="temp",
    y="sal",
    z="chl",
    color="FGI",
    size="FGI",
    hover_name="timestamp",
    color_continuous_scale="Viridis",
    title="3D Plot — Dinamika Lingkungan Laut & FGI",
)
fig3d.update_traces(marker=dict(opacity=0.8, line=dict(width=0.5, color="DarkSlateGrey")))
st.plotly_chart(fig3d, use_container_width=True)

# --- HEATMAP Korelasi ---
st.subheader("🔥 Heatmap Korelasi Antar-Parameter Laut")
corr = df[["temp", "sal", "chl", "FGI"]].corr()
fig_corr = px.imshow(
    corr,
    text_auto=True,
    color_continuous_scale="Tealrose",
    title="Korelasi Parameter Laut dan FGI",
)
st.plotly_chart(fig_corr, use_container_width=True)

# --- HISTOGRAM ---
st.subheader("📈 Distribusi Nilai FGI")
fig_hist = px.histogram(
    df,
    x="FGI",
    nbins=20,
    color="category",
    title="Distribusi FGI berdasarkan Kategori",
    color_discrete_sequence=px.colors.qualitative.Dark24,
)
st.plotly_chart(fig_hist, use_container_width=True)

st.info("Analisis visual ini membantu memahami hubungan antar variabel laut terhadap pertumbuhan ikan.")
