from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.ml.auto_retraining import run_controlled_auto_retraining

router = APIRouter(prefix="/v1/ml/auto-retraining", tags=["machine-learning-auto-retraining"])


class PromotionGate(BaseModel):
    metric: str = Field(min_length=1, max_length=64)
    operator: str = Field(min_length=1, max_length=8)
    value: float


class AutoRetrainingRequest(BaseModel):
    x: list[float] = Field(min_length=5, max_length=100000)
    y: list[float] = Field(min_length=5, max_length=100000)
    learning_rate: float = Field(default=0.01, gt=0)
    epochs: int = Field(default=1000, ge=1, le=100000)
    test_fraction: float = Field(default=0.2, gt=0, lt=1)
    seed: int = 42
    threshold: float = Field(default=0.5, gt=0, lt=1)
    gates: list[PromotionGate] = Field(default_factory=list, max_length=50)
    mean_shift_threshold: float = Field(default=1.0, gt=0)
    std_ratio_threshold: float = Field(default=2.0, gt=1)
    performance_degradation_threshold: float = Field(default=0.15, gt=0, lt=1)
    promote_if_passed: bool = True


@router.post("/{model_key}/run")
async def run_auto_retraining(
    model_key: str,
    body: AutoRetrainingRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.retrain")),
):
    try:
        result = await run_controlled_auto_retraining(
            db,
            model_key=model_key,
            x=body.x,
            y=body.y,
            actor_id=principal.subject,
            learning_rate=body.learning_rate,
            epochs=body.epochs,
            test_fraction=body.test_fraction,
            seed=body.seed,
            threshold=body.threshold,
            gates=[gate.model_dump() for gate in body.gates],
            mean_shift_threshold=body.mean_shift_threshold,
            std_ratio_threshold=body.std_ratio_threshold,
            performance_degradation_threshold=body.performance_degradation_threshold,
            promote_if_passed=body.promote_if_passed,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "model_key": result.model_key,
        "drift": result.drift,
        "retraining_started": result.retraining_started,
        "candidate": result.candidate,
        "promoted": result.promoted,
        "previous_active_version": result.previous_active_version,
        "active_version": result.active_version,
    }
