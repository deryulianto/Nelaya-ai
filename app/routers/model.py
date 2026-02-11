from fastapi import APIRouter
from app.utils.ai_tools import run_inference
router = APIRouter(prefix="/model", tags=["Model"])
@router.get("/predict")
def predict(example: str):
    result = run_inference(example)
    return {"input": example, "prediction": result}
