import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path

st.set_page_config(page_title="FGI Evaluator", page_icon="📈", layout="wide")

st.title("📈 FGI Evaluator Dashboard")
st.markdown("""
Analisis performa dan pola prediksi **Fish Growth Intelligence (FGI)**  
berdasarkan hasil inferensi yang tersimpan di `logs/inference_log.csv`.
""")

# === Load Data ===
log_path = Path("logs/inference_log.csv")

if not log_path.exists() or log_path.stat().st_size == 0:
    st.warning("⚠️ Belum ada data inferensi. Lakukan prediksi dulu melalui menu **AI Inference**.")
    st.stop()

try:
    df = pd.read_csv(log_path)
except Exception as e:
    st.error(f"Gagal membaca file log: {e}")
    st.stop()

# === Auto-fix header dan kolom ===
expected_cols = ["timestamp", "temp", "sal", "chl", "FGI", "category"]

# Jika kolom kurang, tambahkan placeholder
for col in expected_cols:
    if col not in df.columns:
        df[col] = np.nan

# Pastikan kolom FGI numerik dan bersih
df["FGI"] = (
    df["FGI"]
    .astype(str)
    .str.replace("FGI", "", regex=False)
    .str.replace(":", "", regex=False)
)
df["FGI"] = pd.to_numeric(df["FGI"], errors="coerce")

# Bersihkan timestamp (optional)
if "timestamp" in df.columns:
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

# Hapus baris kosong / tidak valid
df = df.dropna(subset=["FGI"])

if df.empty:
    st.warning("⚠️ Data FGI belum valid. Pastikan log hasil inferensi berisi kolom numerik.")
    st.stop()

# === Statistik Umum ===
st.subheader("📊 Statistik Umum")
col1, col2, col3 = st.columns(3)

col1.metric("Total Inferensi", f"{len(df)}")
col2.metric("Rata-rata FGI", f"{df['FGI'].mean():.3f}")
col3.metric("FGI Maksimum", f"{df['FGI'].max():.3f}")

# === Distribusi Kategori ===
if "category" in df.columns:
    cat_count = df["category"].value_counts().reset_index()
    cat_count.columns = ["Kategori", "Jumlah"]
    st.bar_chart(cat_count.set_index("Kategori"))
else:
    st.info("Kolom kategori tidak ditemukan dalam log.")

# === Tabel Data (opsional toggle) ===
st.sidebar.header("🧭 Data Control")
show_raw = st.sidebar.checkbox("Tampilkan data mentah")

if show_raw:
    st.subheader("🧾 Data Mentah")
    st.dataframe(df.tail(20))

# === Trend Plot ===
if "timestamp" in df.columns:
    df = df.sort_values("timestamp")
    st.line_chart(df.set_index("timestamp")["FGI"])

st.success("✅ Evaluasi selesai tanpa error.")
