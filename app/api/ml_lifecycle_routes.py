from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.ml.champion_challenger import lifecycle_snapshot, promote_challenger

router = APIRouter(prefix="/v1/ml/lifecycle", tags=["machine-learning-lifecycle"])


class PromotionPolicyRequest(BaseModel):
    minimum_canary_comparisons: int = Field(default=10, ge=0, le=100000)
    maximum_canary_difference: float = Field(default=0.20, ge=0)
    minimum_feedback: int = Field(default=20, ge=1, le=100000)
    maximum_production_degradation: float = Field(default=0.20, ge=0)


@router.get("/{model_key}")
async def get_lifecycle(
    model_key: str,
    minimum_canary_comparisons: int = Query(default=10, ge=0, le=100000),
    maximum_canary_difference: float = Query(default=0.20, ge=0),
    minimum_feedback: int = Query(default=20, ge=1, le=100000),
    maximum_production_degradation: float = Query(default=0.20, ge=0),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.monitor")),
):
    try:
        return await lifecycle_snapshot(
            db,
            model_key=model_key,
            minimum_canary_comparisons=minimum_canary_comparisons,
            maximum_canary_difference=maximum_canary_difference,
            minimum_feedback=minimum_feedback,
            maximum_production_degradation=maximum_production_degradation,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{model_key}/challengers/{version}/promote")
async def promote(
    model_key: str,
    version: int,
    body: PromotionPolicyRequest,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.models.activate")),
):
    try:
        return await promote_challenger(
            db,
            model_key=model_key,
            version=version,
            minimum_canary_comparisons=body.minimum_canary_comparisons,
            maximum_canary_difference=body.maximum_canary_difference,
            minimum_feedback=body.minimum_feedback,
            maximum_production_degradation=body.maximum_production_degradation,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
