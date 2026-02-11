from fastapi import FastAPI
<<<<<<< HEAD
from app.routers import fgi
=======

from app.routers.fgi import router as fgi_router
from app.routers.signals import router as signals_router
from app.routers.fgi_tiles import router as fgi_tiles_router
from app.routers.waves import router as waves_router
from app.routers.surf import router as surf_router
from app.routers.data import router as data_router
from app.routers.fgi_cache import router as fgi_cache_router
from app.routers.fgi_map_build import router as fgi_map_router
from app.routers.ocean_memory import router as ocean_memory_router
from app.routers.fgi_map import router as fgi_map_router
from app.routers import earth
from app.routers.time_series import router as time_series_router
from fastapi import FastAPI
from app.services.user_store import init_db
from app.routers.auth import router as auth_router
from app.routers.me import router as me_router
from app.routers.time_series_profile import router as ts_profile_router
HEAD
0dc80102 (time-series: depth temp profile chart + thermocline/MLD tooltip polish)

from app.routers.fgi_time_series_profile import router as fgi_ts_profile_router
f2877372 (api: add /api/v1/fgi/time-series/temp-profile alias)

app = FastAPI()
app.include_router(fgi.router, prefix="/api/v1/fgi")

# daftar router
app.include_router(fgi.router)

@app.get("/health")
def health():
HEAD
    return {"ok": True, "service": "nelaya-ai", "version": "0.9.1"}
    return {"ok": True}

# mount routers (router masing-masing sudah punya prefix /api/v1)
init_db()
app.include_router(auth_router)
app.include_router(me_router)
app.include_router(fgi_router)
app.include_router(signals_router)
app.include_router(fgi_tiles_router)
app.include_router(waves_router)
app.include_router(surf_router)
app.include_router(data_router)
app.include_router(fgi_cache_router)
app.include_router(fgi_map_router)
app.include_router(ocean_memory_router)
app.include_router(fgi_map_router)
app.include_router(earth.router)
app.include_router(time_series_router)
app.include_router(ts_profile_router)
app.include_router(fgi_ts_profile_router)

0dc80102 (time-series: depth temp profile chart + thermocline/MLD tooltip polish)
