from fastapi import APIRouter

from app.estimate import (
    FINISH_LEVELS,
    HOUSE_TYPES,
    REGIONS,
    EstimateInput,
    calculate_estimate,
)

router = APIRouter(prefix="/v1/estimates", tags=["estimates"])


@router.get("/presets")
def presets():
    return {
        "ok": True,
        "data": {
            "regions": REGIONS,
            "house_types": HOUSE_TYPES,
            "finish_levels": FINISH_LEVELS,
        },
    }


@router.post("/calculate")
def calculate(body: EstimateInput):
    return {"ok": True, "data": calculate_estimate(body)}
