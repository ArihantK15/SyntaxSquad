from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from app.api.deps import get_db
from app.services.policy_service import get_policy, update_policy

router = APIRouter(prefix="/settings", tags=["settings"])


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weight_mrz: float
    weight_tamper: float
    weight_face: float
    weight_consistency: float
    weight_watchlist: float
    threshold_low: float
    threshold_medium: float
    threshold_high: float


class PolicyUpdate(BaseModel):
    weight_mrz: float
    weight_tamper: float
    weight_face: float
    weight_consistency: float
    weight_watchlist: float
    threshold_low: float
    threshold_medium: float
    threshold_high: float


@router.get("/policy", response_model=PolicyOut)
def get_policy_settings(db: Session = Depends(get_db)):
    """The risk engine's live weights/thresholds -- what the Settings page's
    sliders actually control."""
    return get_policy(db)


@router.post("/policy", response_model=PolicyOut)
def update_policy_settings(payload: PolicyUpdate, db: Session = Depends(get_db)):
    total_weight = (
        payload.weight_mrz + payload.weight_tamper + payload.weight_face
        + payload.weight_consistency + payload.weight_watchlist
    )
    if abs(total_weight - 1.0) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Factor weights must sum to 100% (got {round(total_weight * 100, 1)}%)."
        )
    if not (0 <= payload.threshold_low < payload.threshold_medium < payload.threshold_high <= 100):
        raise HTTPException(
            status_code=400,
            detail="Risk tier cutoffs must be strictly ascending and within 0-100."
        )
    return update_policy(db, **payload.model_dump())
