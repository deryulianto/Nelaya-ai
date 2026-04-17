# auth_service/app/main.py
from fastapi import FastAPI
from auth_service.app.services.user_store import init_db
from auth_service.app.routers.auth import router as auth_router
from auth_service.app.routers.me import router as me_router
from auth_service.app.routers.nelayan import router as nelayan_router
from auth_service.app.routers.trip import router as trip_router
from auth_service.app.routers.batch import router as batch_router
from auth_service.app.routers.listing import router as listing_router
from auth_service.app.routers.trace import router as trace_router
from auth_service.app.routers.public_listing import router as public_listing_router
from auth_service.app.routers.buyer_interest import router as buyer_interest_router
from auth_service.app.routers.public_marketplace import router as public_marketplace_router
from auth_service.app.routers.public_marketplace_insight import router as public_marketplace_insight_router
from auth_service.app.routers.public_marketplace_archive import router as public_marketplace_archive_router
from auth_service.app.routers.public_decision import router as public_decision_router

app = FastAPI(title="NELAYA-AI Auth Service", version="0.1.0")

init_db()
app.include_router(auth_router)
app.include_router(me_router)
app.include_router(nelayan_router)
app.include_router(trip_router)
app.include_router(batch_router)
app.include_router(listing_router)
app.include_router(trace_router)
app.include_router(public_listing_router)
app.include_router(buyer_interest_router)
app.include_router(public_marketplace_insight_router)
app.include_router(public_marketplace_archive_router)
app.include_router(public_decision_router)

@app.get("/healthz")
def healthz():
    return {"ok": True}