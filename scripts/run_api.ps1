param([int]$Port=8000)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn apps.api.main:app --reload --port $Port
