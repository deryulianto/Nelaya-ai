import os
import json
from fastapi import APIRouter, HTTPException, Header
from auth_service.app.utils.security import verify_jwt
from auth_service.app.services.user_store import get_user_by_phone

router = APIRouter(prefix="/api/v1/nelayan", tags=["Nelayan"])

SNAPSHOT_PATH = "/home/coastalai/NELAYA-AI-LAB/data/catch_reco_today.json"

def _get_phone_from_auth(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ValueError("missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_jwt(token)
    return str(payload.get("sub"))

@router.get("/dashboard/today")
def dashboard_today(authorization: str | None = Header(default=None)):
    try:
        phone = _get_phone_from_auth(authorization)
        user = get_user_by_phone(phone)
        if not user:
            raise ValueError("user not found")

        landing_port = user.get("landing_port")
        gear = user.get("gear_subtype")

        if not landing_port or not gear:
            raise ValueError("profil belum lengkap")

        if not os.path.exists(SNAPSHOT_PATH):
            raise ValueError("data rekomendasi belum tersedia")

        with open(SNAPSHOT_PATH, "r") as f:
            data = json.load(f)

        # cari rekomendasi sesuai port + gear
        for port_block in data.get("ports", []):
            if port_block["landing_port"] == landing_port and port_block["gear_subtype"] == gear:
                top = port_block.get("recommendations", [])
                if not top:
                    raise ValueError("tidak ada rekomendasi hari ini")

                best = top[0]

                return {
                    "status": best.get("go_indicator", "Belum tersedia"),
                    "perkiraan_bersih": best.get("net_income_est_idr"),
                    "minimal_agar_tidak_rugi_kg": best.get("break_even_kg"),
                    "risiko": best.get("risk_level"),
                    "lokasi_terbaik": top[:5]
                }

        raise ValueError("kombinasi port+gear tidak ditemukan")

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
