from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.ml.training_pipeline import run_training_pipeline
from app.services.ml.tuning import tune_hyperparameters

router = APIRouter(prefix="/v1/ml/tuning", tags=["machine-learning-tuning"])


class PromotionGate(BaseModel):
    metric: str = Field(min_length=1, max_length=64)
    operator: str = Field(min_length=1, max_length=8)
    value: float


class TuningRequest(BaseModel):
    model_key: str = Field(min_length=1, max_length=160)
    algorithm: str
    x: list[float] = Field(min_length=5, max_length=100000)
    y: list[float] = Field(min_length=5, max_length=100000)
    learning_rates: list[float] = Field(default_factory=lambda: [0.001, 0.01, 0.05], min_length=1, max_length=20)
    epochs_options: list[int] = Field(default_factory=lambda: [500, 1000, 3000], min_length=1, max_length=20)
    thresholds: list[float] = Field(default_factory=lambda: [0.4, 0.5, 0.6], min_length=1, max_length=20)
    preprocessing_options: list[str] = Field(default_factory=lambda: ["standardize", "minmax"], min_length=1, max_length=3)
    folds: int = Field(default=5, ge=2, le=20)
    seed: int = 42
    test_fraction: float = Field(default=0.2, gt=0, lt=1)
    gates: list[PromotionGate] = Field(default_factory=list, max_length=50)
    metadata: dict = Field(default_factory=dict)
    promote_if_passed: bool = False


@router.post("/run")
async def run_tuning(
    body: TuningRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.train")),
):
    try:
        tuning = tune_hyperparameters(
            algorithm=body.algorithm,
            x=body.x,
            y=body.y,
            learning_rates=body.learning_rates,
            epochs_options=body.epochs_options,
            thresholds=body.thresholds,
            preprocessing_options=body.preprocessing_options,
            folds=body.folds,
            seed=body.seed,
        )
        params = tuning.best_params
        pipeline = await run_training_pipeline(
            db,
            model_key=body.model_key,
            algorithm=body.algorithm,
            x=body.x,
            y=body.y,
            created_by=principal.subject,
            learning_rate=params["learning_rate"],
            epochs=params["epochs"],
            test_fraction=body.test_fraction,
            seed=body.seed,
            threshold=params.get("threshold", 0.5),
            gates=[gate.model_dump() for gate in body.gates],
            metadata={
                **body.metadata,
                "hyperparameter_tuning": {
                    "folds": tuning.folds,
                    "primary_metric": tuning.primary_metric,
                    "best_score": tuning.best_score,
                    "best_params": tuning.best_params,
                    "trial_count": len(tuning.trials),
                },
            },
            promote_if_passed=body.promote_if_passed,
            preprocessing=params["preprocessing"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "tuning": {
            "algorithm": tuning.algorithm,
            "task": tuning.task,
            "folds": tuning.folds,
            "primary_metric": tuning.primary_metric,
            "best_params": tuning.best_params,
            "best_score": tuning.best_score,
            "trials": tuning.trials,
        },
        "candidate": pipeline.model,
        "evaluation": pipeline.evaluation,
        "promoted": pipeline.promoted,
        "previous_active_version": pipeline.previous_active_version,
    }
