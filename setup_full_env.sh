#!/bin/bash
set -e

echo "=============================================="
echo "🚀 NELAYA-AI LAB: Full Environment Setup"
echo "=============================================="

# 1️⃣  Pastikan Python 3.11 tersedia
PY_VER=$(python3 --version)
echo "Python version: $PY_VER"

# 2️⃣  Buat virtual environment
if [ ! -d ".venv" ]; then
  echo "📦 Membuat virtual environment .venv ..."
  python3 -m venv .venv
else
  echo "✅ Virtual environment sudah ada."
fi

# 3️⃣  Aktivasi environment
echo "🔧 Mengaktifkan virtual environment ..."
source .venv/bin/activate

# 4️⃣  Upgrade pip
echo "⬆️  Meng-upgrade pip ..."
pip install --upgrade pip

# 5️⃣  Install paket utama
echo "📚 Menginstal core packages (AI, Big Data, Web) ..."
pip install numpy pandas polars dask duckdb
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install scikit-learn lightning transformers datasets opencv-python
pip install fastapi uvicorn streamlit requests python-dotenv sqlalchemy psutil matplotlib seaborn plotly

# 6️⃣  Tes GPU
echo "🧠 Mengecek GPU..."
python3 - << 'PYCODE'
import torch
if torch.cuda.is_available():
    print(f"✅ GPU terdeteksi: {torch.cuda.get_device_name(0)}")
else:
    print("⚠️ GPU tidak terdeteksi. Pastikan driver NVIDIA dan CUDA aktif.")
PYCODE

# 7️⃣  Tes Streamlit
echo "🌐 Mengecek Streamlit..."
python3 - << 'PYCODE'
import importlib.util
if importlib.util.find_spec("streamlit"):
    print("✅ Streamlit sudah terinstal dengan baik.")
else:
    print("❌ Streamlit belum ditemukan.")
PYCODE

# 8️⃣  Simpan dependencies
echo "📄 Menyimpan daftar paket ke requirements.txt ..."
pip freeze > requirements.txt

echo "=============================================="
echo "🎉 Setup Selesai!"
echo "Aktifkan environment dengan:"
echo "   source .venv/bin/activate"
echo "Jalankan backend dengan:"
echo "   bash scripts/run_api.sh"
echo "Jalankan dashboard dengan:"
echo "   streamlit run dashboard/Home.py --server.port 8501"
echo "=============================================="
