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

# ✅ NEW: FGI Species API v0.4.1
mount("app.routers.fgi_species", prefix="")

# ✅ NEW: FGI Feature Store v0.1
mount("app.routers.fgi_feature_store", prefix="")

# ✅ NEW: Behavior FGI
mount("app.routers.fgi_behavior", prefix="")
mount("app.routers.fgi_behavior", prefix="/api/v1")

mount("app.routers.fgi_zones", prefix="")
mount("app.routers.fgi_zones", prefix="/api/v1")

mount("app.routers.fgi_decision", prefix="")
mount("app.routers.fgi_decision", prefix="/api/v1")

# ✅ NEW: Upwelling Watch / UPI
mount("app.routers.upwelling", prefix="")
mount("app.routers.upwelling", prefix="/api/v1")

# ✅ NEW: Pelagic Movement Intelligence
mount("app.routers.fgi_pelagic_movement", prefix="")
mount("app.routers.fgi_pelagic_movement", prefix="/api/v1")

# ✅ NEW: FGI Physics-informed Support
mount("app.routers.fgi_physics_support", prefix="")
mount("app.routers.fgi_physics_support", prefix="/api/v1")

# ✅ NEW: Daily Current Analysis Dashboard
mount("app.routers.current_analysis", prefix="")
mount("app.routers.current_analysis", prefix="/api/v1")

# ✅ NEW: Integrated Ocean Decision Intelligence v0.9-alpha
mount("app.routers.ocean_decision", prefix="")

# ✅ NEW: Tuna Depth Current Layer v0.7.3
mount("app.routers.tuna_depth_current", prefix="")

# ✅ NEW: NS-informed Ocean Diagnostics v0.8-alpha
mount("app.routers.ns_ocean_diagnostics", prefix="")

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
mount("app.routers.fgi_plan", prefix="")
mount("app.routers.fgi_trip", prefix="")
mount("app.routers.ocean_memory", prefix="")
mount("app.routers.fgi_time_series", prefix="")
mount("app.routers.fgi_time_series_profile", prefix="")

mount("app.routers.fgi_rumpon", prefix="")
mount("app.routers.rumpon", prefix="")

mount("app.routers.time_series", prefix="")
mount("app.routers.time_series_profile", prefix="")

mount("app.routers.fgi_time_series_station", prefix="")

# -----------------------------------------------------------------------------
# OCEAN INTELLIGENCE ROUTERS
# -----------------------------------------------------------------------------
mount("app.routers.osi_v1", prefix="")
mount("app.routers.osi_today", prefix="")
mount("app.routers.osi_map", prefix="")
# mount("app.routers.insight_today", prefix="")
mount("app.routers.brief_today", prefix="")

mount("app.routers.island", prefix="")
mount("app.routers.island", prefix="/api/v1")

mount("app.routers.ocean_ask", prefix="")

mount("app.routers.iod", prefix="")
mount("app.routers.iod", prefix="/api/v1")

mount("app.routers.insight", prefix="")
mount("app.routers.insight", prefix="/api/v1")

mount("app.routers.narrative", prefix="")
mount("app.routers.narrative", prefix="/api/v1")

mount("app.routers.bleaching", prefix="")
mount("app.routers.bleaching", prefix="/api/v1")

# Biodiversity Watch v0.1
mount("app.routers.biodiversity", prefix="")

mount("app.routers.decision", prefix="")
mount("app.routers.decision", prefix="/api/v1")



# Optional init_db
try:
    from app.services.user_store import init_db  # type: ignore
    init_db()
except Exception:
    pass