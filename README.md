
# NELAYA‑AI (Starter Kit)

Monorepo ringan untuk memulai **NELAYA‑AI** sebagai *frontier ocean* platform.

## Struktur
```
.
├─ apps/
│  ├─ api/          # FastAPI (healthcheck)
│  └─ web/          # Streamlit landing (tanpa aset gambar)
├─ .github/workflows/ci.yml
├─ docker-compose.yml
├─ .gitignore
├─ LICENSE
└─ requirements.txt
```

## Cara jalan (lokal, Windows PowerShell)

```powershell
# 1) siapkan venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2) jalankan API (port 8000)
uvicorn apps.api.main:app --reload --port 8000

# 3) jalankan Web (port 8501) di jendela lain
streamlit run apps/web/app.py --server.port 8501
```

Buka:
- API docs: http://localhost:8000/docs
- Healthcheck: http://localhost:8000/api/v1/health
- Web: http://localhost:8501

## Cara jalan (Docker)
```bash
docker compose up --build -d
```

## Lisensi
Apache-2.0 (lihat `LICENSE`).
