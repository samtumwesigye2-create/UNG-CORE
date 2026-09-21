from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.ml.training_pipeline import run_training_pipeline

router = APIRouter(prefix="/v1/ml/training-pipeline", tags=["machine-learning-training-pipeline"])


class PromotionGate(BaseModel):
    metric: str = Field(min_length=1, max_length=64)
    operator: str = Field(min_length=1, max_length=8)
    value: float


class TrainingPipelineRequest(BaseModel):
    model_key: str = Field(min_length=1, max_length=160)
    algorithm: str
    x: list[float] = Field(min_length=5, max_length=100000)
    y: list[float] = Field(min_length=5, max_length=100000)
    learning_rate: float = Field(default=0.01, gt=0)
    epochs: int = Field(default=1000, ge=1, le=100000)
    test_fraction: float = Field(default=0.2, gt=0, lt=1)
    seed: int = 42
    threshold: float = Field(default=0.5, gt=0, lt=1)
    gates: list[PromotionGate] = Field(default_factory=list, max_length=50)
    metadata: dict = Field(default_factory=dict)
    promote_if_passed: bool = False


@router.post("/run")
async def run_pipeline(
    body: TrainingPipelineRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.train")),
):
    try:
        result = await run_training_pipeline(
            db,
            model_key=body.model_key,
            algorithm=body.algorithm,
            x=body.x,
            y=body.y,
            created_by=principal.subject,
            learning_rate=body.learning_rate,
            epochs=body.epochs,
            test_fraction=body.test_fraction,
            seed=body.seed,
            threshold=body.threshold,
            gates=[gate.model_dump() for gate in body.gates],
            metadata=body.metadata,
            promote_if_passed=body.promote_if_passed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "algorithm": result.algorithm,
        "task": result.task,
        "train_size": result.train_size,
        "test_size": result.test_size,
        "model": result.model,
        "evaluation": result.evaluation,
        "promoted": result.promoted,
        "previous_active_version": result.previous_active_version,
    }
