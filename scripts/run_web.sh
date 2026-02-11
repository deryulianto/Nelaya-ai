#!/bin/bash
# ==================================================
# 🚀 Jalankan NELAYA-AI Web Dashboard (Streamlit)
# ==================================================

# Pastikan di direktori root proyek
cd "$(dirname "$0")/.."

# Pastikan virtual environment aktif
if [ -z "$VIRTUAL_ENV" ]; then
    echo "[INFO] Mengaktifkan environment virtual..."
    source .venv/bin/activate
fi

# Jalankan Streamlit
echo "[INFO] 🚀 Menjalankan NELAYA-AI Dashboard di http://127.0.0.1:8501 ..."
streamlit run dashboard/Home.py --server.address 0.0.0.0 --server.port 8501
