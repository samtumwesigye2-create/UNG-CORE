from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.ml.evaluation import evaluate_predictions, train_test_split_indices
from app.services.ml.model_registry import record_validation, serialize_model

router = APIRouter(prefix="/v1/ml/evaluation", tags=["machine-learning-evaluation"])


class SplitRequest(BaseModel):
    size: int = Field(ge=3, le=1_000_000)
    test_fraction: float = Field(default=0.2, gt=0, lt=1)
    seed: int = 42


class PromotionGate(BaseModel):
    metric: str = Field(min_length=1, max_length=64)
    operator: str = Field(min_length=1, max_length=8)
    value: float


class ValidateModelRequest(BaseModel):
    task: str
    actual: list[float] = Field(min_length=1, max_length=100000)
    predicted: list[float] = Field(min_length=1, max_length=100000)
    baseline_predicted: list[float] | None = Field(default=None, max_length=100000)
    threshold: float = Field(default=0.5, gt=0, lt=1)
    gates: list[PromotionGate] = Field(default_factory=list, max_length=50)


@router.post("/split")
async def split_dataset(
    body: SplitRequest,
    _: Principal = Depends(require_permission("ung.core.ml.evaluate")),
):
    try:
        train_indices, test_indices = train_test_split_indices(
            body.size,
            test_fraction=body.test_fraction,
            seed=body.seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "train_indices": train_indices,
        "test_indices": test_indices,
        "train_size": len(train_indices),
        "test_size": len(test_indices),
        "seed": body.seed,
    }


@router.post("/models/{model_key}/versions/{version}/validate")
async def validate_model(
    model_key: str,
    version: int,
    body: ValidateModelRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.evaluate")),
):
    try:
        result = evaluate_predictions(
            task=body.task,
            actual=body.actual,
            predicted=body.predicted,
            baseline_predicted=body.baseline_predicted,
            threshold=body.threshold,
            gates=[gate.model_dump() for gate in body.gates],
        )
        row = await record_validation(
            db,
            model_key,
            version,
            task=result.task,
            metrics=result.metrics,
            baseline_metrics=result.baseline_metrics,
            baseline_improvement=result.baseline_improvement,
            gates=result.gates,
            passed=result.passed,
            validated_by=principal.subject,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "passed": result.passed,
        "metrics": result.metrics,
        "baseline_metrics": result.baseline_metrics,
        "baseline_improvement": result.baseline_improvement,
        "gates": result.gates,
        "model": serialize_model(row),
    }
