
from fastapi import FastAPI

app = FastAPI(title="NELAYA‑AI API", version="0.1.0")

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "service": "nelaya-api"}
