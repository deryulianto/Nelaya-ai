param([int]$Port=8501)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run apps/web/app.py --server.port $Port
