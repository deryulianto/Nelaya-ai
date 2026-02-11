from fastapi import APIRouter
import platform, psutil

router = APIRouter(prefix="/system", tags=["System"])

@router.get("/status")
def system_status():
    return {
        "os": platform.system(),
        "cpu": psutil.cpu_percent(),
        "memory": psutil.virtual_memory().percent
    }
