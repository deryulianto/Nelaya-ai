from fastapi import FastAPI
from app.routers import fgi

app = FastAPI()
app.include_router(fgi.router, prefix="/api/v1/fgi")

# daftar router
app.include_router(fgi.router)

@app.get("/health")
def health():
    return {"ok": True, "service": "nelaya-ai", "version": "0.9.1"}
