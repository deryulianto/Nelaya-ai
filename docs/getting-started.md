# Mulai

## Dev cepat (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn apps.api.main:app --reload --port 8000
# tab baru:
streamlit run apps/web/app.py --server.port 8501
```
- API: http://localhost:8000/docs
- Web: http://localhost:8501

## Docker
```bash
docker compose up --build -d
```
