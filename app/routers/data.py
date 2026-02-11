from fastapi import APIRouter
from app.utils.io_tools import list_datasets
router = APIRouter(prefix="/data", tags=["Data"])
@router.get("/list")
def list_data():
    return {"datasets": list_datasets()}
