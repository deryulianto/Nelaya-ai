# auth_service/app/main.py
from fastapi import FastAPI
from auth_service.app.services.user_store import init_db
from auth_service.app.routers.auth import router as auth_router
from auth_service.app.routers.me import router as me_router
from auth_service.app.routers.nelayan import router as nelayan_router
from auth_service.app.routers.trip import router as trip_router
from auth_service.app.routers.batch import router as batch_router

app = FastAPI(title="NELAYA-AI Auth Service", version="0.1.0")

init_db()
app.include_router(auth_router)
app.include_router(me_router)
app.include_router(nelayan_router)
app.include_router(trip_router)
app.include_router(batch_router)

@app.get("/healthz")
def healthz():
    return {"ok": True}