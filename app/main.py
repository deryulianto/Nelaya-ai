from __future__ import annotations

import os
import logging
import importlib
from fastapi import FastAPI

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("nelaya")

STRICT_IMPORT = os.getenv("NELAYA_STRICT_IMPORT", "0") == "1"

# -----------------------------------------------------------------------------
# App (buat app dulu, baru mount router)
# -----------------------------------------------------------------------------
app = FastAPI(title="NELAYA-AI API", version="0.9.1")


@app.get("/health")
def health():
    return {"ok": True, "service": "nelaya-ai", "version": "0.9.1"}


# -----------------------------------------------------------------------------
# Router mounting helper
# -----------------------------------------------------------------------------
def opt_router(module_path: str, attr: str = "router"):
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    except Exception as e:
        log.exception("❌ Router import failed: %s (%s)", module_path, e)
        if STRICT_IMPORT:
            raise
        return None


def mount(module_path: str, *, prefix: str = "", attr: str = "router"):
    r = opt_router(module_path, attr)
    if r is not None:
        app.include_router(r, prefix=prefix)
        log.info("✅ Mounted: %s (prefix='%s')", module_path, prefix)
    else:
        log.warning("⚠️ Skipped: %s", module_path)


# -----------------------------------------------------------------------------
# ROUTERS (urut jelas)
# -----------------------------------------------------------------------------
mount("app.routers.auth", prefix="")
mount("app.routers.me", prefix="")

mount("app.routers.fgi", prefix="")
mount("app.routers.fgi", prefix="/api/v1")

mount("app.routers.signals", prefix="")
mount("app.routers.earth", prefix="")
mount("app.routers.waves", prefix="")
# mount("app.routers.surf", prefix="")
mount("app.routers.surf_v1", prefix="")
mount("app.routers.data", prefix="")

mount("app.routers.fgi_cache", prefix="")
mount("app.routers.fgi_map", prefix="")
mount("app.routers.fgi_map_grid", prefix="")
mount("app.routers.fgi_recommendations", prefix="")
mount("app.routers.ocean_memory", prefix="")
mount("app.routers.fgi_time_series", prefix="")
mount("app.routers.fgi_time_series_profile", prefix="")

mount("app.routers.fgi_rumpon", prefix="")
mount("app.routers.rumpon", prefix="")

mount("app.routers.time_series", prefix="")
mount("app.routers.time_series_profile", prefix="")

# -----------------------------------------------------------------------------
# OCEAN INTELLIGENCE ROUTERS
# -----------------------------------------------------------------------------
mount("app.routers.osi_v1", prefix="")
mount("app.routers.osi_today", prefix="")
mount("app.routers.osi_map", prefix="")
mount("app.routers.insight_today", prefix="")
mount("app.routers.brief_today", prefix="")

mount("app.routers.ocean_ask", prefix="")

# Optional init_db
try:
    from app.services.user_store import init_db  # type: ignore
    init_db()
except Exception:
    pass